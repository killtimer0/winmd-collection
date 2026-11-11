use windows_rdl::implib::{Import, read};

const X86: u16 = 0x14c;
const ARM64: u16 = 0xaa64;

fn member(name: &str, body: &[u8]) -> Vec<u8> {
    let mut header = [b' '; 60];
    header[..name.len()].copy_from_slice(name.as_bytes());
    header[48..58].copy_from_slice(format!("{:<10}", body.len()).as_bytes());
    header[58] = b'`';
    header[59] = b'\n';
    let mut out = header.to_vec();
    out.extend_from_slice(body);
    if body.len() % 2 == 1 {
        out.push(b'\n');
    }
    out
}

fn object(machine: u16, name_type: u16, strings: &[&str]) -> Vec<u8> {
    let mut data = vec![];
    for string in strings {
        data.extend_from_slice(string.as_bytes());
        data.push(0);
    }
    let mut body = vec![0, 0, 0xff, 0xff];
    body.extend_from_slice(&0u16.to_le_bytes());
    body.extend_from_slice(&machine.to_le_bytes());
    body.extend_from_slice(&0u32.to_le_bytes());
    body.extend_from_slice(&(data.len() as u32).to_le_bytes());
    body.extend_from_slice(&0u16.to_le_bytes());
    body.extend_from_slice(&(name_type << 2).to_le_bytes());
    body.extend_from_slice(&data);
    body
}

fn archive(members: &[Vec<u8>]) -> Vec<u8> {
    let mut out = b"!<arch>\n".to_vec();
    for (index, body) in members.iter().enumerate() {
        out.extend_from_slice(&member(&format!("/{index}"), body));
    }
    out
}

#[test]
fn name_types_resolve_the_dll_export_name() {
    let bytes = archive(&[
        object(X86, 1, &["fopen", "filesystem.dll"]),
        object(X86, 2, &["_malloc", "heap.dll"]),
        object(X86, 2, &["__aligned_malloc", "heap.dll"]),
        object(X86, 3, &["_stack_probe@12", "stack.dll"]),
        object(ARM64, 4, &["#_Cbuild", "math.dll", "_Cbuild"]),
    ]);
    let imports = read(&bytes).unwrap();
    assert_eq!(
        imports,
        vec![
            Import {
                machine: X86,
                export: "fopen".into(),
                dll: "filesystem.dll".into()
            },
            Import {
                machine: X86,
                export: "malloc".into(),
                dll: "heap.dll".into()
            },
            // One prefix is removed; the second underscore belongs to the public name.
            Import {
                machine: X86,
                export: "_aligned_malloc".into(),
                dll: "heap.dll".into()
            },
            Import {
                machine: X86,
                export: "stack_probe".into(),
                dll: "stack.dll".into()
            },
            Import {
                machine: ARM64,
                export: "_Cbuild".into(),
                dll: "math.dll".into()
            },
        ]
    );
}

#[test]
fn duplicate_exports_keep_their_target_machine() {
    let bytes = archive(&[
        object(0xa641, 4, &["#malloc", "heap.dll", "malloc"]),
        object(ARM64, 1, &["malloc", "heap.dll"]),
    ]);
    let imports = read(&bytes).unwrap();
    assert_eq!(
        imports.iter().map(|i| i.machine).collect::<Vec<_>>(),
        vec![0xa641, ARM64]
    );
    assert!(imports.iter().all(|i| i.export == "malloc"));
}

#[test]
fn ordinal_members_have_no_export_name() {
    let bytes = archive(&[object(X86, 0, &["heap.dll"])]);
    assert!(read(&bytes).unwrap().is_empty());
}

#[test]
fn malformed_archives_are_rejected() {
    assert!(read(b"not an archive").is_err());
    let mut truncated = archive(&[object(X86, 1, &["malloc", "heap.dll"])]);
    truncated.truncate(truncated.len() - 1);
    assert!(read(&truncated).is_err());
    let mut bad_marker = archive(&[object(X86, 1, &["malloc", "heap.dll"])]);
    bad_marker[8 + 58] = b'X';
    assert!(read(&bad_marker).is_err());
}
