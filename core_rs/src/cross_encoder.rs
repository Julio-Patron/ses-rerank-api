use std::borrow::Cow;
use std::path::Path;
use std::sync::Mutex;

use ndarray::Array2;
use ort::session::builder::GraphOptimizationLevel;
use ort::session::{Session, SessionInputValue};
use ort::value::Tensor;
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;

/// ONNX cross-encoder that scores (query, document) pairs.
///
/// Tokenization happens in Python; this type owns the ONNX Runtime session and
/// releases the GIL while inference runs, so `asyncio.to_thread` callers do not
/// stall the event loop.
#[pyclass]
pub struct CrossEncoderEngine {
    session: Mutex<Session>,
    uses_token_type_ids: bool,
    output_name: String,
}

#[pymethods]
impl CrossEncoderEngine {
    #[new]
    #[pyo3(signature = (model_dir, model_file = "model.onnx", intra_threads = None))]
    pub fn new(model_dir: &str, model_file: &str, intra_threads: Option<usize>) -> PyResult<Self> {
        let model_path = Path::new(model_dir).join(model_file);
        let threads = intra_threads.unwrap_or_else(num_cpus::get).max(1);

        let session = Session::builder()
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to create builder: {e}")))?
            .with_optimization_level(GraphOptimizationLevel::Level3)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to set opt level: {e}")))?
            .with_intra_threads(threads)
            .map_err(|e| PyRuntimeError::new_err(format!("Failed to set threads: {e}")))?
            .commit_from_file(&model_path)
            .map_err(|e| {
                PyRuntimeError::new_err(format!(
                    "Failed to load model {}: {e}",
                    model_path.display()
                ))
            })?;

        let uses_token_type_ids = session
            .inputs()
            .iter()
            .any(|input| input.name() == "token_type_ids");
        let output_name = session
            .outputs()
            .iter()
            .map(|output| output.name())
            .find(|name| *name == "logits")
            .or_else(|| session.outputs().first().map(|output| output.name()))
            .ok_or_else(|| PyRuntimeError::new_err("Model declares no outputs"))?
            .to_string();

        Ok(CrossEncoderEngine {
            session: Mutex::new(session),
            uses_token_type_ids,
            output_name,
        })
    }

    /// Scores every pair and returns `(row_index, logit)` sorted by descending
    /// logit, truncated to `top_k`. `token_type_ids` may be `None` for models
    /// (e.g. XLM-RoBERTa) whose tokenizer does not produce them.
    #[pyo3(signature = (input_ids, attention_mask, token_type_ids, top_k))]
    pub fn rerank_batch<'py>(
        &self,
        py: Python<'py>,
        input_ids: numpy::PyReadonlyArray2<'py, i64>,
        attention_mask: numpy::PyReadonlyArray2<'py, i64>,
        token_type_ids: Option<numpy::PyReadonlyArray2<'py, i64>>,
        top_k: usize,
    ) -> PyResult<Vec<(usize, f32)>> {
        let input_ids = input_ids.as_array().to_owned();
        let attention_mask = attention_mask.as_array().to_owned();
        if input_ids.is_empty() {
            return Ok(Vec::new());
        }
        if attention_mask.shape() != input_ids.shape() {
            return Err(PyValueError::new_err(
                "attention_mask must have the same shape as input_ids",
            ));
        }

        let token_type_ids = if self.uses_token_type_ids {
            let ids = match token_type_ids {
                Some(ids) => ids.as_array().to_owned(),
                None => Array2::zeros(input_ids.raw_dim()),
            };
            if ids.shape() != input_ids.shape() {
                return Err(PyValueError::new_err(
                    "token_type_ids must have the same shape as input_ids",
                ));
            }
            Some(ids)
        } else {
            None
        };

        let logits = py
            .detach(|| self.score(input_ids, attention_mask, token_type_ids))
            .map_err(PyRuntimeError::new_err)?;

        let mut scores: Vec<(usize, f32)> = logits.into_iter().enumerate().collect();
        scores.sort_by(|a, b| b.1.total_cmp(&a.1));
        scores.truncate(top_k);
        Ok(scores)
    }
}

impl CrossEncoderEngine {
    fn score(
        &self,
        input_ids: Array2<i64>,
        attention_mask: Array2<i64>,
        token_type_ids: Option<Array2<i64>>,
    ) -> Result<Vec<f32>, String> {
        let batch_size = input_ids.nrows();
        let tensor = |name: &str, array: Array2<i64>| {
            Tensor::from_array(array)
                .map(SessionInputValue::from)
                .map_err(|e| format!("Failed to build {name} tensor: {e}"))
        };

        let mut inputs: Vec<(Cow<'static, str>, SessionInputValue<'static>)> = vec![
            ("input_ids".into(), tensor("input_ids", input_ids)?),
            (
                "attention_mask".into(),
                tensor("attention_mask", attention_mask)?,
            ),
        ];
        if let Some(ids) = token_type_ids {
            inputs.push(("token_type_ids".into(), tensor("token_type_ids", ids)?));
        }

        let mut session = self
            .session
            .lock()
            .map_err(|_| "Inference session lock poisoned".to_string())?;
        let outputs = session
            .run(inputs)
            .map_err(|e| format!("Inference failed: {e}"))?;
        let (_, logits) = outputs[self.output_name.as_str()]
            .try_extract_tensor::<f32>()
            .map_err(|e| format!("Failed to read {} output: {e}", self.output_name))?;

        if logits.len() < batch_size || !logits.len().is_multiple_of(batch_size) {
            return Err(format!(
                "Unexpected output size {} for batch of {batch_size}",
                logits.len()
            ));
        }
        // Single-logit heads give one score per row; for multi-label heads the
        // last column is the "relevant" class.
        let labels = logits.len() / batch_size;
        Ok((0..batch_size)
            .map(|row| logits[row * labels + labels - 1])
            .collect())
    }
}
