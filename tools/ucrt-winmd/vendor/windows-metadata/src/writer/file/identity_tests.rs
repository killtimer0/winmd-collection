use super::*;

fn read(file: File) -> reader::File {
    reader::File::new(file.into_stream()).unwrap()
}

fn definition(name: &str, ty: &str, version: [u16; 4], flags: AssemblyFlags) -> reader::File {
    let mut file = File::new(name);
    file.records.Assembly[0].MajorVersion = version[0];
    file.records.Assembly[0].MinorVersion = version[1];
    file.records.Assembly[0].BuildNumber = version[2];
    file.records.Assembly[0].RevisionNumber = version[3];
    file.records.Assembly[0].Flags = flags;
    file.records.Assembly[0].Culture = file.strings.insert("zh-Hans").0;
    file.records.Assembly[0].PublicKey = file.blobs.insert(&[1, 3, 5, 7, 9]).0;
    file.TypeDef(
        "External",
        ty,
        TypeDefOrRef::default(),
        TypeAttributes::Public,
    );
    read(file)
}

fn assert_identity(
    index: &reader::Index,
    ty: &str,
    name: &str,
    version: [u16; 4],
    flags: AssemblyFlags,
) {
    let identity = index.reference_assembly("External", ty).unwrap();
    assert_eq!(identity.name, name);
    assert_eq!(
        identity.version,
        u64::from(version[0])
            | (u64::from(version[1]) << 16)
            | (u64::from(version[2]) << 32)
            | (u64::from(version[3]) << 48)
    );
    assert_eq!(identity.flags, flags);
    assert_eq!(identity.culture, "zh-Hans");
    assert_eq!(identity.public_key_or_token, &[1, 3, 5, 7, 9]);
}

#[test]
fn external_definition_identity_survives_generation_and_reference_copying() {
    for (version, flags) in [
        ([0, 0, 0, 0], AssemblyFlags(1)),
        ([2, 4, 6, 8], AssemblyFlags(0x201)),
    ] {
        let source = reader::Index::new(vec![definition(
            "Official.winmd",
            "Attribute",
            version,
            flags,
        )]);
        let mut generated = File::new("Generated.winmd");
        generated.set_reference(source);
        generated.TypeRef("External", "Attribute");
        let generated = reader::Index::new(vec![read(generated)]);
        assert_identity(&generated, "Attribute", "Official.winmd", version, flags);

        let mut copied = File::new("Copied.winmd");
        copied.set_reference(generated);
        copied.TypeRef("External", "Attribute");
        assert_identity(
            &reader::Index::new(vec![read(copied)]),
            "Attribute",
            "Official.winmd",
            version,
            flags,
        );
    }
}

#[test]
fn assembly_references_do_not_collapse_same_name_different_identities() {
    let reference = reader::Index::new(vec![
        definition("Same.winmd", "First", [1, 2, 3, 4], AssemblyFlags(1)),
        definition("Same.winmd", "Second", [5, 6, 7, 8], AssemblyFlags(0x201)),
    ]);
    let mut output = File::new("Output.winmd");
    output.set_reference(reference);
    output.TypeRef("External", "First");
    output.TypeRef("External", "Second");
    let output = reader::Index::new(vec![read(output)]);
    assert_identity(
        &output,
        "First",
        "Same.winmd",
        [1, 2, 3, 4],
        AssemblyFlags(1),
    );
    assert_identity(
        &output,
        "Second",
        "Same.winmd",
        [5, 6, 7, 8],
        AssemblyFlags(0x201),
    );
}

#[test]
fn actual_definition_overrides_stale_inherited_identity() {
    let mut stale = File::new("Consumer.winmd");
    stale.set_reference(reader::Index::new(vec![definition(
        "Official.winmd",
        "Attribute",
        [255; 4],
        AssemblyFlags::WindowsRuntime,
    )]));
    stale.TypeRef("External", "Attribute");
    let mut official = File::new("Official.winmd");
    official.records.Assembly[0] = rec::Assembly {
        Name: official.strings.insert("Official.winmd"),
        ..Default::default()
    };
    official.TypeDef(
        "External",
        "Attribute",
        TypeDefOrRef::default(),
        TypeAttributes::Public,
    );
    let mut output = File::new("Output.winmd");
    output.set_reference(reader::Index::new(vec![read(stale), read(official)]));
    output.TypeRef("External", "Attribute");
    let output = reader::Index::new(vec![read(output)]);
    let identity = output.reference_assembly("External", "Attribute").unwrap();
    assert_eq!(identity.name, "Official.winmd");
    assert_eq!(identity.version, 0);
    assert_eq!(identity.flags, AssemblyFlags(0));
    assert_eq!(identity.culture, "");
    assert!(identity.public_key_or_token.is_empty());
}

#[test]
fn inherited_reference_retains_token_culture_and_hash() {
    let mut source = File::new("Consumer.winmd");
    let record = rec::AssemblyRef {
        Name: source.strings.insert("netstandard"),
        MajorVersion: 2,
        MinorVersion: 1,
        PublicKeyOrToken: source.blobs.insert(&[11, 22, 33, 44, 55, 66, 77, 88]),
        Culture: source.strings.insert("en-US").0,
        HashValue: source.blobs.insert(&[9, 8, 7]).0,
        ..Default::default()
    };
    let assembly = source.insert_assembly_ref(record);
    source.records.TypeRef.push(rec::TypeRef {
        TypeName: source.strings.insert("Attribute"),
        TypeNamespace: source.strings.insert("External"),
        ResolutionScope: ResolutionScope::AssemblyRef(assembly),
    });
    let mut output = File::new("Output.winmd");
    output.set_reference(reader::Index::new(vec![read(source)]));
    output.TypeRef("External", "Attribute");
    let output = reader::Index::new(vec![read(output)]);
    let identity = output.reference_assembly("External", "Attribute").unwrap();
    assert_eq!(identity.name, "netstandard");
    assert_eq!(identity.version, 2 | (1 << 16));
    assert_eq!(identity.flags, AssemblyFlags(0));
    assert_eq!(identity.culture, "en-US");
    assert_eq!(
        identity.public_key_or_token,
        &[11, 22, 33, 44, 55, 66, 77, 88]
    );
    assert_eq!(identity.hash_value, &[9, 8, 7]);
}
