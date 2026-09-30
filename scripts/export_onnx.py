import os
import sys

try:
    from optimum.onnxruntime import ORTModelForSequenceClassification
    from transformers import AutoTokenizer
except ImportError:
    print("Please install optimum and transformers: pip install optimum[onnxruntime] transformers")
    sys.exit(1)

def export_model():
    model_id = "BAAI/bge-reranker-base"
    save_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "model_onnx")
    os.makedirs(save_dir, exist_ok=True)

    print(f"Downloading and exporting '{model_id}' to ONNX...")
    print("This might take a few minutes depending on your internet connection...")

    # Load model and export to ONNX
    # Cross-Encoders use SequenceClassification architecture
    model = ORTModelForSequenceClassification.from_pretrained(model_id, export=True)
    tokenizer = AutoTokenizer.from_pretrained(model_id)

    # Save to the target directory
    model.save_pretrained(save_dir)
    tokenizer.save_pretrained(save_dir)

    print(f"\n✅ Export complete! Model and tokenizer saved to: {save_dir}")

if __name__ == "__main__":
    export_model()
