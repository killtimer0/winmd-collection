use super::*;

#[test]
fn nested_pointer_qualifiers_arrays_and_references_roundtrip() {
    let types = [
        Type::PtrMut(Box::new(Type::PtrConst(Box::new(Type::I32), 1)), 1),
        Type::PtrConst(Box::new(Type::PtrMut(Box::new(Type::I32), 1)), 1),
        Type::PtrConst(Box::new(Type::I32), 3),
        Type::PtrMut(Box::new(Type::Void), 1),
        Type::Array(Box::new(Type::PtrConst(Box::new(Type::I32), 2))),
        Type::RefMut(Box::new(Type::PtrConst(Box::new(Type::I32), 1))),
        Type::RefConst(Box::new(Type::PtrMut(Box::new(Type::I32), 1))),
        Type::ArrayFixed(Box::new(Type::PtrConst(Box::new(Type::I32), 1)), 7),
    ];
    let mut file = File::new("Qualifier.winmd");
    file.TypeDef(
        "Probe",
        "Record",
        TypeDefOrRef::default(),
        TypeAttributes::Public,
    );
    for (position, ty) in types.iter().enumerate() {
        file.Field(&format!("field{position}"), ty, FieldAttributes::Public);
    }
    let index = reader::Index::new(vec![reader::File::new(file.into_stream()).unwrap()]);
    let actual: Vec<_> = index
        .expect("Probe", "Record")
        .fields()
        .map(|f| f.ty())
        .collect();
    assert_eq!(actual, types);
    let identity = index
        .reference_assembly("System.Runtime.CompilerServices", "IsConst")
        .unwrap();
    assert_eq!(identity.name, "mscorlib");
    assert_eq!(identity.version, 4);
    assert_eq!(
        identity.public_key_or_token,
        &[0xB7, 0x7A, 0x5C, 0x56, 0x19, 0x34, 0xE0, 0x89]
    );
}

#[test]
fn each_const_pointer_level_has_its_own_modifier() {
    let mut file = File::new("Qualifier.winmd");
    let mut signature = vec![];
    file.Type(&Type::PtrConst(Box::new(Type::I32), 2), &mut signature);
    assert_eq!(signature.len(), 7);
    assert_eq!(signature[0], ELEMENT_TYPE_CMOD_REQD);
    assert_eq!(signature[2], ELEMENT_TYPE_PTR);
    assert_eq!(&signature[..3], &signature[3..6]);
    assert_eq!(signature[6], ELEMENT_TYPE_I4);
}
