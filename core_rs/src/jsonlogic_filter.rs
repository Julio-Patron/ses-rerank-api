pub fn filter_by_jsonlogic(rule_str: &str, metadata_json_strings: &[String]) -> Result<Vec<usize>, String> {
    let results = jsonlogic_fast::evaluate_batch(rule_str, metadata_json_strings)
        .map_err(|e| format!("JSONLogic error: {}", e))?;
    
    let mut passed = Vec::new();
    for (i, val) in results.into_iter().enumerate() {
        println!("Metadata {}: Eval result: {}", i, val);
        if val == serde_json::Value::Bool(true) {
            passed.push(i);
        }
    }
    
    Ok(passed)
}
