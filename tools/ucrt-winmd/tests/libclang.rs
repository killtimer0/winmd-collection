use std::path::PathBuf;
use std::process::Command;

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
