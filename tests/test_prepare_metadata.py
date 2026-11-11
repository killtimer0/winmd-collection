import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
spec = importlib.util.spec_from_file_location("prepare", Path(__file__).resolve().parents[1] / "scripts/prepare-metadata.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class PreparationTests(unittest.TestCase):
    def test_merge_publishes_only_aggregate_and_licenses_after_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            (root / "sources").mkdir()
            sdk = root / "SDK"
            metadata = sdk / "UnionMetadata/10.0.10/Windows.winmd"
            metadata.parent.mkdir(parents=True)
            metadata.write_bytes(b"system metadata")
            tool = sdk / "bin/10.0.10/x64/mdmerge.exe"
            tool.parent.mkdir(parents=True)
            tool.write_bytes(b"tool")
            archive = root / "package.zip"
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("component", b"component")
                z.writestr("license", b"license")
                z.writestr("webview", b"reference")
            package = {"members": [
                {"member": "component", "file": "Microsoft.UI.winmd", "sha256": prepare.digest(b"component")},
                {"member": "license", "file": "licenses/winui/license.txt", "sha256": prepare.digest(b"license")}]}
            webview = {"members": [{"member": "webview", "file": "Microsoft.Web.WebView2.Core.winmd", "sha256": prepare.digest(b"reference")}]}
            record = root / "sources/winui.json"
            source = {"kind": "merged", "packages": [package], "files": {}}
            record.write_text(json.dumps(source))
            output = root / "artifacts/Microsoft.winmd"
            prepare.write_files({output: b"previous"})

            def merge(command, check):
                self.assertTrue(check)
                self.assertEqual(command[0], str(tool))
                inputs = Path(command[command.index("-i") + 1])
                self.assertEqual((inputs / "Microsoft.UI.winmd").read_bytes(), b"component")
                self.assertEqual(list(inputs.glob("*.winmd")), [inputs / "Microsoft.UI.winmd"])
                self.assertEqual((inputs.parent / "references/Microsoft.Web.WebView2.Core.winmd").read_bytes(), b"reference")
                destination = Path(command[command.index("-o") + 1])
                prepare.write_files({destination / "Microsoft.winmd": b"merged"})

            with patch.object(prepare, "ROOT", root), patch.object(prepare, "find_windows_winmd", return_value=metadata), patch.object(prepare, "download", return_value=archive):
                before = record.read_bytes()
                for failure in (prepare.subprocess.CalledProcessError(2, "mdmerge"), None):
                    with patch.object(prepare.subprocess, "run", side_effect=failure):
                        with self.assertRaises((prepare.subprocess.CalledProcessError, FileNotFoundError)):
                            prepare.merge_winui(source, webview)
                    self.assertEqual(record.read_bytes(), before)
                    self.assertEqual(output.read_bytes(), b"previous")
                with patch.object(prepare.subprocess, "run", side_effect=merge):
                    prepare.merge_winui(source, webview)
                self.assertEqual(output.read_bytes(), b"merged")
                self.assertEqual(set(json.loads(record.read_bytes())["files"]), {"Microsoft.winmd", "licenses/winui/license.txt"})
                self.assertEqual(list((root / "artifacts").glob("*.winmd")), [output])
                self.assertEqual(list((root / "tmp").iterdir()), [])

    def test_generated_import_preserves_generation_provenance_not_importing_head(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "generated"
            output.mkdir()
            (root / "sources").mkdir()
            (root / "tools/ucrt-winmd").mkdir(parents=True)
            (root / "tools/ucrt-winmd/LICENSE").write_bytes(b"license")
            (root / "sources/ucrt.json").write_text(json.dumps({"kind": "generated", "source_inputs": [{"path": "stale"}], "metadata_references": [{"path": "stale"}], "files": dict.fromkeys(("UCRT.winmd", "licenses/ucrt/generator-LICENSE"), "0" * 64)}))
            data = b"generated metadata"
            (output / "UCRT.winmd").write_bytes(data)
            manifest = {"artifacts": [{"path": "out/UCRT.winmd", "sha256": hashlib.sha256(data).hexdigest()}],
                        "generator_revision": "generation-revision",
                        "source_inputs": [{"path": "main.h", "sha256": prepare.digest(b"old source")}],
                        "metadata_references": [{"path": "original/Windows.Win32.winmd", "sha256": prepare.digest(b"reference")}],
                        "generation": [{"architecture": arch} for arch in ("x86", "x64", "arm64")],
                        "checks": {"contracts": "passed", "ast_audit_and_clippy": "passed"},
                        "toolchain": {"sdk_include": "SDK/10.0.26100.0", "msvc_include": "MSVC/14.51.36231/include"}}
            (output / "manifest.json").write_text(json.dumps(manifest))
            (root / "tools/ucrt-winmd/main.h").write_bytes(b"new source")
            with patch.object(prepare, "ROOT", root), patch.object(prepare.subprocess, "check_output", side_effect=AssertionError("Import must not query current HEAD")):
                prepare.import_ucrt(output)
                record = json.loads((root / "sources/ucrt.json").read_text())
                self.assertEqual(record["files"]["UCRT.winmd"], hashlib.sha256(data).hexdigest())
                self.assertEqual(record["generator_revision"], "generation-revision")
                self.assertEqual(record["sdk_version"], "10.0.26100.0")
                self.assertEqual(record["generation_manifest_sha256"], hashlib.sha256((output / "manifest.json").read_bytes()).hexdigest())
                self.assertEqual((root / "artifacts/licenses/ucrt/generator-LICENSE").read_bytes(), b"license")
                self.assertNotIn("source_inputs", record)
                self.assertNotIn("metadata_references", record)
                self.assertEqual(set(record["files"]), {"UCRT.winmd", "licenses/ucrt/generator-LICENSE"})
                self.assertFalse((root / "artifacts/manifest.json").exists())
                before = (root / "sources/ucrt.json").read_bytes()
                for name in ("generator_revision", "source_inputs", "metadata_references"):
                    incomplete = dict(manifest)
                    del incomplete[name]
                    (output / "manifest.json").write_text(json.dumps(incomplete))
                    with self.subTest(missing=name), self.assertRaisesRegex(ValueError, "missing generation provenance"):
                        prepare.import_ucrt(output)
                    self.assertEqual((root / "sources/ucrt.json").read_bytes(), before)
                (output / "manifest.json").write_text(json.dumps(manifest))
                (output / "UCRT.winmd").write_bytes(b"corrupt")
                with self.assertRaises(ValueError): prepare.import_ucrt(output)
                self.assertEqual((root / "artifacts/UCRT.winmd").read_bytes(), data)

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
                self.assertFalse((root / "artifacts").exists())
                source["members"][1]["sha256"] = hashlib.sha256(b"second").hexdigest()
                prepare.prepare("sample", source)
                self.assertEqual((root / "artifacts/路径/a").read_bytes(), b"first")
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
                self.assertFalse((root / "artifacts").exists())


class SDKPreparationTests(unittest.TestCase):
    def setUp(self):
        temp_root = prepare.ROOT / "tmp"
        temp_root.mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.sdk_root = self.root / "SDK 路径 with spaces"
        (self.root / "sources").mkdir()
        self.record = self.root / "sources/winrt.json"
        self.record.write_text(json.dumps({"kind": "sdk", "files": {"Windows.winmd": "0" * 64}}))
        root_patch = patch.object(prepare, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        environment = patch.dict(os.environ, {"WindowsSdkDir": str(self.sdk_root)})
        environment.start()
        self.addCleanup(environment.stop)

    def sdk(self, version, data):
        include = self.sdk_root / "Include" / version
        (include / "ucrt").mkdir(parents=True)
        (include / "ucrt/stdio.h").write_bytes(b"")
        (include / "shared").mkdir()
        (include / "shared/sdkddkver.h").write_bytes(b"")
        metadata = self.sdk_root / "UnionMetadata" / version / "Windows.winmd"
        metadata.parent.mkdir(parents=True)
        metadata.write_bytes(data)
        return include, metadata

    def test_shared_sdk_discovery_and_explicit_selection(self):
        older_include, older = self.sdk("10.0.9", b"older")
        _, newer = self.sdk("10.0.10", b"newer")
        (self.sdk_root / "Include/10.0.11").mkdir()
        self.assertEqual(prepare.find_windows_winmd(), newer)
        self.assertEqual(prepare.find_windows_winmd(older_include), older)

    def test_facade_is_not_used_when_sdk_metadata_is_missing(self):
        include, metadata = self.sdk("10.0.10", b"metadata")
        facade = metadata.parent / "Facade/Windows.winmd"
        facade.parent.mkdir(parents=True)
        metadata.replace(facade)
        with self.assertRaises(ValueError):
            prepare.find_windows_winmd(include)

    def test_import_records_current_sdk_hash_and_refreshes_changed_input(self):
        include, metadata = self.sdk("10.0.10", b"first SDK metadata")
        for data in (b"first SDK metadata", b"updated SDK metadata"):
            metadata.write_bytes(data)
            prepare.import_winrt(include)
            record = json.loads(self.record.read_text())
            self.assertEqual(record, {
                "kind": "sdk", "sdk_version": "10.0.10",
                "sdk_member": "UnionMetadata/10.0.10/Windows.winmd",
                "files": {"Windows.winmd": hashlib.sha256(data).hexdigest()},
            })
            self.assertEqual((self.root / "artifacts/Windows.winmd").read_bytes(), data)
            self.assertFalse((self.root / "artifacts/sources").exists())

    def test_missing_sdk_leaves_source_record_unchanged(self):
        record = self.record.read_bytes()
        with self.assertRaises(prepare.subprocess.CalledProcessError):
            prepare.import_winrt()
        self.assertEqual(self.record.read_bytes(), record)
        self.assertFalse((self.root / "artifacts").exists())


if __name__ == "__main__":
    unittest.main()
