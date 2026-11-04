import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location("prepare", Path(__file__).resolve().parents[1] / "scripts/prepare-metadata.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class PreparationTests(unittest.TestCase):
    def test_generated_import_uses_verified_manifest_not_other_machine_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "generated"
            output.mkdir()
            (root / "sources").mkdir()
            (root / "tools/ucrt-winmd").mkdir(parents=True)
            (root / "tools/ucrt-winmd/LICENSE").write_bytes(b"license")
            (root / "sources/ucrt.json").write_text(json.dumps({"kind": "generated", "files": dict.fromkeys(("UCRT.winmd", "manifest.json", "LICENSE"), "0" * 64)}))
            data = b"generated metadata"
            (output / "UCRT.winmd").write_bytes(data)
            manifest = {"artifacts": [{"path": "out/UCRT.winmd", "sha256": hashlib.sha256(data).hexdigest()}],
                        "generation": [{"architecture": arch} for arch in ("x86", "x64", "arm64")],
                        "checks": {"contracts": "passed", "ast_audit_and_clippy": "passed"},
                        "toolchain": {"sdk_include": "SDK/10.0.26100.0", "msvc_include": "MSVC/14.51.36231/include"}}
            (output / "manifest.json").write_text(json.dumps(manifest))
            with patch.object(prepare, "ROOT", root), patch.object(prepare.subprocess, "check_output", return_value="revision\n"):
                prepare.import_ucrt(output)
                record = json.loads((root / "sources/ucrt.json").read_text())
                self.assertEqual(record["files"]["UCRT.winmd"], hashlib.sha256(data).hexdigest())
                self.assertEqual(record["generator_revision"], "revision")
                self.assertEqual(record["sdk_version"], "10.0.26100.0")
                (output / "UCRT.winmd").write_bytes(b"corrupt")
                with self.assertRaises(ValueError): prepare.import_ucrt(output)
                self.assertEqual((root / "artifacts/ucrt/UCRT.winmd").read_bytes(), data)

    def test_selected_members_verified_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "input.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("a", b"first")
                z.writestr("b", b"second")
            source = {"package": "p", "version": "1", "members": [
                {"member": "a", "file": "路径/a", "sha256": hashlib.sha256(b"first").hexdigest()},
                {"member": "b", "file": "b", "sha256": "0" * 64}]}
            with patch.object(prepare, "ROOT", root), patch.object(prepare, "download", return_value=archive):
                with self.assertRaises(ValueError): prepare.prepare("sample", source)
                self.assertFalse((root / "artifacts/sample").exists())
                source["members"][1]["sha256"] = hashlib.sha256(b"second").hexdigest()
                prepare.prepare("sample", source)
                self.assertEqual((root / "artifacts/sample/路径/a").read_bytes(), b"first")
                for bad in ("../escape", "C:/escape", "/escape", "路径/a"):
                    source["members"][1]["file"] = bad
                    with self.assertRaises(ValueError): prepare.prepare("sample", source)

    def test_invalid_cached_archive_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cache = root / "tmp/deps/p.1.nupkg"
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b"bad")
            with patch.object(prepare, "ROOT", root):
                with self.assertRaises(ValueError): prepare.download({"package": "p", "version": "1", "archive_sha256": "0" * 64})
            self.assertEqual(cache.read_bytes(), b"bad")

    def test_duplicate_member_must_match_selected_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "input.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("a", b"same")
                z.writestr("b", b"different")
            sha = hashlib.sha256(b"same").hexdigest()
            source = {"package": "p", "version": "1", "members": [{"member": "a", "file": "a", "sha256": sha}], "duplicate_member": {"member": "b", "sha256": sha}}
            with patch.object(prepare, "ROOT", root), patch.object(prepare, "download", return_value=archive):
                with self.assertRaises(ValueError): prepare.prepare("sample", source)
                self.assertFalse((root / "artifacts/sample").exists())


if __name__ == "__main__":
    unittest.main()
