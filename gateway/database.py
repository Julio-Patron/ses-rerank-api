import abc
import asyncio
import hashlib
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ses_gateway_database")

# Environment configurations
POSTGRES_ENABLED = os.getenv("POSTGRES_ENABLED", "false").lower() == "true"
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB", "ses_gateway")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")

# Define Abstract Database Adapter
class DatabaseAdapter(abc.ABC):
    @abc.abstractmethod
    async def connect(self) -> None:
        pass

    @abc.abstractmethod
    async def get_api_key(self, key_hash: str) -> Optional[Dict[str, Any]]:
        pass

    @abc.abstractmethod
    async def create_api_key(self, name: str, namespace: str, rate_limit: int, role: str) -> Dict[str, Any]:
        pass

    @abc.abstractmethod
    async def revoke_api_key(self, key_token: str) -> bool:
        pass

    @abc.abstractmethod
    async def list_api_keys(self) -> List[Dict[str, Any]]:
        pass

    @abc.abstractmethod
    async def log_usage(self, tenant_id: str, api_key_id: Optional[str], endpoint: str, tokens: int, latency_ms: float) -> None:
        pass

    @abc.abstractmethod
    async def update_credits(self, key_hash: str, credits_deducted: int, tokens_saved: int) -> Dict[str, Any]:
        pass

    @abc.abstractmethod
    async def get_analytics(self) -> Dict[str, Any]:
        pass

    @abc.abstractmethod
    async def bootstrap_admin_key(self, admin_key: str) -> None:
        pass


# Concrete SQLite Adapter (Ideal for local standalone development / testing)
class SQLiteDatabaseAdapter(DatabaseAdapter):
    def __init__(self, db_path: str = "data/gateway.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    async def connect(self) -> None:
        # Run inside thread pool to prevent blocking event loop
        await asyncio.to_thread(self._run_migrations)
        logger.info(f"📂 SQLite persistent storage loaded at: {self.db_path}")

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _run_migrations(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 1. Tenants
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                plan_tier TEXT DEFAULT 'developer',
                rate_limit_per_minute INTEGER NOT NULL DEFAULT 60,
                is_active INTEGER DEFAULT 1,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # 2. API Keys
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                key_hash TEXT NOT NULL UNIQUE,
                key_prefix TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                credits_remaining INTEGER DEFAULT 1000,
                tokens_saved_total INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                expires_at TEXT,
                last_used_at TEXT
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id);")

            # 3. Usage Logs
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS usage_logs (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                api_key_id TEXT REFERENCES api_keys(id) ON DELETE SET NULL,
                endpoint_accessed TEXT NOT NULL,
                tokens_consumed INTEGER DEFAULT 0,
                processing_time_ms REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_usage_logs_tenant_date ON usage_logs(tenant_id, created_at);")
            conn.commit()

    async def bootstrap_admin_key(self, admin_key: str) -> None:
        def _bootstrap():
            key_hash = hashlib.sha256(admin_key.encode()).hexdigest()
            key_prefix = admin_key[:15]
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Check if dev key already bootstrapped
                cursor.execute("SELECT id FROM api_keys WHERE key_hash = ?", (key_hash,))
                if cursor.fetchone():
                    return
                
                # Create a default developer tenant
                tenant_id = str(uuid.uuid4())
                cursor.execute(
                    "INSERT INTO tenants (id, name, plan_tier, rate_limit_per_minute) VALUES (?, ?, ?, ?)",
                    (tenant_id, "Bootstrap Administrator", "enterprise", 100)
                )
                
                # Insert key mapping
                key_id = str(uuid.uuid4())
                cursor.execute(
                    "INSERT INTO api_keys (id, tenant_id, key_hash, key_prefix, status) VALUES (?, ?, ?, ?, ?)",
                    (key_id, tenant_id, key_hash, key_prefix, "active")
                )
                conn.commit()
                logger.info("Bootstrapped rotated administrator token inside SQLite.")

        await asyncio.to_thread(_bootstrap)

    async def get_api_key(self, key_hash: str) -> Optional[Dict[str, Any]]:
        def _query():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT k.id as key_id, k.key_hash, k.key_prefix, k.status, 
                           k.credits_remaining, k.tokens_saved_total,
                           t.id as tenant_id, t.name as tenant_name, t.plan_tier, 
                           t.rate_limit_per_minute as rate_limit, t.is_active
                    FROM api_keys k
                    JOIN tenants t ON k.tenant_id = t.id
                    WHERE k.key_hash = ? AND k.status = 'active' AND t.is_active = 1
                """, (key_hash,))
                row = cursor.fetchone()
                if not row:
                    return None
                
                # Update last used
                cursor.execute(
                    "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), row["key_id"])
                )
                conn.commit()
                
                return {
                    "key": row["key_hash"],  # For backward compatibility with server state
                    "id": row["key_id"],
                    "key_prefix": row["key_prefix"],
                    "name": row["tenant_name"],
                    "namespace": f"tenant_{row['tenant_id'][:8]}",  # Isolates namespace per tenant id
                    "rate_limit": row["rate_limit"],
                    "role": "admin" if row["plan_tier"] == "enterprise" else "client",
                    "tenant_id": row["tenant_id"],
                    "credits_remaining": row["credits_remaining"],
                    "tokens_saved_total": row["tokens_saved_total"]
                }
        return await asyncio.to_thread(_query)

    async def create_api_key(self, name: str, namespace: str, rate_limit: int, role: str) -> Dict[str, Any]:
        def _insert():
            raw_token = "ses_" + hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()[:24]
            key_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            key_prefix = raw_token[:15]
            
            tenant_id = str(uuid.uuid4())
            key_id = str(uuid.uuid4())
            
            plan = "enterprise" if role == "admin" else "pro"
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO tenants (id, name, plan_tier, rate_limit_per_minute) VALUES (?, ?, ?, ?)",
                    (tenant_id, name, plan, rate_limit)
                )
                cursor.execute(
                    "INSERT INTO api_keys (id, tenant_id, key_hash, key_prefix, status) VALUES (?, ?, ?, ?, ?)",
                    (key_id, tenant_id, key_hash, key_prefix, "active")
                )
                conn.commit()
                
                return {
                    "key": raw_token,  # Return raw token to display to user once
                    "key_details": {
                        "key": key_hash,
                        "id": key_id,
                        "tenant_id": tenant_id,
                        "key_prefix": key_prefix,
                        "name": name,
                        "namespace": f"tenant_{tenant_id[:8]}",
                        "rate_limit": rate_limit,
                        "role": role,
                        "created_at": int(datetime.now(timezone.utc).timestamp())
                    }
                }
        return await asyncio.to_thread(_insert)

    async def revoke_api_key(self, key_token_or_prefix: str) -> bool:
        def _delete():
            # If the user passed raw key, calculate hash, else match prefix
            key_hash = hashlib.sha256(key_token_or_prefix.encode()).hexdigest()
            
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE api_keys SET status = 'revoked' WHERE key_hash = ? OR key_prefix = ?",
                    (key_hash, key_token_or_prefix)
                )
                conn.commit()
                return cursor.rowcount > 0
        return await asyncio.to_thread(_delete)

    async def list_api_keys(self) -> List[Dict[str, Any]]:
        def _list():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT k.id as key_id, k.key_prefix, k.status, k.created_at,
                           t.id as tenant_id, t.name as tenant_name, t.plan_tier, t.rate_limit_per_minute
                    FROM api_keys k
                    JOIN tenants t ON k.tenant_id = t.id
                    WHERE k.status = 'active'
                """)
                rows = cursor.fetchall()
                keys = []
                for row in rows:
                    created_epoch = int(datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S").timestamp()) if " " in row["created_at"] else int(datetime.now(timezone.utc).timestamp())
                    keys.append({
                        "key": row["key_prefix"] + "...",  # Do not return full hashes/keys in listing
                        "name": row["tenant_name"],
                        "namespace": f"tenant_{row['tenant_id'][:8]}",
                        "rate_limit": row["rate_limit_per_minute"],
                        "role": "admin" if row["plan_tier"] == "enterprise" else "client",
                        "created_at": created_epoch
                    })
                return keys
        return await asyncio.to_thread(_list)

    async def log_usage(self, tenant_id: str, api_key_id: Optional[str], endpoint: str, tokens: int, latency_ms: float) -> None:
        def _log():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO usage_logs (id, tenant_id, api_key_id, endpoint_accessed, tokens_consumed, processing_time_ms) VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), tenant_id, api_key_id, endpoint, tokens, latency_ms)
                )
                conn.commit()
        await asyncio.to_thread(_log)

    async def update_credits(self, key_hash: str, credits_deducted: int, tokens_saved: int) -> Dict[str, Any]:
        def _update():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE api_keys SET credits_remaining = credits_remaining - ?, tokens_saved_total = tokens_saved_total + ? WHERE key_hash = ? RETURNING credits_remaining, tokens_saved_total",
                    (credits_deducted, tokens_saved, key_hash)
                )
                row = cursor.fetchone()
                conn.commit()
                if not row:
                    raise ValueError("API Key not found")
                return {"credits_remaining": row["credits_remaining"], "tokens_saved_total": row["tokens_saved_total"]}
        return await asyncio.to_thread(_update)

    async def get_analytics(self) -> Dict[str, Any]:
        def _analytics():
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Global metrics
                cursor.execute("SELECT COUNT(*) FROM usage_logs")
                total_reqs = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM usage_logs WHERE endpoint_accessed LIKE '%search%'")
                total_searches = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM usage_logs WHERE endpoint_accessed LIKE '%ingest%'")
                total_ingestions = cursor.fetchone()[0]
                
                cursor.execute("SELECT AVG(processing_time_ms) FROM usage_logs")
                avg_latency = cursor.fetchone()[0] or 0.0
                
                # Recent logs
                cursor.execute("""
                    SELECT u.created_at, t.name as tenant_name, u.endpoint_accessed, u.processing_time_ms
                    FROM usage_logs u
                    JOIN tenants t ON u.tenant_id = t.id
                    ORDER BY u.created_at DESC LIMIT 50
                """)
                logs = []
                for row in cursor.fetchall():
                    logs.append({
                        "timestamp": row["created_at"],
                        "key_name": row["tenant_name"],
                        "endpoint": row["endpoint_accessed"],
                        "namespace": "global",
                        "status_code": 200,
                        "latency_ms": row["processing_time_ms"]
                    })
                
                # Keys performance
                cursor.execute("""
                    SELECT t.name, t.plan_tier, COUNT(u.id) as calls, AVG(u.processing_time_ms) as avg_lat
                    FROM usage_logs u
                    JOIN tenants t ON u.tenant_id = t.id
                    GROUP BY t.id
                """)
                keys_info = []
                for row in cursor.fetchall():
                    keys_info.append({
                        "name": row["name"],
                        "namespace": "global",
                        "role": "admin" if row["plan_tier"] == "enterprise" else "client",
                        "total_calls": row["calls"],
                        "avg_latency_ms": row["avg_lat"]
                    })
                
                return {
                    "total_requests": total_reqs,
                    "total_errors": 0,
                    "total_searches": total_searches,
                    "total_ingestions": total_ingestions,
                    "average_latency_ms": avg_latency,
                    "keys_performance": keys_info,
                    "recent_logs": logs
                }
        return await asyncio.to_thread(_analytics)


# Concrete PostgreSQL Adapter using asyncpg (High performance client)
class PostgresDatabaseAdapter(DatabaseAdapter):
    def __init__(self):
        self.pool = None

    async def connect(self) -> None:
        import asyncpg
        self.pool = await asyncpg.create_pool(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            min_size=2,
            max_size=10
        )
        await self._run_migrations()
        logger.info(f"🐘 PostgreSQL active on: postgres://{POSTGRES_USER}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}")

    async def _run_migrations(self) -> None:
        async with self.pool.acquire() as conn:
            # Create extension
            await conn.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
            
            # Create tables
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS tenants (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                name VARCHAR(255) NOT NULL,
                plan_tier VARCHAR(50) DEFAULT 'developer',
                rate_limit_per_minute INT NOT NULL DEFAULT 60,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            """)
            
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                key_hash VARCHAR(255) NOT NULL UNIQUE,
                key_prefix VARCHAR(15) NOT NULL,
                status VARCHAR(20) DEFAULT 'active',
                credits_remaining INT DEFAULT 1000,
                tokens_saved_total INT DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                expires_at TIMESTAMPTZ,
                last_used_at TIMESTAMPTZ
            );
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_tenant ON api_keys(tenant_id);")

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS usage_logs (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                api_key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL,
                endpoint_accessed VARCHAR(255) NOT NULL,
                tokens_consumed INT DEFAULT 0,
                processing_time_ms FLOAT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_logs_tenant_date ON usage_logs(tenant_id, created_at);")

    async def bootstrap_admin_key(self, admin_key: str) -> None:
        key_hash = hashlib.sha256(admin_key.encode()).hexdigest()
        key_prefix = admin_key[:15]
        
        async with self.pool.acquire() as conn:
            existing = await conn.fetchval("SELECT id FROM api_keys WHERE key_hash = $1", key_hash)
            if existing:
                return
            
            async with conn.transaction():
                tenant_id = await conn.fetchval(
                    "INSERT INTO tenants (name, plan_tier, rate_limit_per_minute) VALUES ($1, $2, $3) RETURNING id",
                    "Bootstrap Administrator", "enterprise", 100
                )
                await conn.execute(
                    "INSERT INTO api_keys (tenant_id, key_hash, key_prefix, status) VALUES ($1, $2, $3, $4)",
                    tenant_id, key_hash, key_prefix, "active"
                )
                logger.info("Bootstrapped rotated administrator token inside PostgreSQL.")

    async def get_api_key(self, key_hash: str) -> Optional[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT k.id as key_id, k.key_hash, k.key_prefix, k.status, 
                       k.credits_remaining, k.tokens_saved_total,
                       t.id as tenant_id, t.name as tenant_name, t.plan_tier, 
                       t.rate_limit_per_minute as rate_limit, t.is_active
                FROM api_keys k
                JOIN tenants t ON k.tenant_id = t.id
                WHERE k.key_hash = $1 AND k.status = 'active' AND t.is_active = TRUE
            """, key_hash)
            
            if not row:
                return None
                
            # Update last used
            await conn.execute(
                "UPDATE api_keys SET last_used_at = NOW() WHERE id = $1",
                row["key_id"]
            )
            
            return {
                "key": row["key_hash"],
                "id": str(row["key_id"]),
                "key_prefix": row["key_prefix"],
                "name": row["tenant_name"],
                "namespace": f"tenant_{str(row['tenant_id'])[:8]}",
                "rate_limit": row["rate_limit"],
                "role": "admin" if row["plan_tier"] == "enterprise" else "client",
                "tenant_id": str(row["tenant_id"]),
                "credits_remaining": row["credits_remaining"],
                "tokens_saved_total": row["tokens_saved_total"]
            }

    async def create_api_key(self, name: str, namespace: str, rate_limit: int, role: str) -> Dict[str, Any]:
        raw_token = "ses_" + hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()[:24]
        key_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        key_prefix = raw_token[:15]
        
        plan = "enterprise" if role == "admin" else "pro"
        
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                tenant_id = await conn.fetchval(
                    "INSERT INTO tenants (name, plan_tier, rate_limit_per_minute) VALUES ($1, $2, $3) RETURNING id",
                    name, plan, rate_limit
                )
                key_id = await conn.fetchval(
                    "INSERT INTO api_keys (tenant_id, key_hash, key_prefix, status) VALUES ($1, $2, $3, $4) RETURNING id",
                    tenant_id, key_hash, key_prefix, "active"
                )
                
                return {
                    "key": raw_token,
                    "key_details": {
                        "key": key_hash,
                        "id": str(key_id),
                        "tenant_id": str(tenant_id),
                        "key_prefix": key_prefix,
                        "name": name,
                        "namespace": f"tenant_{str(tenant_id)[:8]}",
                        "rate_limit": rate_limit,
                        "role": role,
                        "created_at": int(datetime.now(timezone.utc).timestamp())
                    }
                }

    async def revoke_api_key(self, key_token_or_prefix: str) -> bool:
        key_hash = hashlib.sha256(key_token_or_prefix.encode()).hexdigest()
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE api_keys SET status = 'revoked' WHERE key_hash = $1 OR key_prefix = $2",
                key_hash, key_token_or_prefix
            )
            return "UPDATE 0" not in result

    async def list_api_keys(self) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT k.id as key_id, k.key_prefix, k.status, k.created_at,
                       t.id as tenant_id, t.name as tenant_name, t.plan_tier, t.rate_limit_per_minute
                FROM api_keys k
                JOIN tenants t ON k.tenant_id = t.id
                WHERE k.status = 'active'
            """)
            keys = []
            for row in rows:
                keys.append({
                    "key": row["key_prefix"] + "...",
                    "name": row["tenant_name"],
                    "namespace": f"tenant_{str(row['tenant_id'])[:8]}",
                    "rate_limit": row["rate_limit_per_minute"],
                    "role": "admin" if row["plan_tier"] == "enterprise" else "client",
                    "created_at": int(row["created_at"].timestamp())
                })
            return keys

    async def log_usage(self, tenant_id: str, api_key_id: Optional[str], endpoint: str, tokens: int, latency_ms: float) -> None:
        async with self.pool.acquire() as conn:
            # Convert str to UUID
            t_uuid = uuid.UUID(tenant_id)
            k_uuid = uuid.UUID(api_key_id) if api_key_id else None
            await conn.execute(
                "INSERT INTO usage_logs (tenant_id, api_key_id, endpoint_accessed, tokens_consumed, processing_time_ms) VALUES ($1, $2, $3, $4, $5)",
                t_uuid, k_uuid, endpoint, tokens, latency_ms
            )

    async def update_credits(self, key_hash: str, credits_deducted: int, tokens_saved: int) -> Dict[str, Any]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "UPDATE api_keys SET credits_remaining = credits_remaining - $1, tokens_saved_total = tokens_saved_total + $2 WHERE key_hash = $3 RETURNING credits_remaining, tokens_saved_total",
                credits_deducted, tokens_saved, key_hash
            )
            if not row:
                raise ValueError("API Key not found")
            return {"credits_remaining": row["credits_remaining"], "tokens_saved_total": row["tokens_saved_total"]}

    async def get_analytics(self) -> Dict[str, Any]:
        async with self.pool.acquire() as conn:
            total_reqs = await conn.fetchval("SELECT COUNT(*) FROM usage_logs") or 0
            total_searches = await conn.fetchval("SELECT COUNT(*) FROM usage_logs WHERE endpoint_accessed LIKE '%search%'") or 0
            total_ingestions = await conn.fetchval("SELECT COUNT(*) FROM usage_logs WHERE endpoint_accessed LIKE '%ingest%'") or 0
            avg_latency = await conn.fetchval("SELECT AVG(processing_time_ms) FROM usage_logs") or 0.0
            
            # Recent logs
            rows_logs = await conn.fetch("""
                SELECT u.created_at, t.name as tenant_name, u.endpoint_accessed, u.processing_time_ms
                FROM usage_logs u
                JOIN tenants t ON u.tenant_id = t.id
                ORDER BY u.created_at DESC LIMIT 50
            """)
            logs = []
            for row in rows_logs:
                logs.append({
                    "timestamp": row["created_at"].isoformat(),
                    "key_name": row["tenant_name"],
                    "endpoint": row["endpoint_accessed"],
                    "namespace": "global",
                    "status_code": 200,
                    "latency_ms": row["processing_time_ms"]
                })
                
            # Keys performance
            rows_perf = await conn.fetch("""
                SELECT t.name, t.plan_tier, COUNT(u.id) as calls, AVG(u.processing_time_ms) as avg_lat
                FROM usage_logs u
                JOIN tenants t ON u.tenant_id = t.id
                GROUP BY t.id, t.name, t.plan_tier
            """)
            keys_info = []
            for row in rows_perf:
                keys_info.append({
                    "name": row["name"],
                    "namespace": "global",
                    "role": "admin" if row["plan_tier"] == "enterprise" else "client",
                    "total_calls": row["calls"],
                    "avg_latency_ms": row["avg_lat"]
                })
                
            return {
                "total_requests": total_reqs,
                "total_errors": 0,
                "total_searches": total_searches,
                "total_ingestions": total_ingestions,
                "average_latency_ms": float(avg_latency),
                "keys_performance": keys_info,
                "recent_logs": logs
            }


# Factory Method to instantiate the appropriate Database Adapter
_db_adapter: Optional[DatabaseAdapter] = None

def get_database_adapter() -> DatabaseAdapter:
    global _db_adapter
    if _db_adapter is None:
        if POSTGRES_ENABLED:
            try:
                adapter = PostgresDatabaseAdapter()
                # Run synchronous validation of import / initialization
                import asyncpg
                _db_adapter = adapter
            except Exception as e:
                logger.warning(f"⚠️ Failed to import asyncpg or setup postgres: {e}. Defaulting to SQLite.")
                _db_adapter = SQLiteDatabaseAdapter()
        else:
            _db_adapter = SQLiteDatabaseAdapter()
            
    return _db_adapter
