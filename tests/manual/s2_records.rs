// Usage: s2_records UNCAPPED_ARCHIVE_JSON EXPECTED_S2_JSON
// Run after the pipeline against controlled search or journal responses.
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
            "[.[] | select(.source == \"semantic_scholar\")] | length as $count | map({key: .id, value: {title, abstract, authors, venue, source_type, year, citations, paper_url, pdf_url}}) | from_entries | length == $count and . == $expected[0]",
            &args[1],
        ])
        .status()
        .expect("jq must be installed for this manual check");
    assert!(
        status.success(),
        "Semantic Scholar records differ from the source fixture"
    );
    println!("Semantic Scholar records match the source fixture");
}
