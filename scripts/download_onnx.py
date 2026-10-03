import os
from huggingface_hub import hf_hub_download

def download_model():
    print("Downloading ONNX model from Hugging Face...")
    os.makedirs("model_onnx", exist_ok=True)
    
    # We will use cross-encoder/ms-marco-MiniLM-L-6-v2 ONNX version from a reliable repo
    # The ONNX version of cross-encoder/ms-marco-MiniLM-L-6-v2 is available at BAAI/bge-reranker-base or similar.
    # Actually, a common one is "Xenova/ms-marco-MiniLM-L-6-v2" which contains ONNX files.
    # Let's try to download model.onnx and tokenizer.json from Xenova/ms-marco-MiniLM-L-6-v2
    
    repo_id = "Xenova/ms-marco-MiniLM-L-6-v2"
    
    onnx_file = hf_hub_download(repo_id=repo_id, filename="onnx/model.onnx")
    tokenizer_file = hf_hub_download(repo_id=repo_id, filename="tokenizer.json")
    tokenizer_config = hf_hub_download(repo_id=repo_id, filename="tokenizer_config.json")
    
    import shutil
    shutil.copy(onnx_file, "model_onnx/model.onnx")
    shutil.copy(tokenizer_file, "model_onnx/tokenizer.json")
    shutil.copy(tokenizer_config, "model_onnx/tokenizer_config.json")
    
    print("Downloaded ONNX model successfully to model_onnx/")

if __name__ == "__main__":
    download_model()
