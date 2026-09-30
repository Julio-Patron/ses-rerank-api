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

    pub fn rerank_batch<'py>(
        &self,
        py: Python<'py>,
        input_ids: numpy::PyReadonlyArray2<'py, i64>,
        attention_mask: numpy::PyReadonlyArray2<'py, i64>,
        top_k: usize,
    ) -> PyResult<Vec<(usize, f32)>> {
        let input_ids_view = input_ids.as_array();
        let attention_mask_view = attention_mask.as_array();

        if input_ids_view.is_empty() {
            return Ok(Vec::new());
        }

        let batch_size = input_ids_view.shape()[0];

        // Tensor::from_array can take owned Array. We can .to_owned() which is a single contiguous allocation,
        // vastly faster than a loop appending to a Vec!
        let input_tensor = Tensor::from_array(input_ids_view.to_owned()).unwrap();
        let mask_tensor = Tensor::from_array(attention_mask_view.to_owned()).unwrap();

        let inputs = ort::inputs! {
            "input_ids" => input_tensor,
            "attention_mask" => mask_tensor,
        };

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
