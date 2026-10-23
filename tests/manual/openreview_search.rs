// Usage: openreview_search CONFERENCES_DB_JSON EXPECTED_OPENREVIEW_JSON
// Use the uncapped conferences_db.json, not the browser subset conferences.json.
// Run after the pipeline against controlled search or fallback responses.
use std::{env, process::Command};

fn main() {
    let args: Vec<String> = env::args().collect();
    assert_eq!(
        args.len(),
        3,
        "supply generated conferences and expected records"
    );
    let status = Command::new("jq")
        .args([
            "-e", "--slurpfile", "expected", &args[2],
            "[.[] | select(.source == \"openreview\")] | length as $count | map({key: .id, value: {title, abstract, authors, venue, published_date, presentation_type, paper_url, pdf_url}}) | from_entries | length == $count and . == $expected[0]",
            &args[1],
        ])
        .status()
        .expect("jq must be installed for this manual check");
    assert!(
        status.success(),
        "OpenReview records differ from the source fixture"
    );
    println!("OpenReview search records match the source fixture");
}
