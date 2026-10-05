/// Returns the indices of the metadata documents for which `rule_str` evaluates
/// to exactly `true`.
pub fn filter_by_jsonlogic(
    rule_str: &str,
    metadata_json_strings: &[String],
) -> Result<Vec<usize>, String> {
    let results = jsonlogic_fast::evaluate_batch(rule_str, metadata_json_strings)
        .map_err(|e| format!("JSONLogic error: {e}"))?;

    Ok(results
        .into_iter()
        .enumerate()
        .filter(|(_, value)| *value == serde_json::Value::Bool(true))
        .map(|(index, _)| index)
        .collect())
}

#[cfg(test)]
mod tests {
    use super::filter_by_jsonlogic;

    fn metadata(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| value.to_string()).collect()
    }

    #[test]
    fn keeps_only_documents_matching_the_rule() {
        let docs = metadata(&[
            r#"{"year": 2020}"#,
            r#"{"year": 2024}"#,
            r#"{}"#,
            r#"{"year": 2025}"#,
        ]);
        let passed = filter_by_jsonlogic(r#"{">=": [{"var": "year"}, 2024]}"#, &docs).unwrap();
        assert_eq!(passed, vec![1, 3]);
    }

    #[test]
    fn truthy_but_non_boolean_results_do_not_pass() {
        let docs = metadata(&[r#"{"tag": "a"}"#]);
        let passed = filter_by_jsonlogic(r#"{"var": "tag"}"#, &docs).unwrap();
        assert!(passed.is_empty());
    }

    #[test]
    fn invalid_rule_is_an_error() {
        let docs = metadata(&[r#"{}"#]);
        let error = filter_by_jsonlogic("{not json", &docs).unwrap_err();
        assert!(error.starts_with("JSONLogic error"));
    }
}
