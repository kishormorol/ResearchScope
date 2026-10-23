// Use a disposable local API, prepared synthetic paper and canned Responses server.
// Usage: paper_chat SESSION_ID DUMMY_TOKEN complete|PROVIDER_ERROR_CODE [fixture_marker]
use std::{
    env,
    io::{Read, Write},
    net::TcpStream,
    time::Duration,
};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    assert!(
        (4..=5).contains(&args.len()),
        "supply session, dummy token, result and optional marker"
    );
    assert!(args[1].chars().all(|c| c.is_ascii_hexdigit() || c == '-'));
    assert!(!args[2].contains(['\r', '\n']));
    assert!(args[3] == "complete" || args[3].starts_with("provider_"));
    let marker = args.get(4).map(String::as_str).unwrap_or("");
    assert!(marker.len() < 64 && marker.chars().all(|c| c.is_ascii_lowercase() || c == '_'));
    let body = format!(r#"{{"content":"What embedding does the method use? {marker}"}}"#);
    let mut stream = TcpStream::connect("127.0.0.1:8000")?;
    stream.set_read_timeout(Some(Duration::from_secs(10)))?;
    stream.set_write_timeout(Some(Duration::from_secs(5)))?;
    write!(stream,
        "POST /chat/sessions/{}/messages HTTP/1.1\r\nHost: 127.0.0.1:8000\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: {}\r\n\r\n{}",
        args[1], args[2], body.len(), body)?;
    let mut response = String::new();
    stream.take(1024 * 1024 + 1).read_to_string(&mut response)?;
    assert!(
        response.len() <= 1024 * 1024,
        "response exceeds fixture limit"
    );
    assert!(
        response.starts_with("HTTP/1.1 200 "),
        "chat request failed: {response}"
    );
    assert!(response.contains("event: message_started\n"));
    if args[3] == "complete" {
        assert!(response.contains("event: message_completed\n"));
        assert!(response.contains("event: citations\n"));
        assert!(response.contains("The method uses fixture embeddings [S1]."));
        assert!(response.contains("\"page_start\": 1"));
        assert!(!response.contains("event: error\n"));
    } else {
        assert!(response.contains("event: error\n"));
        assert!(response.contains(&format!("\"code\": \"{}\"", args[3])));
        assert!(!response.contains("event: message_completed\n"));
        assert!(!response.contains("event: delta\n"));
        assert!(!response.contains("event: citations\n"));
    }
    println!("chat stream matched {} marker={marker}", args[3]);
    Ok(())
}
