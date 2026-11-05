use std::path::PathBuf;

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
