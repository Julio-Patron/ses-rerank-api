import asyncio
import json
import logging
import os
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("ses_worker")

# Load environment variables (same as gateway)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

import redis.asyncio as redis
from ses.services.reranker import RerankerService

async def main():
    logger.info("Starting SES Rerank Worker...")
    
    # Initialize the Reranker Engine
    model_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "model_onnx"))
    try:
        reranker_service = RerankerService(model_dir=model_dir)
        logger.info("Initialized ONNX CrossEncoder Engine.")
    except Exception as e:
        logger.error(f"Failed to initialize Reranker Engine: {e}")
        sys.exit(1)
        
    # Connect to Redis
    try:
        redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            decode_responses=True
        )
        # Ping to check connection
        await redis_client.ping()
        logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        sys.exit(1)
        
    logger.info("Worker is ready and waiting for tasks on 'ses_rerank_queue'...")
    
    while True:
        try:
            # BRPOP blocks until a task is available in the queue
            result = await redis_client.brpop("ses_rerank_queue", timeout=0)
            if not result:
                continue
                
            queue_name, task_json = result
            task_data = json.loads(task_json)
            task_id = task_data.get("task_id")
            
            if not task_id:
                logger.error("Received task without task_id")
                continue
                
            logger.info(f"Processing task {task_id}")
            
            try:
                # Perform the heavy computation (which runs in a thread pool via RerankerService)
                rerank_result = await reranker_service.rerank(
                    query=task_data.get("query"),
                    documents=task_data.get("documents"),
                    top_n=task_data.get("top_n", 5),
                    jsonlogic_filter=task_data.get("jsonlogic_filter")
                )
                
                # Push the result back to the specific task queue
                response_key = f"ses_rerank_result:{task_id}"
                
                # Use a pipeline to push and set expiry in one atomic operation
                async with redis_client.pipeline(transaction=True) as pipe:
                    pipe.rpush(response_key, json.dumps(rerank_result))
                    pipe.expire(response_key, 60) # Expire the result after 60s to avoid memory leaks if gateway died
                    await pipe.execute()
                    
                logger.info(f"Task {task_id} completed successfully")
                
            except Exception as inner_e:
                logger.error(f"Error processing task {task_id}: {inner_e}")
                # Send error back to gateway
                error_result = {"error": str(inner_e)}
                response_key = f"ses_rerank_result:{task_id}"
                async with redis_client.pipeline(transaction=True) as pipe:
                    pipe.rpush(response_key, json.dumps(error_result))
                    pipe.expire(response_key, 60)
                    await pipe.execute()
                    
        except Exception as e:
            logger.error(f"Worker loop error: {e}")
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
