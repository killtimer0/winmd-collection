use std::path::PathBuf;
use std::process::Command;

#[test]
fn crt_parameter_aliases_survive_metadata_roundtrip() {
    use windows_metadata::{Type, reader::Index};

    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("verification/crt-parameter-aliases");
    for target in [
        "i686-pc-windows-msvc",
        "x86_64-pc-windows-msvc",
        "aarch64-pc-windows-msvc",
    ] {
        let dir = root.join(target);
        std::fs::create_dir_all(&dir).unwrap();
        windows_clang::clang()
            .input_text(
                "typedef char *va_list; int consume(va_list args, char *raw, va_list *indirect);",
            )
            .args(["-x", "c", &format!("--target={target}")])
            .namespace("Probe")
            .library("probe.dll")
            .output(dir.join("input.rdl"))
            .write()
            .unwrap();
        for (input, output) in [
            ("input.rdl", "first.winmd"),
            ("roundtrip.rdl", "second.winmd"),
        ] {
            windows_rdl::reader()
                .input(dir.join(input))
                .output(dir.join(output))
                .write()
                .unwrap();
            let index = Index::read(dir.join(output)).unwrap();
            let method = index
                .expect("Probe", "Apis")
                .methods()
                .find(|method| method.name() == "consume")
                .unwrap();
            let alias = Type::value_named("Probe", "va_list");
            assert_eq!(
                method.signature(&[]).types,
                vec![
                    alias.clone(),
                    Type::PtrMut(Box::new(Type::I8), 1),
                    Type::PtrMut(Box::new(alias), 1),
                ],
                "{target}: {output}"
            );
            windows_rdl::writer()
                .input(dir.join(output))
                .output(dir.join("roundtrip.rdl"))
                .write()
                .unwrap();
        }
    }
}

#[test]
fn selected_includes_take_precedence_over_compiler_defaults() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let config: serde_json::Value =
        serde_json::from_slice(&std::fs::read(root.join("out/toolchain.json")).unwrap()).unwrap();
    let args: Vec<String> = serde_json::from_value(config["clang_args"].clone()).unwrap();
    let dir = root.join("verification/include-search/路径 with spaces");
    let selected = dir.join("selected");
    let resource = dir.join("resource");
    std::fs::create_dir_all(&selected).unwrap();
    std::fs::create_dir_all(resource.join("include")).unwrap();
    std::fs::write(selected.join("selection.h"), "int selected_header;\n").unwrap();
    std::fs::write(
        resource.join("include/selection.h"),
        "#error compiler defaults displaced the selected include directory\n",
    )
    .unwrap();
    let source = dir.join("probe.c");
    std::fs::write(&source, "#include <selection.h>\n").unwrap();
    let output = Command::new(config["clang_path"].as_str().unwrap())
        .args(args)
        .arg("--target=i686-pc-windows-msvc")
        .arg("-I")
        .arg(&selected)
        .arg("-resource-dir")
        .arg(&resource)
        .arg("-fsyntax-only")
        .arg(&source)
        .env("INCLUDE", &selected)
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn version_queries_and_generation_share_a_runtime_lifetime() {
    let dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("verification")
        .join("libclang-lifetime");
    std::fs::create_dir_all(&dir).unwrap();
    for _ in 0..2 {
        assert!(!windows_clang::clang_version().unwrap().is_empty());
        windows_clang::clang()
            .input_text("int probe(int value);")
            .args(["-x", "c", "--target=i686-pc-windows-msvc"])
            .namespace("Probe")
            .library("probe.dll")
            .output(dir.join("probe.rdl"))
            .write()
            .unwrap();
        windows_rdl::reader()
            .input(dir.join("probe.rdl"))
            .output(dir.join("probe.winmd"))
            .write()
            .unwrap();
        let index = windows_metadata::reader::Index::read(dir.join("probe.winmd")).unwrap();
        assert!(
            index
                .expect("Probe", "Apis")
                .methods()
                .any(|method| method.name() == "probe")
        );
    }
}
