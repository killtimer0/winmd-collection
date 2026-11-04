import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location("prepare", Path(__file__).resolve().parents[1] / "scripts/prepare-metadata.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class ExtractionTests(unittest.TestCase):
    def test_verified_output_and_unicode_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "input.zip"
            data = b"metadata"
            with zipfile.ZipFile(package, "w") as archive:
                archive.writestr("sdk/Windows.Win32.winmd", data)
            destination = root / "路径 with spaces" / "Windows.Win32.winmd"
            source = {"file": destination.name, "sha256": hashlib.sha256(data).hexdigest()}
            prepare.extract(package, source, destination)
            self.assertEqual(destination.read_bytes(), data)
            source["sha256"] = "0" * 64
            with self.assertRaises(ValueError):
                prepare.extract(package, source, destination)
            self.assertEqual(destination.read_bytes(), data)
            self.assertFalse(destination.with_suffix(".winmd.partial").exists())

    def test_missing_or_ambiguous_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for members in ([], ["a/Test.winmd", "b/Test.winmd"]):
                with zipfile.ZipFile(root / "input.zip", "w") as archive:
                    for name in members:
                        archive.writestr(name, b"data")
                with self.assertRaises(ValueError):
                    prepare.extract(root / "input.zip", {"file": "Test.winmd"}, root / "output.winmd")
                self.assertFalse((root / "output.winmd").exists())


if __name__ == "__main__":
    unittest.main()
