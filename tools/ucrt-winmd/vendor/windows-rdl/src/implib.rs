//! Reader for SDK COFF import libraries, which record the DLL exporting each symbol.

use crate::Error;

/// One short-import symbol, its DLL export name and the architecture it targets.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Import {
    /// Target machine (`IMAGE_FILE_MACHINE_*`); ARM64 libraries also carry ARM64EC.
    pub machine: u16,
    /// DLL export name after applying the member's name type.
    pub export: String,
    pub dll: String,
}

const ARCHIVE_MAGIC: &[u8] = b"!<arch>\n";
const MEMBER_HEADER_LEN: usize = 60;
/// `IMPORT_OBJECT_HEADER` short-import signature.
const IMPORT_SIGNATURE: &[u8] = &[0x00, 0x00, 0xFF, 0xFF];
const IMPORT_HEADER_LEN: usize = 20;
const MACHINE_OFFSET: usize = 6;
const SIZE_OF_DATA_OFFSET: usize = 12;
const FLAGS_OFFSET: usize = 18;

/// `IMPORT_OBJECT_NAME_TYPE` values.
const ORDINAL: u16 = 0;
const NAME: u16 = 1;
const NAME_NO_PREFIX: u16 = 2;
const UNDECORATE: u16 = 3;
const EXPORTAS: u16 = 4;

/// Parses every named short-import member, preserving archive order and duplicates.
///
/// Ordinal-only members carry no export name and are skipped.
pub fn read(bytes: &[u8]) -> Result<Vec<Import>, Error> {
    if bytes.len() < ARCHIVE_MAGIC.len() || &bytes[..ARCHIVE_MAGIC.len()] != ARCHIVE_MAGIC {
        return Err(err("not a COFF archive (missing `!<arch>` magic)"));
    }

    let mut imports = vec![];
    let mut pos = ARCHIVE_MAGIC.len();

    while pos + MEMBER_HEADER_LEN <= bytes.len() {
        let header = &bytes[pos..pos + MEMBER_HEADER_LEN];

        // The end marker guards against a misaligned archive walk.
        let name = trim(&header[0..16]);
        let size = parse_decimal(&header[48..58])?;
        if header[58..60] != [0x60, 0x0A] {
            return Err(err("malformed archive member header (bad end marker)"));
        }

        let data_start = pos + MEMBER_HEADER_LEN;
        let data_end = data_start
            .checked_add(size)
            .filter(|&end| end <= bytes.len())
            .ok_or_else(|| err("archive member extends past end of data"))?;
        let data = &bytes[data_start..data_end];

        // Skip archive bookkeeping members.
        if name != b"/" && name != b"//" && data.starts_with(IMPORT_SIGNATURE) {
            if let Some(import) = parse_short_import(data)? {
                imports.push(import);
            }
        }

        pos = data_end + (size & 1);
    }

    Ok(imports)
}

fn parse_short_import(data: &[u8]) -> Result<Option<Import>, Error> {
    let machine = u16::from_le_bytes(
        data.get(MACHINE_OFFSET..MACHINE_OFFSET + 2)
            .ok_or_else(|| err("short import member is shorter than its header"))?
            .try_into()
            .unwrap(),
    );
    let size_of_data = u32::from_le_bytes(
        data.get(SIZE_OF_DATA_OFFSET..SIZE_OF_DATA_OFFSET + 4)
            .ok_or_else(|| err("short import member is shorter than its header"))?
            .try_into()
            .unwrap(),
    ) as usize;
    let flags = u16::from_le_bytes(
        data.get(FLAGS_OFFSET..FLAGS_OFFSET + 2)
            .ok_or_else(|| err("short import member is shorter than its header"))?
            .try_into()
            .unwrap(),
    );
    let name_type = (flags >> 2) & 0x7;

    let strings = data
        .get(IMPORT_HEADER_LEN..IMPORT_HEADER_LEN + size_of_data)
        .ok_or_else(|| err("short import names extend past member data"))?;

    if name_type == ORDINAL {
        return Ok(None);
    }

    let mut parts = strings.split(|&b| b == 0);
    let symbol = next_string(&mut parts, "symbol")?;
    let dll = next_string(&mut parts, "DLL")?;
    let export = match name_type {
        NAME => symbol,
        NAME_NO_PREFIX => strip_prefix(&symbol).to_string(),
        UNDECORATE => strip_undecorate(&symbol),
        EXPORTAS => next_string(&mut parts, "export")?,
        other => {
            return Err(err(&format!(
                "short import has unsupported name type {other}"
            )));
        }
    };

    Ok(Some(Import {
        machine,
        export,
        dll,
    }))
}

fn strip_prefix(symbol: &str) -> &str {
    symbol.strip_prefix('_').unwrap_or(symbol)
}

/// MSVC name undecoration for `__cdecl`/`__stdcall` decorations: `_name@12` -> `name`.
fn strip_undecorate(symbol: &str) -> String {
    let name = strip_prefix(symbol);
    match name.rfind('@') {
        Some(at) if name[at + 1..].chars().all(|c| c.is_ascii_digit()) => name[..at].to_string(),
        _ => name.to_string(),
    }
}

fn next_string<'a>(
    parts: &mut impl Iterator<Item = &'a [u8]>,
    what: &str,
) -> Result<String, Error> {
    let bytes = parts
        .next()
        .filter(|b| !b.is_empty())
        .ok_or_else(|| err(&format!("short import missing {what} name")))?;
    std::str::from_utf8(bytes)
        .map(str::to_string)
        .map_err(|_| err(&format!("short import {what} name is not valid UTF-8")))
}

fn parse_decimal(field: &[u8]) -> Result<usize, Error> {
    let text = std::str::from_utf8(field)
        .map_err(|_| err("archive member size is not valid ASCII"))?
        .trim();
    text.parse::<usize>()
        .map_err(|_| err("archive member has an invalid size field"))
}

fn trim(field: &[u8]) -> &[u8] {
    let end = field.iter().rposition(|&b| b != b' ').map_or(0, |i| i + 1);
    &field[..end]
}

fn err(message: &str) -> Error {
    Error::new(message, "", 0, 0)
}
