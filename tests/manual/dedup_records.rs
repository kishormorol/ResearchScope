// Usage: dedup_records UNCAPPED_JOURNAL_ARCHIVE EXPECTED_RECORDS_JSON
// Run after the actual pipeline reads controlled source responses.
use std::{env, process::Command};

fn main() {
    let args: Vec<String> = env::args().collect();
    assert_eq!(args.len(), 3, "supply an archive and expected records");
    let status = Command::new("jq")
        .args([
            "-e", "--slurpfile", "expected", &args[2],
            "length as $count | map({key: .id, value: {source, source_type, title, abstract, authors, year, venue, paper_url, pdf_url}}) | from_entries | length == $count and . == $expected[0]",
            &args[1],
        ])
        .status()
        .expect("jq must be installed for this manual check");
    assert!(
        status.success(),
        "deduplicated records differ from the fixture"
    );
    println!("Deduplicated records match the source fixture");
}
