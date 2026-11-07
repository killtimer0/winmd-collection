use windows_metadata::{HasAttributes, Type, Value};

#[test]
fn anonymous_callback_signatures_survive_rdl_and_arch_merge() {
    let directory =
        std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("verification/callback-contract");
    std::fs::create_dir_all(&directory).unwrap();
    let header = directory.join("callbacks.h");
    std::fs::write(
        &header,
        "int __cdecl atexit(void (__cdecl *callback)(void));\n\
         int __cdecl at_quick_exit(void (__cdecl *callback)(void));\n\
         int __cdecl register_callback(int (__cdecl *callback)(int, const void *));\n\
         int __cdecl indirect_callback(void (__cdecl ***callback)(void));\n\
         int __cdecl stdcall_callback(void (__stdcall *callback)(void));\n\
         int __cdecl fastcall_callback(void (__fastcall *callback)(void));\n",
    )
    .unwrap();
    let merged = directory.join("merged.winmd");
    let mut merger = windows_metadata::merge();
    for (target, arch) in [
        ("i686-pc-windows-msvc", 1),
        ("x86_64-pc-windows-msvc", 2),
        ("aarch64-pc-windows-msvc", 4),
    ] {
        let rdl = directory.join(format!("callbacks-{arch}.rdl"));
        let winmd = directory.join(format!("callbacks-{arch}.winmd"));
        windows_clang::clang()
            .inputs([&header])
            .args(["-x", "c", "-target", target])
            .namespace("CallbackTest")
            .library("ucrtbase")
            .output(&rdl)
            .write()
            .unwrap();
        windows_rdl::reader()
            .input(&rdl)
            .output(&winmd)
            .write()
            .unwrap();
        assert_callbacks(&winmd);
        merger.arch_input(&winmd, arch);
    }
    merger.output(&merged).merge().unwrap();
    assert_callbacks(&merged);

    let roundtrip_rdl = directory.join("roundtrip.rdl");
    let roundtrip_winmd = directory.join("roundtrip.winmd");
    windows_rdl::writer()
        .input(&merged)
        .output(&roundtrip_rdl)
        .write()
        .unwrap();
    windows_rdl::reader()
        .input(&roundtrip_rdl)
        .output(&roundtrip_winmd)
        .write()
        .unwrap();
    assert_callbacks(&roundtrip_winmd);
}

fn assert_callbacks(path: &std::path::Path) {
    let file = windows_metadata::reader::File::new(std::fs::read(path).unwrap()).unwrap();
    let index = windows_metadata::reader::Index::new(vec![file]);
    let apis = index.expect("CallbackTest", "Apis");
    for (name, return_type, params, pointers, abi) in [
        ("atexit", Type::Void, vec![], 0, 2),
        ("at_quick_exit", Type::Void, vec![], 0, 2),
        (
            "register_callback",
            Type::I32,
            vec![Type::I32, Type::PtrConst(Box::new(Type::Void), 1)],
            0,
            2,
        ),
        ("indirect_callback", Type::Void, vec![], 2, 2),
        ("stdcall_callback", Type::Void, vec![], 0, 1),
        ("fastcall_callback", Type::Void, vec![], 0, 5),
    ] {
        let method = apis.methods().find(|method| method.name() == name).unwrap();
        let signature = method.signature(&[]);
        assert_eq!(signature.return_type, Type::I32, "{name} return");
        let [ty] = signature.types.as_slice() else {
            panic!("{name} must have one callback parameter");
        };
        let ty = if pointers == 0 {
            ty
        } else {
            let Type::PtrMut(inner, depth) = ty else {
                panic!("{name} lost callback pointer layers: {ty:?}");
            };
            assert_eq!(*depth, pointers, "{name} callback pointer depth");
            inner
        };
        let Type::ClassName(callback) = ty else {
            panic!(
                "{name} must reference a callback, got {:?}",
                signature.types
            );
        };
        let callback = index.expect(&callback.namespace, &callback.name);
        let invoke = callback
            .methods()
            .find(|method| method.name() == "Invoke")
            .expect("callback Invoke");
        let signature = invoke.signature(&[]);
        assert_eq!(signature.return_type, return_type, "{name} callback return");
        assert_eq!(signature.types, params, "{name} callback parameters");
        let attribute = callback
            .find_attribute("UnmanagedFunctionPointerAttribute")
            .expect("callback ABI");
        let (_, Value::EnumValue(_, actual_abi)) = attribute.value().into_iter().next().unwrap()
        else {
            panic!("callback ABI enum");
        };
        assert_eq!(*actual_abi, Value::I32(abi), "{name} callback source ABI");
    }
}

#[test]
fn rejects_variadic_anonymous_callbacks() {
    let directory =
        std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("verification/callback-contract");
    std::fs::create_dir_all(&directory).unwrap();
    let header = directory.join("variadic.h");
    std::fs::write(
        &header,
        "void register_variadic(int (__cdecl *callback)(int, ...));",
    )
    .unwrap();
    let error = windows_clang::clang()
        .inputs([&header])
        .args(["-x", "c", "-target", "i686-pc-windows-msvc"])
        .namespace("CallbackTest")
        .library("ucrtbase")
        .output(directory.join("variadic.rdl"))
        .write()
        .expect_err("variadic callback cannot be emitted with a fixed signature");
    assert!(
        error
            .to_string()
            .contains("unsupported variadic anonymous callback"),
        "{error}"
    );
}
