use super::*;

#[derive(Debug)]
pub struct Callback {
    pub name: String,
    pub params: Vec<Param>,
    pub return_type: metadata::Type,
    /// Non-default source calling convention; `None` is the platform default.
    pub calling_convention: Option<CallingConvention>,
}

impl Callback {
    pub fn anonymous(function: &Type, parser: &mut Parser<'_>) -> metadata::Type {
        if function.is_variadic() {
            parser.unsupported_callback = Some(format!(
                "unsupported variadic anonymous callback: {}",
                function.spelling()
            ));
            return metadata::Type::Void;
        }
        let return_type = function.fn_result_type().to_type(parser);
        let params: Vec<_> = function
            .fn_arg_types()
            .into_iter()
            .enumerate()
            .map(|(index, ty)| Param {
                name: format!("arg{index}"),
                ty: ty.to_type(parser),
                annotation: ParamAnnotation::default(),
            })
            .collect();
        let calling_convention = function.fn_calling_convention(parser);
        let signature = format!(
            "{return_type:?}:{:?}:{calling_convention:?}",
            params.iter().map(|param| &param.ty).collect::<Vec<_>>()
        );
        let hash = signature.bytes().fold(0xcbf29ce484222325u64, |hash, byte| {
            (hash ^ u64::from(byte)).wrapping_mul(0x100000001b3)
        });
        let name = format!("__callback_{hash:016x}");
        let ty = metadata::Type::value_named(parser.namespace, &name);
        parser.pending_callbacks.push(Self {
            name,
            params,
            return_type,
            calling_convention,
        });
        ty
    }

    /// Parse a non-variadic function-pointer typedef as a callback.
    pub fn parse(cursor: Cursor, parser: &mut Parser<'_>) -> Result<Option<Self>, Error> {
        let name = cursor.name();
        if name.is_empty() {
            return Ok(None);
        }
        // Per-header mode keeps underscore callbacks because functions may reference them.
        if parser.header_root.is_none() && name.starts_with('_') {
            return Ok(None);
        }

        let underlying = cursor.typedef_underlying_type();

        let underlying = if underlying.kind() == CXType_Elaborated {
            underlying.underlying_type()
        } else {
            underlying
        };

        let Some(fn_type) = underlying.function_pointee() else {
            return Ok(None);
        };

        // Variadic callbacks are emitted later as opaque typedef aliases.
        if fn_type.is_variadic() {
            return Ok(None);
        }

        let return_type = fn_type.fn_result_type().to_type(parser);

        // Two-level typedefs carry parameter declarations on the referenced base typedef.
        let param_source = if cursor
            .children()
            .iter()
            .any(|c| c.kind() == CXCursor_ParmDecl)
        {
            cursor
        } else {
            cursor
                .children()
                .into_iter()
                .find(|c| c.kind() == CXCursor_TypeRef)
                .map(|c| c.referenced())
                .filter(|r| r.children().iter().any(|c| c.kind() == CXCursor_ParmDecl))
                .unwrap_or(cursor)
        };

        let source_name = param_source.name();
        let tokens = parser
            .tu
            .tokenize(parser.tu.to_expansion_range(param_source.extent()));

        // Use the shared SAL/MIDL path so callbacks match functions and COM methods.
        let midl_annotations =
            scan_method_param_annotations(&tokens, &source_name, parser.macro_defs);
        let params = parse_params(&param_source, &midl_annotations, parser);

        // clang erases x64 conventions from the type, so recover non-default ones from tokens.
        let calling_convention =
            detect_callback_calling_convention(&tokens, &source_name, parser.macro_defs).or_else(
                || (cursor.language() == CXLanguage_C).then_some(CallingConvention::Cdecl),
            );

        Ok(Some(Self {
            name,
            params,
            return_type,
            calling_convention,
        }))
    }

    pub fn write(&self, namespace: &str) -> Result<TokenStream, Error> {
        let name = write_ident(&self.name);

        let params = self.params.iter().map(|param| {
            let name = write_ident(&param.name);
            let ty = write_type(namespace, &param.ty);
            let attrs = param_attrs_for_annotation(&param.annotation, &param.ty);
            let const_attr = const_string_attribute(&param.ty);
            let unspecified = if !param.annotation.in_param && !param.annotation.out_param {
                quote! { #[unspecified] }
            } else {
                quote! {}
            };
            quote! { #(#attrs)* #const_attr #unspecified #name: #ty }
        });

        let return_type = match &self.return_type {
            metadata::Type::Void => quote! {},
            ty => {
                let const_attr = const_string_attribute(ty);
                let ty = write_type(namespace, ty);
                quote! { -> #const_attr #ty }
            }
        };

        // Bare `extern fn` encodes the platform default in the reader.
        let abi = match self.calling_convention {
            Some(CallingConvention::Cdecl) => quote! { "C" },
            Some(CallingConvention::Fastcall) => quote! { "fastcall" },
            Some(CallingConvention::Stdcall) | None => quote! {},
        };

        Ok(quote! {
            extern #abi fn #name(#(#params),*) #return_type;
        })
    }
}
