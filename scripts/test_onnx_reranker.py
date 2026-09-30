import asyncio
import os
import sys

# Add root path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ses.services.reranker import RerankerService

async def main():
    model_dir = os.path.join(os.path.dirname(__file__), "..", "model_onnx")
    print(f"Loading from: {model_dir}")
    
    service = RerankerService(model_dir)
    print("Service initialized!")
    
    query = "What is the capital of France?"
    documents = [
        "The capital of France is Paris.",
        "Berlin is the capital of Germany.",
        "France is a country in Western Europe.",
        "Paris is a beautiful city."
    ]
    
    print("Reranking...")
    result = await service.rerank(query, documents, top_n=2)
    
    print("Results:")
    for r in result["results"]:
        print(f"- [Score: {r['relevance_score']:.4f}] {r['document']}")
        
    print("\nMeta:")
    print(result["meta"])

if __name__ == "__main__":
    asyncio.run(main())
