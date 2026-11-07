use std::path::PathBuf;
use windows_metadata::{HasAttributes, ParamAttributes, Value, reader::Index};

#[test]
fn sal_written_lengths_are_reported_without_losing_buffer_extents() {
    const CHILD: &str = "UCRT_SAL_DIAGNOSTIC_CHILD";
    if std::env::var_os(CHILD).is_some() {
        let directory =
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("verification/sal-diagnostics");
        std::fs::create_dir_all(&directory).unwrap();
        let rdl = directory.join("input.rdl");
        windows_clang::clang()
            .input_text(
                r#"
                #define _Out_writes_bytes_to_opt_(capacity, written)
                void write_buffer(_Out_writes_bytes_to_opt_(capacity, written) void *buffer,
                    unsigned capacity, unsigned written);
                "#,
            )
            .args(["-x", "c", "--target=x86_64-pc-windows-msvc"])
            .namespace("Probe")
            .library("")
            .output(&rdl)
            .write()
            .unwrap();
        assert!(
            std::fs::read_to_string(rdl)
                .unwrap()
                .contains("#[size_param(1)]")
        );
        return;
    }
    let output = std::process::Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            "sal_written_lengths_are_reported_without_losing_buffer_extents",
            "--nocapture",
        ])
        .env(CHILD, "1")
        .output()
        .unwrap();
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(output.status.success(), "{stderr}");
    assert!(
        stderr.contains("unsupported SAL initialized/written length written"),
        "{stderr}"
    );
    assert!(stderr.contains("_Out_writes_bytes_to_opt_"), "{stderr}");
    assert!(
        stderr.contains("initialized/written length omitted"),
        "{stderr}"
    );
}

#[test]
fn sdk_style_sal_survives_declarations_architecture_merge_and_roundtrip() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let directory = root.join("verification/sal-contract");
    let config: serde_json::Value =
        serde_json::from_slice(&std::fs::read(root.join("out/toolchain.json")).unwrap()).unwrap();
    let reference = PathBuf::from(config["win32_metadata"].as_str().unwrap());
    std::fs::create_dir_all(&directory).unwrap();
    let mut merger = windows_metadata::merge::Merger::new();
    merger.reference(&reference);
    for (target, bits) in [
        ("i686-pc-windows-msvc", 1),
        ("x86_64-pc-windows-msvc", 2),
        ("aarch64-pc-windows-msvc", 4),
    ] {
        let rdl = directory.join(format!("{bits}.rdl"));
        windows_clang::clang()
            .input_text(
                r#"
                #define _In_
                #define _In_opt_
                #define _Out_opt_
                #define _Out_writes_z_(n)
                #define _Out_writes_bytes_to_opt_(n, used)
                #define _In_reads_bytes_opt_(n)
                #define _Inout_updates_bytes_(n)
                #define _Inout_updates_(n)
                #define _Out_writes_(n)
                #define _Out_writes_to_ptr_(end)
                typedef int (*onexit_fn)(void);
                double strtod(_In_ const char *string, _Out_opt_ char **end);
                onexit_fn _onexit(_In_opt_ onexit_fn function);
                int _ecvt_s(_Out_writes_z_(count) char *buffer, _In_ unsigned count);
                int memcpy_s(_Out_writes_bytes_to_opt_(capacity, count) void *dest,
                    _In_ unsigned capacity, _In_reads_bytes_opt_(count) const void *src,
                    _In_ unsigned count);
                void qsort(_Inout_updates_bytes_(count * width) void *base,
                    _In_ unsigned count, _In_ unsigned width);
                int _makepath_s(_Out_writes_z_(count) char *path, _In_ unsigned count,
                    _In_opt_ const char *drive);
                void elements(_Inout_updates_(count) int *items, _In_ unsigned count);
                void literal(_Out_writes_(0x10u) int *items);
                void octal(_Out_writes_(010) int *items);
                void indirect(_Out_writes_(*count) int *items, _In_ unsigned *count);
                void end_pointer(_Out_writes_to_ptr_(end) int *items, _In_ int *end);
                void unannotated(int value, char *pointer);
                "#,
            )
            .args(["-x", "c", &format!("--target={target}")])
            .namespace("Probe")
            .library("")
            .output(&rdl)
            .write()
            .unwrap();
        let source = std::fs::read_to_string(&rdl).unwrap();
        std::fs::write(&rdl, source.replace("#[library(\"\")]", "#[declaration]")).unwrap();
        let metadata = directory.join(format!("{bits}.winmd"));
        windows_rdl::reader()
            .input(&rdl)
            .input(root.join("declarations.rdl"))
            .reference(&reference)
            .output(&metadata)
            .write()
            .unwrap();
        check_sal(&Index::read(&metadata).unwrap());
        merger.arch_input(metadata, bits);
    }
    let merged = directory.join("merged.winmd");
    merger.output(&merged).merge().unwrap();
    let rdl = directory.join("roundtrip.rdl");
    windows_rdl::writer()
        .input(&merged)
        .output(&rdl)
        .write()
        .unwrap();
    let roundtrip = directory.join("roundtrip.winmd");
    windows_rdl::reader()
        .input(&rdl)
        .reference(&reference)
        .output(&roundtrip)
        .write()
        .unwrap();
    for path in [&merged, &roundtrip] {
        for bits in [1, 2, 4] {
            check_sal(&Index::new_for_architecture(
                vec![windows_metadata::reader::File::read(path).unwrap()],
                bits,
            ));
        }
    }
}

fn check_sal(index: &Index) {
    let apis = index.expect("Probe", "Apis");
    let input = ParamAttributes::In;
    let output = ParamAttributes::Out;
    let optional = ParamAttributes::Optional;
    for (name, expected) in [
        ("strtod", vec![input, output | optional]),
        ("_onexit", vec![input | optional]),
        ("_ecvt_s", vec![output, input]),
        (
            "memcpy_s",
            vec![output | optional, input, input | optional, input],
        ),
        ("qsort", vec![input | output, input, input]),
        ("_makepath_s", vec![output, input, input | optional]),
        ("elements", vec![input | output, input]),
        ("literal", vec![output]),
        ("octal", vec![output]),
        ("indirect", vec![output, input]),
        ("end_pointer", vec![output, input]),
        ("unannotated", vec![ParamAttributes(0), ParamAttributes(0)]),
    ] {
        let method = apis.methods().find(|method| method.name() == name).unwrap();
        let params: Vec<_> = method
            .params()
            .filter(|param| param.sequence() != 0)
            .collect();
        assert_eq!(
            params.iter().map(|param| param.flags()).collect::<Vec<_>>(),
            expected,
            "{name}"
        );
    }
    for (name, position, attribute, property, value) in [
        (
            "_ecvt_s",
            0,
            "NativeArrayInfoAttribute",
            "CountParamIndex",
            Value::I16(1),
        ),
        (
            "_makepath_s",
            0,
            "NativeArrayInfoAttribute",
            "CountParamIndex",
            Value::I16(1),
        ),
        (
            "memcpy_s",
            0,
            "MemorySizeAttribute",
            "BytesParamIndex",
            Value::I16(1),
        ),
        (
            "memcpy_s",
            2,
            "MemorySizeAttribute",
            "BytesParamIndex",
            Value::I16(3),
        ),
        (
            "elements",
            0,
            "NativeArrayInfoAttribute",
            "CountParamIndex",
            Value::I16(1),
        ),
        (
            "literal",
            0,
            "NativeArrayInfoAttribute",
            "CountConst",
            Value::I32(16),
        ),
        (
            "octal",
            0,
            "NativeArrayInfoAttribute",
            "CountConst",
            Value::I32(8),
        ),
    ] {
        let method = apis.methods().find(|method| method.name() == name).unwrap();
        let param = method
            .params()
            .filter(|param| param.sequence() != 0)
            .nth(position)
            .unwrap();
        assert_eq!(
            param.find_attribute(attribute).unwrap().value(),
            vec![(property.into(), value)],
            "{name}"
        );
    }
    for name in ["qsort", "indirect", "end_pointer"] {
        let method = apis.methods().find(|method| method.name() == name).unwrap();
        let param = method.params().find(|param| param.sequence() == 1).unwrap();
        assert!(
            param.find_attribute("MemorySizeAttribute").is_none(),
            "{name}"
        );
        assert!(
            param.find_attribute("NativeArrayInfoAttribute").is_none(),
            "{name}"
        );
    }
}
