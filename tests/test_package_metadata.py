import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location("package", Path(__file__).resolve().parents[1] / "scripts/package-metadata.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "sources"
        self.directory = self.root / "artifacts/sample"
        self.source.mkdir()
        (self.directory / "sources").mkdir(parents=True)
        self.record = {"members": [{"file": "data.winmd", "sha256": hashlib.sha256(b"good").hexdigest()}]}
        self.write_record()
        (self.directory / "data.winmd").write_bytes(b"good")
        self.patches = (patch.object(package, "ROOT", self.root), patch.object(package, "SOURCES", ("sample",)))
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def write_record(self):
        text = json.dumps(self.record)
        (self.source / "sample.json").write_text(text, encoding="utf-8")
        (self.directory / "sources/sample.json").write_text(text, encoding="utf-8")

    def test_corrupt_output_preserves_existing_zip(self):
        zip_path = self.root / "artifacts/sample.zip"
        zip_path.write_bytes(b"existing")
        (self.directory / "data.winmd").write_bytes(b"corrupt")
        with self.assertRaises(ValueError): package.main()
        self.assertEqual(zip_path.read_bytes(), b"existing")

    def test_stale_files_excluded_and_all_hashes_match(self):
        (self.directory / "source.json").write_text("stale")
        package.main()
        zip_path = self.root / "artifacts/sample.zip"
        with zipfile.ZipFile(zip_path) as archive:
            names = set(archive.namelist())
            self.assertEqual(names, {"sample/data.winmd", "sample/sources/sample.json", "sample/SHA256SUMS"})
            lines = archive.read("sample/SHA256SUMS").decode().splitlines()
            self.assertEqual(len(lines), len(names) - 1)
            for line in lines:
                sha, path = line.split("  ", 1)
                self.assertEqual(sha, hashlib.sha256(archive.read("sample/" + path)).hexdigest())
        self.assertEqual((self.root / "artifacts/SHA256SUMS").read_text().strip(), hashlib.sha256(zip_path.read_bytes()).hexdigest() + "  sample.zip")
        self.assertTrue((self.directory / "source.json").exists())

    def test_collision_and_provenance_mismatch_rejected(self):
        self.record["members"].append({"file": "DATA.winmd", "sha256": "0" * 64})
        self.write_record()
        with self.assertRaises(ValueError): package.main()
        self.record["members"].pop()
        self.write_record()
        (self.directory / "sources/sample.json").write_text("{}")
        with self.assertRaises(ValueError): package.main()

    def test_sdk_inventory_is_packaged_and_checked_against_recorded_hash(self):
        self.record = {
            "kind": "sdk", "sdk_version": "10.0.10",
            "sdk_member": "UnionMetadata/10.0.10/Windows.winmd",
            "files": {"data.winmd": hashlib.sha256(b"good").hexdigest()},
        }
        self.write_record()
        package.main()
        zip_path = self.root / "artifacts/sample.zip"
        with zipfile.ZipFile(zip_path) as archive:
            self.assertEqual(archive.read("sample/data.winmd"), b"good")
            self.assertEqual(json.loads(archive.read("sample/sources/sample.json")), self.record)
        previous = zip_path.read_bytes()
        (self.directory / "data.winmd").write_bytes(b"corrupt")
        with self.assertRaises(ValueError): package.main()
        self.assertEqual(zip_path.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
