use super::*;

impl<'a> AssemblyRef<'a> {
    pub fn name(&self) -> &'a str {
        self.str(3)
    }

    pub fn version(&self) -> [u16; 4] {
        let version = self.file().u64(self.pos(), Self::TABLE, 0);
        [
            version as u16,
            (version >> 16) as u16,
            (version >> 32) as u16,
            (version >> 48) as u16,
        ]
    }

    pub fn public_key_or_token(&self) -> &'a [u8] {
        self.file().blob(self.pos(), Self::TABLE, 2)
    }
}

impl std::fmt::Debug for AssemblyRef<'_> {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        f.debug_tuple("AssemblyRef").field(&self.0).finish()
    }
}
