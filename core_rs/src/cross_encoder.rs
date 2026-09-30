use pyo3::prelude::*;
use pyo3::exceptions::PyRuntimeError;
use std::path::Path;
use std::sync::{Arc, Mutex};
use ort::session::{Session, builder::GraphOptimizationLevel};
use ort::value::Tensor;
use ndarray::Array2;

#[pyclass]
pub struct CrossEncoderEngine {
    session: Arc<Mutex<Session>>,
}

#[pymethods]
impl CrossEncoderEngine {
    #[new]
    pub fn new(model_dir: &str) -> PyResult<Self> {
        let model_path = Path::new(model_dir).join("model.onnx");
        
        let session = Session::builder()
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to create builder: {}", e)))?
            .with_optimization_level(GraphOptimizationLevel::Level3)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to set opt level: {}", e)))?
            // Enable internal multithreading for batch inference
            .with_intra_threads(num_cpus::get())
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to set threads: {}", e)))?
            .commit_from_file(model_path)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to load model: {}", e)))?;

        Ok(CrossEncoderEngine {
            session: Arc::new(Mutex::new(session)),
        })
    }

    /// Evaluates a pre-tokenized batch of query-document pairs.
    pub fn rerank_batch(
        &self,
        input_ids: Vec<Vec<i64>>,
        attention_mask: Vec<Vec<i64>>,
        top_k: usize,
    ) -> PyResult<Vec<(usize, f32)>> {
        if input_ids.is_empty() {
            return Ok(Vec::new());
        }

        let batch_size = input_ids.len();
        let seq_len = input_ids[0].len();

        let mut all_input_ids: Vec<i64> = Vec::with_capacity(batch_size * seq_len);
        let mut all_attention_masks: Vec<i64> = Vec::with_capacity(batch_size * seq_len);

        for i in 0..batch_size {
            if input_ids[i].len() != seq_len || attention_mask[i].len() != seq_len {
                return Err(PyRuntimeError::new_err("All inputs in the batch must have the same sequence length (padded)."));
            }
            all_input_ids.extend(&input_ids[i]);
            all_attention_masks.extend(&attention_mask[i]);
        }

        let input_ids_array = Array2::from_shape_vec((batch_size, seq_len), all_input_ids).unwrap();
        let attention_mask_array = Array2::from_shape_vec((batch_size, seq_len), all_attention_masks).unwrap();

        let input_tensor = Tensor::from_array(input_ids_array).unwrap();
        let mask_tensor = Tensor::from_array(attention_mask_array).unwrap();

        let inputs = ort::inputs! {
            "input_ids" => input_tensor,
            "attention_mask" => mask_tensor,
        };

        // Lock session to fulfill mutable borrow requirements
        let mut session_lock = self.session.lock().unwrap();
        let outputs = match session_lock.run(inputs) {
            Ok(o) => o,
            Err(e) => return Err(PyRuntimeError::new_err(format!("Inference failed: {}", e))),
        };

        let logits_tensor = outputs["logits"].try_extract_tensor::<f32>().unwrap();
        let logits_slice = logits_tensor.1;

        let mut scores: Vec<(usize, f32)> = (0..batch_size)
            .map(|i| {
                let score = logits_slice[i];
                (i, score)
            })
            .collect();

        scores.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        scores.truncate(top_k);

        Ok(scores)
    }
}
