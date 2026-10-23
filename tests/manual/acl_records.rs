// Usage: acl_records CONFERENCES_DB_JSON EXPECTED_ACL_JSON
// Run after the actual pipeline reads controlled search or BibTeX responses.
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
            "[.[] | select(.source == \"acl_anthology\")] | length as $count | map({key: .id, value: {title, authors, abstract, year, venue, paper_url, pdf_url}}) | from_entries | length == $count and . == $expected[0]",
            &args[1],
        ])
        .status()
        .expect("jq must be installed for this manual check");
    assert!(
        status.success(),
        "ACL records differ from the source fixture"
    );
    println!("ACL records match the source fixture");
}
