// Run from backend in an isolated fixture with no .env file or active API.
// Requires Python, uvicorn and GNU timeout. Checks actual API startup.
use std::process::Command;

fn main() {
    let invalid = [
        None,
        Some(""),
        Some(" \t "),
        Some("change-me-in-production"),
        Some("replace-with-a-long-random-secret"),
        Some("your-secret-key"),
        Some("your-secret-key-here"),
        Some("changeme"),
        Some("secret"),
        Some("  CHANGE-ME-IN-PRODUCTION  "),
    ];
    for secret in invalid {
        let mut command = Command::new("timeout");
        command.args([
            "--kill-after=1",
            "5",
            "python3",
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
        ]);
        command.env_remove("JWT_SECRET");
        if let Some(value) = secret {
            command.env("JWT_SECRET", value);
        }
        let result = command.output().expect("API startup command must run");
        assert_eq!(
            result.status.code(),
            Some(1),
            "unsafe config was not rejected"
        );
        assert!(String::from_utf8_lossy(&result.stderr)
            .contains("JWT_SECRET must be set to a value that is not a placeholder"));
    }
    println!("API startup rejected all ten unsafe signing configurations");
}
