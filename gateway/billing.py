"""Credit-pack catalog. Packs are identified by Stripe Price IDs, not amounts."""

import os
from typing import Any, Dict, Optional

_PACK_NAMES = ("developer", "growth")
_DEFAULT_CREDITS = {"developer": 10_000, "growth": 100_000}
_DEFAULT_RATE_LIMITS = {"developer": 60, "growth": 500}


def credit_pack(name: str) -> Optional[Dict[str, Any]]:
    """Return the server-side pack for a name, or None if it is not configured."""
    if name not in _PACK_NAMES:
        return None
    price_id = os.getenv(f"STRIPE_PRICE_{name.upper()}", "").strip()
    if not price_id:
        return None
    try:
        credits = int(os.getenv(f"STRIPE_CREDITS_{name.upper()}", str(_DEFAULT_CREDITS[name])))
        rate_limit = int(
            os.getenv(f"STRIPE_RATE_LIMIT_{name.upper()}", str(_DEFAULT_RATE_LIMITS[name]))
        )
    except ValueError:
        return None
    if credits <= 0 or rate_limit <= 0:
        return None
    return {
        "name": name,
        "price_id": price_id,
        "credits": credits,
        "rate_limit": rate_limit,
    }


def pack_for_price(price_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """Map a paid Stripe Price ID back to its server-side credit pack."""
    if not price_id:
        return None
    for name in _PACK_NAMES:
        pack = credit_pack(name)
        if pack and pack["price_id"] == price_id:
            return pack
    return None
