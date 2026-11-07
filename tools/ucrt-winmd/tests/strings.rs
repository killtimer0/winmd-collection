use std::path::PathBuf;
use windows_metadata::{HasAttributes, Type, reader::Index};

#[test]
fn official_strings_and_c_qualifiers_survive_roundtrip() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let directory = root.join("verification/string-qualifier-contract");
    let config: serde_json::Value =
        serde_json::from_slice(&std::fs::read(root.join("out/toolchain.json")).unwrap()).unwrap();
    let reference = PathBuf::from(config["win32_metadata"].as_str().unwrap());
    std::fs::create_dir_all(&directory).unwrap();
    windows_clang::clang()
        .input_text(
            r#"
            #define _In_
            typedef char *PSTR;
            typedef const char *PCSTR;
            typedef unsigned short *PWSTR;
            typedef const unsigned short *PCWSTR;
            typedef PCSTR (__cdecl *StringCallback)(PCSTR text);
            struct Strings { PSTR writable; PCSTR readonly; PCWSTR wide; PCSTR *indirect; PCSTR array[2]; };
            PCSTR strings(_In_ PSTR writable, PCSTR readonly, PWSTR wide, PCWSTR wide_readonly);
            void qualifiers(_In_ int *mutable_input, const int **inner_const,
                int *const *outer_const, const int *const *both_const,
                PCSTR *indirect);
            "#,
        )
        .args(["-x", "c", "--target=x86_64-pc-windows-msvc"])
        .namespace("Probe")
        .library("probe.dll")
        .output(directory.join("input.rdl"))
        .write()
        .unwrap();
    for (input, output) in [
        ("input.rdl", "first.winmd"),
        ("roundtrip.rdl", "second.winmd"),
    ] {
        windows_rdl::reader()
            .input(directory.join(input))
            .reference(&reference)
            .output(directory.join(output))
            .write()
            .unwrap();
        check(&Index::read(directory.join(output)).unwrap());
        windows_rdl::writer()
            .input(directory.join(output))
            .output(directory.join("roundtrip.rdl"))
            .write()
            .unwrap();
    }
}

fn check(index: &Index) {
    let narrow = Type::value_named("Windows.Win32.Foundation", "PSTR");
    let wide = Type::value_named("Windows.Win32.Foundation", "PWSTR");
    for name in ["PSTR", "PCSTR", "PWSTR", "PCWSTR"] {
        assert!(
            index.get("Probe", name).next().is_none(),
            "local wrapper {name}"
        );
    }
    let strings = index
        .expect("Probe", "Apis")
        .methods()
        .find(|m| m.name() == "strings")
        .unwrap();
    let signature = strings.signature(&[]);
    assert_eq!(signature.return_type, narrow);
    assert_eq!(
        signature.types,
        vec![narrow.clone(), narrow.clone(), wide.clone(), wide.clone()]
    );
    let params = strings.params_by_sequence(4).unwrap();
    assert!(
        params
            .return_param()
            .unwrap()
            .has_attribute("ConstAttribute")
    );
    for (param, expected) in params.params().iter().zip([false, true, false, true]) {
        assert_eq!(param.unwrap().has_attribute("ConstAttribute"), expected);
    }
    let record = index.expect("Probe", "Strings");
    let callback = index.expect("Probe", "StringCallback");
    let invoke = callback.methods().find(|m| m.name() == "Invoke").unwrap();
    assert_eq!(invoke.signature(&[]).return_type, narrow);
    assert_eq!(invoke.signature(&[]).types, vec![narrow.clone()]);
    let callback_params = invoke.params_by_sequence(1).unwrap();
    assert!(
        callback_params
            .return_param()
            .unwrap()
            .has_attribute("ConstAttribute")
    );
    assert!(
        callback_params.params()[0]
            .unwrap()
            .has_attribute("ConstAttribute")
    );
    for (name, ty, constant) in [
        ("writable", narrow.clone(), false),
        ("readonly", narrow, true),
        ("wide", wide, true),
    ] {
        let field = record.fields().find(|f| f.name() == name).unwrap();
        assert_eq!(field.ty(), ty);
        assert_eq!(field.has_attribute("ConstAttribute"), constant);
    }
    assert_eq!(
        record.fields().find(|f| f.name() == "array").unwrap().ty(),
        Type::ArrayFixed(Box::new(Type::PtrConst(Box::new(Type::I8), 1)), 2)
    );
    let qualifiers = index
        .expect("Probe", "Apis")
        .methods()
        .find(|m| m.name() == "qualifiers")
        .unwrap();
    assert_eq!(
        qualifiers.signature(&[]).types,
        vec![
            Type::PtrMut(Box::new(Type::I32), 1),
            Type::PtrMut(Box::new(Type::PtrConst(Box::new(Type::I32), 1)), 1),
            Type::PtrConst(Box::new(Type::PtrMut(Box::new(Type::I32), 1)), 1),
            Type::PtrConst(Box::new(Type::I32), 2),
            Type::PtrMut(Box::new(Type::PtrConst(Box::new(Type::I8), 1)), 1),
        ]
    );
}
