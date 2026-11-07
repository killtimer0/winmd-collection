use std::error::Error;

fn main() -> Result<(), Box<dyn Error>> {
    std::env::set_current_dir(env!("CARGO_MANIFEST_DIR"))?;
    let arch = std::env::args().nth(1).unwrap_or_else(|| "x64".into());
    let config: serde_json::Value = serde_json::from_slice(
        &std::fs::read("out/toolchain.json")
            .map_err(|error| format!("{error}; configure the toolchain with build.ps1 first"))?,
    )?;
    let reference = std::path::Path::new(
        config["win32_metadata"]
            .as_str()
            .ok_or("toolchain win32_metadata is required")?,
    );
    if arch == "merge" {
        let mut merger = windows_metadata::merge::Merger::new();
        merger.reference(reference);
        for (name, bits) in [("x86", 1), ("x64", 2), ("arm64", 4)] {
            merger.arch_input(format!("out/{name}/UCRT.winmd"), bits);
        }
        merger.output("out/UCRT.winmd").merge()?;
        roundtrip(std::path::Path::new("out"), reference)?;
        return Ok(());
    }
    let target = match arch.as_str() {
        "x86" => "i686-pc-windows-msvc",
        "x64" => "x86_64-pc-windows-msvc",
        "arm64" => "aarch64-pc-windows-msvc",
        _ => return Err("expected x86, x64 or arm64".into()),
    };
    let out = std::path::PathBuf::from("out").join(&arch);
    std::fs::create_dir_all(&out)?;
    let mut args = clang_args(&config)?;
    args.push(format!("--target={target}"));
    let clang_version = windows_clang::clang_version()?;
    println!("{clang_version}");
    if out.join("rdl").exists() {
        std::fs::remove_dir_all(out.join("rdl"))?;
    }
    windows_clang::clang()
        .input("main.h")
        .args(args)
        .scope_headers(["stdio.h", "stdlib.h", "string.h", "time.h", "stat.h"])
        .scope("ucrt")
        .scope_headers(["vadefs.h", "vcruntime.h", "vcruntime_startup.h", "stddef.h"])
        .namespace("Ucrt.CRuntime")
        .library("")
        .output(out.join("rdl"))
        .write_by_header()?;
    for entry in std::fs::read_dir(out.join("rdl"))? {
        let path = entry?.path();
        if path.extension().is_some_and(|extension| extension == "rdl") {
            let source = std::fs::read_to_string(&path)?;
            std::fs::write(&path, source.replace("#[library(\"\")]", "#[declaration]"))?;
        }
    }
    windows_rdl::reader()
        .input(out.join("rdl"))
        .input("declarations.rdl")
        .reference(reference)
        .output(out.join("UCRT.untagged.winmd"))
        .write()?;
    let bits = match arch.as_str() {
        "x86" => 1,
        "x64" => 2,
        _ => 4,
    };
    windows_metadata::merge::Merger::new()
        .reference(reference)
        .arch_input(out.join("UCRT.untagged.winmd"), bits)
        .output(out.join("UCRT.winmd"))
        .merge()?;
    roundtrip(&out, reference)?;
    write_inventory(&out)?;
    std::fs::write(
        out.join("generation.json"),
        serde_json::to_vec_pretty(&serde_json::json!({
            "architecture": arch, "target": target, "libclang_version": clang_version,
        }))?,
    )?;
    Ok(())
}

fn clang_args(config: &serde_json::Value) -> Result<Vec<String>, Box<dyn Error>> {
    let args: Vec<String> = serde_json::from_value(config["clang_args"].clone())?;
    if args.is_empty() {
        return Err("toolchain clang_args must not be empty".into());
    }
    Ok(args)
}

fn roundtrip(out: &std::path::Path, reference: &std::path::Path) -> Result<(), Box<dyn Error>> {
    windows_rdl::writer()
        .input(out.join("UCRT.winmd"))
        .output(out.join("roundtrip.rdl"))
        .write()?;
    windows_rdl::reader()
        .input(out.join("roundtrip.rdl"))
        .reference(reference)
        .output(out.join("UCRT.roundtrip.winmd"))
        .write()?;
    Ok(())
}

fn write_inventory(out: &std::path::Path) -> Result<(), Box<dyn Error>> {
    let index = windows_metadata::reader::Index::read(out.join("UCRT.winmd"))
        .ok_or("failed to read UCRT metadata for inventory")?;
    let mut inventory = String::from("kind\towner\tname\tparameter_count\tvariadic\tfields\n");
    for ty in index.types().filter(|t| t.namespace() == "Ucrt.CRuntime") {
        let mut fields: Vec<_> = ty.fields().map(|f| f.name()).collect();
        if ty.name() == "Apis" {
            fields.sort();
        }
        inventory.push_str(&format!(
            "type\t\t{}\t\t\t{}\n",
            ty.name(),
            fields.join(",")
        ));
        for method in ty.methods() {
            let sig = method.signature(&[]);
            inventory.push_str(&format!(
                "method\t{}\t{}\t{}\t{}\t\n",
                ty.name(),
                method.name(),
                sig.types.len(),
                (sig.flags.0 & 15) == 5
            ));
        }
    }
    std::fs::write(out.join("winmd-inventory.tsv"), inventory)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn inventory_preserves_record_field_order_and_function_shape() {
        let out = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("verification/inventory-contract");
        std::fs::create_dir_all(&out).unwrap();
        windows_rdl::reader()
            .input_text(
                r#"#[win32] mod Ucrt { mod CRuntime {
                    struct Record { z: i32, a: u8 }
                    #[declaration] extern "C" fn print(format: *const i8, ...) -> i32;
                    #[declaration] extern "C" fn release(value: *mut u8);
                }}"#,
            )
            .input("declarations.rdl")
            .reference_default()
            .output(out.join("UCRT.winmd"))
            .write()
            .unwrap();
        write_inventory(&out).unwrap();
        let inventory = std::fs::read_to_string(out.join("winmd-inventory.tsv")).unwrap();
        let mut rows: Vec<_> = inventory.lines().collect();
        assert_eq!(
            rows.remove(0),
            "kind\towner\tname\tparameter_count\tvariadic\tfields"
        );
        rows.sort();
        assert_eq!(
            rows,
            vec![
                "method\tApis\tprint\t1\ttrue\t",
                "method\tApis\trelease\t1\tfalse\t",
                "type\t\tApis\t\t\t",
                "type\t\tRecord\t\t\tz,a",
            ]
        );
    }

    #[test]
    fn toolchain_args_preserve_unicode_spaces_and_unc_paths() {
        let args = vec![
            "-x",
            "c",
            "-IC:/SDK 路径/ucrt",
            "-I\\\\server\\share\\include",
        ];
        assert_eq!(
            clang_args(&serde_json::json!({"clang_args": args})).unwrap(),
            args
        );
    }

    #[test]
    fn toolchain_rejects_missing_empty_or_nonstring_args() {
        for value in [
            serde_json::json!({}),
            serde_json::json!({"clang_args": []}),
            serde_json::json!({"clang_args": [1]}),
        ] {
            assert!(clang_args(&value).is_err());
        }
    }
}
