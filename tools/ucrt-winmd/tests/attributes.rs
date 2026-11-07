use std::collections::BTreeSet;
use std::path::PathBuf;
use windows_metadata::{HasAttributes, Type, Value, reader::*};

const OFFICIAL: &str = "Windows.Win32.Foundation.Metadata";

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

#[test]
fn generated_attributes_resolve_to_their_owners_after_merging_and_roundtrip() {
    let config: serde_json::Value =
        serde_json::from_slice(&std::fs::read(root().join("out/toolchain.json")).unwrap()).unwrap();
    let official = Index::read(config["win32_metadata"].as_str().unwrap()).unwrap();
    for directory in ["out", "out/x86", "out/x64", "out/arm64"] {
        for name in ["UCRT.winmd", "UCRT.roundtrip.winmd"] {
            let path = root().join(directory).join(name);
            let index = Index::read(&path).unwrap();
            let mut seen = BTreeSet::new();
            for ty in index.types() {
                let attributes = ty
                    .attributes()
                    .chain(ty.fields().flat_map(|field| field.attributes()))
                    .chain(ty.methods().flat_map(|method| method.attributes()));
                for attribute in attributes {
                    let (namespace, signature) = match attribute.name() {
                        "NativeTypedefAttribute" => (OFFICIAL, vec![]),
                        "NativeEncodingAttribute" => (OFFICIAL, vec![Type::String]),
                        "NativeBitfieldAttribute" => {
                            (OFFICIAL, vec![Type::String, Type::I64, Type::I64])
                        }
                        "SupportedArchitectureAttribute" => {
                            (OFFICIAL, vec![Type::value_named(OFFICIAL, "Architecture")])
                        }
                        "DoesNotReturnAttribute" => ("System.Diagnostics.CodeAnalysis", vec![]),
                        "NativeAlignmentAttribute" => ("Winlex.Metadata", vec![Type::I32]),
                        "AlignmentAttribute" => {
                            panic!("legacy alignment attribute in {}", path.display())
                        }
                        _ => continue,
                    };
                    seen.insert(attribute.name().to_string());
                    assert_eq!(attribute.namespace(), namespace, "{}", path.display());
                    assert_eq!(attribute.ctor().signature(&[]).types, signature);
                    let MemberRefParent::TypeRef(reference) = attribute.ctor().parent() else {
                        panic!("expected constructor TypeRef");
                    };
                    if namespace == "Winlex.Metadata" {
                        assert!(matches!(reference.scope(), ResolutionScope::Module(_)));
                        let definition = index.expect(namespace, attribute.name());
                        assert!(definition.methods().any(|method| method.name() == ".ctor"
                            && method.signature(&[]).types == signature));
                        let values = attribute.value();
                        let Value::I32(alignment) = values[0].1 else {
                            panic!("invalid alignment argument")
                        };
                        assert!(alignment > 0 && (alignment as u32).is_power_of_two());
                    } else {
                        let ResolutionScope::AssemblyRef(assembly) = reference.scope() else {
                            panic!(
                                "external attribute points at current module in {}: {}",
                                path.display(),
                                attribute.name()
                            );
                        };
                        assert!(
                            index.get(namespace, attribute.name()).next().is_none(),
                            "copied external definition"
                        );
                        if namespace == OFFICIAL {
                            assert_eq!(assembly.name(), "Windows.Win32.winmd");
                            let definition = official.expect(namespace, attribute.name());
                            assert!(definition.methods().any(|method| method.name() == ".ctor"
                                && method.signature(&[]).types == signature));
                        } else {
                            assert_eq!(assembly.name(), "netstandard");
                            assert_eq!(assembly.version(), [2, 1, 0, 0]);
                            assert_eq!(
                                assembly.public_key_or_token(),
                                &[0xcc, 0x7b, 0x13, 0xff, 0xcd, 0x2d, 0xdd, 0x51]
                            );
                        }
                    }
                }
            }
            for required in [
                "NativeTypedefAttribute",
                "NativeEncodingAttribute",
                "NativeAlignmentAttribute",
                "DoesNotReturnAttribute",
                "NativeBitfieldAttribute",
            ] {
                assert!(
                    seen.contains(required),
                    "{required} missing in {}",
                    path.display()
                );
            }
            if directory != "out" {
                assert!(seen.contains("SupportedArchitectureAttribute"));
            }
        }
    }
}

#[test]
fn architecture_merge_keeps_distinct_native_alignments() {
    let config: serde_json::Value =
        serde_json::from_slice(&std::fs::read(root().join("out/toolchain.json")).unwrap()).unwrap();
    let reference = PathBuf::from(config["win32_metadata"].as_str().unwrap());
    let directory = root().join("verification/alignment-merge-contract");
    std::fs::create_dir_all(&directory).unwrap();
    let mut merger = windows_metadata::merge::Merger::new();
    merger.reference(&reference);
    for (bits, alignment) in [(1, 8), (2, 16), (4, 16)] {
        let path = directory.join(format!("{bits}.winmd"));
        windows_rdl::reader()
            .input_text(&format!(
                "#[win32] mod Probe {{ #[align({alignment})] struct Record {{ value: u32 }} }}"
            ))
            .input(root().join("declarations.rdl"))
            .reference(&reference)
            .output(&path)
            .write()
            .unwrap();
        merger.arch_input(path, bits);
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
        .input(rdl)
        .reference(reference)
        .output(&roundtrip)
        .write()
        .unwrap();
    for path in [&merged, &roundtrip] {
        for (bits, alignment, mask) in [(1, 8, 1), (2, 16, 6), (4, 16, 6)] {
            let index = Index::new_for_architecture(vec![File::read(path).unwrap()], bits);
            let record = index.expect("Probe", "Record");
            assert_eq!(record.arches(), mask);
            assert_eq!(
                record
                    .find_attribute("NativeAlignmentAttribute")
                    .unwrap()
                    .value(),
                vec![(String::new(), Value::I32(alignment))]
            );
        }
    }
}

#[test]
fn alignment_requires_positive_power_of_two_bytes_and_roundtrips_as_align() {
    let directory = root().join("verification/alignment-contract");
    std::fs::create_dir_all(&directory).unwrap();
    for alignment in ["0", "3", "-1", "2147483648"] {
        assert!(
            windows_rdl::reader()
                .input_text(&format!(
                    "#[win32] mod Probe {{ #[align({alignment})] struct Record {{ value: u8 }} }}"
                ))
                .input(root().join("declarations.rdl"))
                .output(directory.join("invalid.winmd"))
                .write()
                .is_err(),
            "accepted alignment {alignment}"
        );
    }
    let metadata = directory.join("valid.winmd");
    windows_rdl::reader()
        .input_text("#[win32] mod Probe { #[align(65536)] struct Record { value: u8 } }")
        .input(root().join("declarations.rdl"))
        .output(&metadata)
        .write()
        .unwrap();
    let rdl = directory.join("roundtrip.rdl");
    windows_rdl::writer()
        .input(&metadata)
        .output(&rdl)
        .write()
        .unwrap();
    assert!(
        std::fs::read_to_string(&rdl)
            .unwrap()
            .contains("#[align(65536)]")
    );
}
