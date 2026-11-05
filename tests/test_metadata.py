import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import metadata


class MetadataTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root / "sources").mkdir()
        self.output = self.root / "artifacts"
        self.data = {self.output / "data.winmd": b"metadata", self.output / "licenses/sample/license.txt": b"license"}
        metadata.write_files(self.data)
        self.record = {"package": "Sample.Package", "version": "1.2", "url": "https://example.com/sample.nupkg",
                       "archive_sha256": "a" * 64,
                       "members": [{"file": p.relative_to(self.output).as_posix(), "sha256": metadata.digest(data)} for p, data in self.data.items()]}
        p = patch.dict(metadata.SOURCES, {"sample": ("query", ())}, clear=True)
        p.start()
        self.addCleanup(p.stop)

    def collect(self):
        (self.root / "sources/sample.json").write_text(json.dumps(self.record), encoding="utf-8")
        sources = metadata.read_sources(self.root)
        entries, groups = metadata.collect(self.root, sources)
        metadata.write_summary(self.root, sources, entries)
        return groups

    def test_inventory_grouping_sources_and_hashes(self):
        extra_path = self.output / "extra.winmd"
        extra_path.write_bytes(b"extra")
        extra = dict(self.record, output="sample", members=[{"file": "extra.winmd", "sha256": metadata.digest(b"extra")}])
        (self.root / "sources/extra.json").write_text(json.dumps(extra))
        unrelated = self.output / "unrelated.winmd"
        unrelated.write_bytes(b"keep")
        self.assertEqual(set(self.collect()["sample"]), {self.output / "data.winmd", extra_path})
        inventory = (self.output / "SHA256SUMS").read_text().splitlines()
        self.assertEqual(len(inventory), 5)
        for line in inventory:
            digest, name = line.split("  ", 1)
            self.assertEqual(digest, metadata.digest((self.output / name).read_bytes()))
        sources = (self.output / "SOURCES.md").read_text(encoding="utf-8")
        for text in ("Sample.Package 1.2", self.record["url"], self.record["archive_sha256"], "data.winmd", "licenses/sample/license.txt"):
            self.assertIn(text, sources)
        self.assertEqual(unrelated.read_bytes(), b"keep")
        self.assertNotIn("unrelated.winmd", "\n".join(inventory))

    def test_corrupt_output_preserves_summary(self):
        self.collect()
        names = ("SOURCES.md", "SHA256SUMS", "licenses/README.md")
        previous = {name: (self.output / name).read_bytes() for name in names}
        (self.output / "data.winmd").write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            self.collect()
        for name, data in previous.items():
            self.assertEqual((self.output / name).read_bytes(), data)

    def test_unsafe_reserved_and_colliding_paths(self):
        for names in (["../escape"], ["C:/escape"], ["/escape"], ["licenses\\escape"], ["."],
                      ["SOURCES.md"], ["SHA256SUMS"], ["licenses/README.md"],
                      ["a", "a"], ["a", "A"], ["a", "a/b"], ["a/b", "a"]):
            with self.subTest(names=names), self.assertRaises(ValueError):
                metadata.output_paths(self.output, names)
        other = dict(self.record, output="sample")
        (self.root / "sources/other.json").write_text(json.dumps(other))
        with self.assertRaisesRegex(ValueError, "Colliding output path"):
            self.collect()

    def test_sdk_generated_provenance_and_required_groups(self):
        files = {"data.winmd": metadata.digest(b"metadata")}
        for record, expected in [
            ({"kind": "sdk", "sdk_version": "10.0.10", "sdk_member": "UnionMetadata/10.0.10/Windows.winmd"}, [metadata.SDK_URL, "10.0.10", "UnionMetadata/10.0.10/Windows.winmd"]),
            ({"kind": "generated", "generator_revision": "revision", "sdk_version": "10.0.10", "msvc_version": "14.1",
              "architectures": ["x86", "x64", "arm64"], "generation_manifest_sha256": "b" * 64, "constraints": "Redistribution unconfirmed."},
             ["revision", "14.1", "x86, x64, arm64", "b" * 64, "Redistribution unconfirmed."]),
        ]:
            self.record = dict(record, files=files)
            self.assertEqual(self.collect()["sample"], [self.output / "data.winmd"])
            sources = (self.output / "SOURCES.md").read_text(encoding="utf-8")
            for text in expected:
                self.assertIn(text, sources)
        with patch.dict(metadata.SOURCES, {"missing": ("query", ())}):
            with self.assertRaisesRegex(ValueError, "Missing metadata records"):
                self.collect()

    def test_failed_replace_preserves_file_and_removes_partial(self):
        path = self.output / "data.winmd"
        with patch.object(Path, "replace", side_effect=OSError("failed")):
            with self.assertRaises(OSError):
                metadata.write_files({path: b"new"})
        self.assertEqual(path.read_bytes(), b"metadata")
        self.assertFalse(path.with_name(path.name + ".partial").exists())


if __name__ == "__main__":
    unittest.main()
