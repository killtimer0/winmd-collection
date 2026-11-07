# Local declaration-mode extension

Based on windows-rdl 0.100.0, with its upstream license retained.

- `reader/item.rs`: recognize `#[declaration] extern ... fn` as a free function.
- `reader/fn.rs`: reject simultaneous library/declaration markers; emit declarations
  without PInvokeImpl or ImplMap. Method implementation flags are ECMA-335
  Native (0x0001), Unmanaged (0x0004) and ForwardRef (0x0010), with no method body.
- Store ABI in `Winlex.Metadata.NativeCallingConventionAttribute(String)`;
  include the attribute definition supplied in the generator's `declarations.rdl`.
- `writer/fn.rs`: recover the declaration marker and ABI when writing RDL from
  metadata without an ImplMap. Other missing-import functions still produce errors.
- Native typedef, encoding, bitfield and architecture attributes use official
  `Windows.Win32.Foundation.Metadata` definitions from explicit reference metadata.
  Architecture arguments use the official enum; attribute definitions retain their
  own architecture markers on round trips.
- `#[noreturn]` maps to `System.Diagnostics.CodeAnalysis.DoesNotReturnAttribute`.
- `#[align(...)]` maps to generator-owned
  `Winlex.Metadata.NativeAlignmentAttribute(Int32 alignment)`, defined in
  `declarations.rdl`. Alignment is a positive power of two in bytes, not packing.
- `reader/param.rs` and `writer/mod.rs`: support `#[unspecified]` parameters so
  absent direction flags remain absent on round trips. Declaration mode disables
  type-based direction inference; callbacks receive explicit unspecified markers
  from the local frontend when they have no direction annotation.
  The writer retains explicit declaration parameter directions rather than
  relying on the reader's disabled inference.
- `reader/struct.rs` and `writer/struct.rs`: encode anonymous nested records with
  parent-scoped TypeRefs and retain them as inline records on round trips.
- `formatter/mod.rs`: return tokenization errors to callers instead of formatting
  invalid input as empty output. Input enumeration and output cleanup propagate
  filesystem errors.

This convention is intended for query-only metadata. It is not an upstream format
extension and does not claim CLR executability. The original library/import mode
remains available.
