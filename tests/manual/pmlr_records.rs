// Usage: pmlr_records CONFERENCES_DB_JSON EXPECTED_PMLR_JSON
// Use the uncapped archive after the actual pipeline reads controlled indexes.
use std::{env, process::Command};

fn main() {
    let args: Vec<String> = env::args().collect();
    assert_eq!(
        args.len(),
        3,
        "supply an uncapped archive and expected records"
    );
    let status = Command::new("jq")
        .args([
            "-e", "--slurpfile", "expected", &args[2],
            "[.[] | select(.source == \"pmlr\")] | length as $count | map({key: .id, value: {title, authors, abstract, paper_url, pdf_url, year, venue}}) | from_entries | length == $count and . == $expected[0]",
            &args[1],
        ])
        .status()
        .expect("jq must be installed for this manual check");
    assert!(
        status.success(),
        "PMLR records differ from the source fixture"
    );
    println!("PMLR records match the source fixture");
}
