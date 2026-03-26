use std::io::{self, Read};
use serde_json::{json, Value};

fn main() {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input).expect("Failed to read stdin");

    let parts: Vec<&str> = input.splitn(2, "\n===\n").collect();
    if parts.len() != 2 {
        eprintln!("Error: could not find separator '==='");
        std::process::exit(1);
    }

    let body_str = parts[0].trim();
    let meta_str = parts[1].trim();

    let body: Value = serde_json::from_str(body_str)
        .unwrap_or(Value::String(body_str.to_string()));

    let mut result = json!({ "body": body });

    for line in meta_str.lines() {
        if let Some((key, value)) = line.split_once(':') {
            let key = key.trim();
            result[key] = Value::String(value.to_string());
        }
    }

    println!("{}", serde_json::to_string_pretty(&result).unwrap());
}