// Use only a disposable local API and dummy credentials.
// The held mode waits for one stdin byte after message_started, then disconnects.
use std::env;
use std::io::{Read, Write};
use std::net::{Shutdown, TcpStream};
use std::process;
use std::time::Duration;

const MAX_RESPONSE: usize = 1_048_576;

fn fail(message: &str) -> ! {
    eprintln!("{message}");
    process::exit(2);
}

fn valid_uuid(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 36
        && bytes.iter().enumerate().all(|(i, byte)| match i {
            8 | 13 | 18 | 23 => *byte == b'-',
            _ => byte.is_ascii_hexdigit(),
        })
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    if args.len() != 3 {
        fail("usage: chat_cancel SESSION_ID DUMMY_JWT started|held|complete");
    }
    let (session_id, token, mode) = (&args[0], &args[1], &args[2]);
    if !valid_uuid(session_id) {
        fail("session id must be a UUID");
    }
    if token.is_empty() || token.bytes().any(|byte| byte == b'\r' || byte == b'\n') {
        fail("JWT must be nonempty and contain no line breaks");
    }
    if mode != "started" && mode != "held" && mode != "complete" {
        fail("mode must be started, held or complete");
    }

    let marker = if mode == "complete" {
        ""
    } else {
        "fixture_hold"
    };
    let content = format!("What embedding does the method use? {marker}");
    let body = format!("{{\"content\":\"{content}\"}}");
    let request = format!(
        "POST /chat/sessions/{session_id}/messages HTTP/1.1\r\nHost: 127.0.0.1:8000\r\nAuthorization: Bearer {token}\r\nContent-Type: application/json\r\nAccept: text/event-stream\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );

    let mut stream =
        TcpStream::connect("127.0.0.1:8000").unwrap_or_else(|_| fail("connect failed"));
    stream
        .set_read_timeout(Some(Duration::from_secs(10)))
        .unwrap_or_else(|_| fail("could not set read timeout"));
    stream
        .set_write_timeout(Some(Duration::from_secs(5)))
        .unwrap_or_else(|_| fail("could not set write timeout"));
    stream
        .write_all(request.as_bytes())
        .unwrap_or_else(|_| fail("request write failed"));

    let mut response = Vec::new();
    let mut chunk = [0u8; 4096];
    let event = if mode == "complete" {
        "event: message_completed\n"
    } else {
        "event: message_started\n"
    };
    loop {
        let count = match stream.read(&mut chunk) {
            Ok(count) => count,
            Err(error) => fail(&format!("response read failed: {error}")),
        };
        if count == 0 {
            break;
        }
        if response.len() + count > MAX_RESPONSE {
            fail("response exceeded 1 MiB before target event");
        }
        response.extend_from_slice(&chunk[..count]);
        if response.windows(4).any(|window| window == b"\r\n\r\n") {
            let headers_end = response
                .windows(4)
                .position(|window| window == b"\r\n\r\n")
                .unwrap()
                + 4;
            if !response[..headers_end].starts_with(b"HTTP/1.1 200 ") {
                fail("API did not return HTTP 200");
            }
        }
        if response
            .windows(event.len())
            .any(|window| window == event.as_bytes())
        {
            break;
        }
    }

    let received = response.len();
    if !response
        .windows(event.len())
        .any(|window| window == event.as_bytes())
    {
        fail("target event was not received");
    }
    if mode == "held" {
        println!("event received; send one input byte to disconnect");
        std::io::stdout().flush().unwrap();
        std::io::stdin().read_exact(&mut [0]).unwrap();
    }
    let _ = stream.shutdown(Shutdown::Both);
    drop(stream);
    println!("mode={mode} received_bytes={received}");
}
