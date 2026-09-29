#[cfg(feature = "python")]
use numpy::{PyReadonlyArray1, PyReadonlyArray2, PyUntypedArrayMethods};
#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;

pub fn cosine_similarity_scores_from_slices<'a>(
    query_vector: &[f32],
    document_vectors: impl IntoIterator<Item = &'a [f32]>,
    top_k: usize,
    threshold: Option<f32>,
) -> Result<Vec<(usize, f32)>, String> {
    if query_vector.is_empty() {
        return Err("query_vector must not be empty".to_string());
    }
    if query_vector.iter().any(|value| !value.is_finite()) {
        return Err("query_vector must contain only finite values".to_string());
    }
    if threshold.is_some_and(|value| !value.is_finite()) {
        return Err("threshold must be finite".to_string());
    }
    if top_k == 0 {
        return Ok(Vec::new());
    }

    let expected_dimensions = query_vector.len();
    let query_norm = query_vector
        .iter()
        .map(|value| value * value)
        .sum::<f32>()
        .sqrt();
    let mut scores = Vec::new();

    for (index, document) in document_vectors.into_iter().enumerate() {
        if document.len() != expected_dimensions {
            return Err(format!(
                "document vector {index} has {} dimensions; expected {expected_dimensions}",
                document.len()
            ));
        }
        if document.iter().any(|value| !value.is_finite()) {
            return Err(format!(
                "document vector {index} must contain only finite values"
            ));
        }

        let (dot_product, document_squared_norm) = query_vector
            .iter()
            .zip(document)
            .fold((0.0_f32, 0.0_f32), |(dot, norm), (query, value)| {
                (dot + query * value, norm + value * value)
            });
        let document_norm = document_squared_norm.sqrt();
        let score = if query_norm > 0.0 && document_norm > 0.0 {
            dot_product / (query_norm * document_norm)
        } else {
            0.0
        };

        if threshold.is_none_or(|minimum| score >= minimum) {
            scores.push((index, score));
        }
    }

    scores.sort_by(|left, right| right.1.total_cmp(&left.1));
    scores.truncate(top_k);
    Ok(scores)
}

pub fn cosine_similarity_scores(
    query_vector: &[f32],
    document_vectors: &[Vec<f32>],
    top_k: usize,
    threshold: Option<f32>,
) -> Result<Vec<(usize, f32)>, String> {
    cosine_similarity_scores_from_slices(
        query_vector,
        document_vectors.iter().map(Vec::as_slice),
        top_k,
        threshold,
    )
}

#[cfg(feature = "python")]
fn as_python_value_error(error: String) -> PyErr {
    PyValueError::new_err(error)
}

/// Calcula la similitud de coseno entre un vector de consulta y una matriz de documentos.
/// Retorna los \u00edndices y scores ordenados de mayor a menor relevancia.
#[cfg(feature = "python")]
#[pyfunction]
fn cosine_similarity_search(
    query_vector: Vec<f32>,
    document_vectors: Vec<Vec<f32>>,
    top_k: usize,
) -> PyResult<Vec<(usize, f32)>> {
    cosine_similarity_scores(&query_vector, &document_vectors, top_k, None)
        .map_err(as_python_value_error)
}

/// Ruta sin copias para los ndarrays contiguos usados por el motor RAG.
#[cfg(feature = "python")]
#[pyfunction]
fn cosine_similarity_search_numpy(
    query_vector: PyReadonlyArray1<'_, f32>,
    document_vectors: PyReadonlyArray2<'_, f32>,
    top_k: usize,
) -> PyResult<Vec<(usize, f32)>> {
    let query = query_vector
        .as_slice()
        .map_err(|_| PyValueError::new_err("query_vector must be C-contiguous"))?;
    let shape = document_vectors.shape();
    if shape[0] == 0 {
        return cosine_similarity_scores_from_slices(
            query,
            std::iter::empty::<&[f32]>(),
            top_k,
            None,
        )
        .map_err(as_python_value_error);
    }
    if shape[1] != query.len() {
        return Err(PyValueError::new_err(format!(
            "document vectors have {} dimensions; expected {}",
            shape[1],
            query.len()
        )));
    }

    let documents = document_vectors
        .as_slice()
        .map_err(|_| PyValueError::new_err("document_vectors must be C-contiguous"))?;
    cosine_similarity_scores_from_slices(query, documents.chunks(shape[1]), top_k, None)
        .map_err(as_python_value_error)
}

#[cfg(feature = "python")]
#[pyfunction]
fn batch_cosine_search(
    queries: Vec<Vec<f32>>,
    documents: Vec<Vec<f32>>,
    top_k: usize,
) -> PyResult<Vec<Vec<(usize, f32)>>> {
    let mut batch_results = Vec::with_capacity(queries.len());
    for query in &queries {
        let result = cosine_similarity_scores(query, &documents, top_k, None)
            .map_err(as_python_value_error)?;
        batch_results.push(result);
    }
    Ok(batch_results)
}

#[cfg(feature = "python")]
#[pyfunction]
fn cosine_similarity_search_with_threshold(
    query_vector: Vec<f32>,
    document_vectors: Vec<Vec<f32>>,
    top_k: usize,
    threshold: f32,
) -> PyResult<Vec<(usize, f32)>> {
    cosine_similarity_scores(&query_vector, &document_vectors, top_k, Some(threshold))
        .map_err(as_python_value_error)
}

/// M\u00f3dulo Python expuesto
#[cfg(feature = "python")]
#[pymodule]
fn jas_vector_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(cosine_similarity_search, m)?)?;
    m.add_function(wrap_pyfunction!(cosine_similarity_search_numpy, m)?)?;
    m.add_function(wrap_pyfunction!(batch_cosine_search, m)?)?;
    m.add_function(wrap_pyfunction!(
        cosine_similarity_search_with_threshold,
        m
    )?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::cosine_similarity_scores;

    fn assert_close(actual: f32, expected: f32) {
        assert!((actual - expected).abs() < 1e-6, "{actual} != {expected}");
    }

    #[test]
    fn ranks_by_cosine_similarity_and_respects_top_k() {
        let documents = vec![vec![0.0, 1.0], vec![1.0, 0.0], vec![-1.0, 0.0]];

        let scores = cosine_similarity_scores(&[1.0, 0.0], &documents, 2, None).unwrap();

        assert_eq!(scores.len(), 2);
        assert_eq!(scores[0].0, 1);
        assert_close(scores[0].1, 1.0);
        assert_eq!(scores[1].0, 0);
        assert_close(scores[1].1, 0.0);
    }

    #[test]
    fn filters_by_threshold() {
        let documents = vec![vec![1.0, 0.0], vec![0.8, 0.6], vec![0.0, 1.0]];

        let scores = cosine_similarity_scores(&[1.0, 0.0], &documents, 10, Some(0.75)).unwrap();

        assert_eq!(scores.len(), 2);
        assert_eq!(scores[0].0, 0);
        assert_eq!(scores[1].0, 1);
    }

    #[test]
    fn handles_zero_vectors_and_empty_documents() {
        let zero_scores =
            cosine_similarity_scores(&[0.0, 0.0], &[vec![1.0, 0.0]], 5, None).unwrap();
        let empty_scores = cosine_similarity_scores(&[1.0], &[], 5, Some(0.5)).unwrap();

        assert_close(zero_scores[0].1, 0.0);
        assert!(empty_scores.is_empty());
    }

    #[test]
    fn rejects_invalid_dimensions_and_non_finite_values() {
        let dimensions = cosine_similarity_scores(&[1.0, 0.0], &[vec![1.0]], 5, None).unwrap_err();
        let query = cosine_similarity_scores(&[], &[], 5, None).unwrap_err();
        let finite = cosine_similarity_scores(&[f32::NAN], &[vec![1.0]], 5, None).unwrap_err();

        assert!(dimensions.contains("expected 2"));
        assert!(query.contains("must not be empty"));
        assert!(finite.contains("finite"));
    }
}
