//! Dependency-free Rust reference for the API-1 command profile.

use std::io::{self, BufRead, Read, Write};

const MAX_MESSAGE: usize = 16 * 1024 * 1024;

const INITIALIZE_RESULT: &str = r#"{"plugin_id":"org.manuskript.reference.rust","api_version":1,"protocol_version":1,"contributions":[{"declaration":{"$kind":"record","name":"contribution_declaration","version":1,"fields":{"kind":{"$kind":"enum","name":"contribution_kind","value":"command"},"descriptor":{"$kind":"record","name":"extension_descriptor","version":1,"fields":{"id":"org.manuskript.reference.rust.command","name":"Rust conformance command","description":"","icon":"","extensions":{"$kind":"tuple","items":[]}}},"configuration":{"$kind":"map","items":{}}}},"operations":["invoke"]}]}"#;

const COMMAND_RESULT: &str = r#"{"$kind":"map","items":{"language":"rust","message":"Manuskript API 1"}}"#;

fn read_message<R: BufRead>(input: &mut R) -> io::Result<Option<String>> {
    let mut length: Option<usize> = None;
    loop {
        let mut line = String::new();
        if input.read_line(&mut line)? == 0 {
            return Ok(None);
        }
        if line == "\r\n" {
            break;
        }
        if let Some((name, value)) = line.split_once(':') {
            if name.trim().eq_ignore_ascii_case("content-length") {
                if length.is_some() {
                    return Err(io::Error::new(io::ErrorKind::InvalidData,
                        "duplicate Content-Length"));
                }
                length = Some(value.trim().parse().map_err(|_| {
                    io::Error::new(io::ErrorKind::InvalidData,
                        "invalid Content-Length")
                })?);
            }
        }
    }
    let length = length.ok_or_else(||
        io::Error::new(io::ErrorKind::InvalidData, "missing Content-Length"))?;
    if !(2..=MAX_MESSAGE).contains(&length) {
        return Err(io::Error::new(io::ErrorKind::InvalidData,
            "payload length is out of bounds"));
    }
    let mut payload = vec![0_u8; length];
    input.read_exact(&mut payload)?;
    String::from_utf8(payload).map(Some).map_err(|_| {
        io::Error::new(io::ErrorKind::InvalidData, "payload is not UTF-8")
    })
}

fn request_id(message: &str) -> io::Result<i64> {
    let start = message.find("\"id\":").ok_or_else(||
        io::Error::new(io::ErrorKind::InvalidData, "request has no id"))? + 5;
    let digits: String = message[start..].chars()
        .take_while(|character| character.is_ascii_digit())
        .collect();
    digits.parse().map_err(|_| {
        io::Error::new(io::ErrorKind::InvalidData, "request id is not numeric")
    })
}

fn send_result<W: Write>(output: &mut W, id: i64, result: &str) -> io::Result<()> {
    let payload = format!(
        "{{\"jsonrpc\":\"2.0\",\"id\":{},\"result\":{}}}", id, result
    );
    write!(output, "Content-Length: {}\r\n\r\n", payload.len())?;
    output.write_all(payload.as_bytes())?;
    output.flush()
}

fn main() -> io::Result<()> {
    let stdin = io::stdin();
    let stdout = io::stdout();
    let mut input = stdin.lock();
    let mut output = stdout.lock();
    while let Some(message) = read_message(&mut input)? {
        if message.contains("\"method\":\"exit\"") {
            return Ok(());
        }
        if message.contains("\"method\":\"initialize\"") {
            send_result(&mut output, request_id(&message)?, INITIALIZE_RESULT)?;
        } else if message.contains("\"method\":\"contribution/call\"") {
            send_result(&mut output, request_id(&message)?, COMMAND_RESULT)?;
        } else if message.contains("\"method\":\"deactivate\"")
            || message.contains("\"method\":\"shutdown\"")
        {
            send_result(&mut output, request_id(&message)?, "null")?;
        }
    }
    Ok(())
}
