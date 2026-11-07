import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


class ManifestTests(unittest.TestCase):
    def test_source_archive_preserves_revision_without_git_even_when_repackaged(self):
        with tempfile.TemporaryDirectory(prefix="archive 路径 ", dir=ROOT / "tmp") as temp:
            root = Path(temp).resolve()
            archive = root / "source.zip"
            environment = dict(os.environ, UCRT_PACKAGE_SCRIPT=str(ROOT / "tools/ucrt-winmd/package-source.ps1"), UCRT_ARCHIVE=str(archive))
            proc = subprocess.run(["pwsh", "-NoProfile", "-Command", "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); & $env:UCRT_PACKAGE_SCRIPT -Destination $env:UCRT_ARCHIVE"], env=environment, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            extracted = root / "extracted"
            with zipfile.ZipFile(archive) as source:
                source.extractall(extracted)
            revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
            self.assertEqual(json.loads((extracted / "source-provenance.json").read_bytes()), {"generator_revision": revision})
            environment = dict(os.environ, UCRT_EXTRACTED_SOURCE=str(extracted), UCRT_REPACKED_SOURCE=str(root / "repacked.zip"))
            script = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
function git { throw 'Git must not be used for extracted sources.' }
. (Join-Path $env:UCRT_EXTRACTED_SOURCE 'scripts/toolchain.ps1')
Get-CrtSourceRevision $env:UCRT_EXTRACTED_SOURCE
& (Join-Path $env:UCRT_EXTRACTED_SOURCE 'package-source.ps1') -Destination $env:UCRT_REPACKED_SOURCE
"""
            proc = subprocess.run(["pwsh", "-NoProfile", "-Command", script], env=environment, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn(revision, proc.stdout)
            with zipfile.ZipFile(root / "repacked.zip") as repacked:
                self.assertEqual(json.loads(repacked.read("source-provenance.json")), {"generator_revision": revision})

    def test_generation_records_revision_and_source_and_reference_digests(self):
        with tempfile.TemporaryDirectory(prefix="provenance 路径 ", dir=ROOT / "tmp") as temp:
            root = Path(temp).resolve()
            for directory in ("out", "SDK/ucrt", "SDK/shared", "MSVC"):
                (root / directory).mkdir(parents=True)
            source = root / "main.h"
            source.write_bytes(b"generation source")
            reference = root / "Windows.Win32.winmd"
            reference.write_bytes(b"generation reference")
            for directory in ("SDK/ucrt", "SDK/shared", "MSVC"):
                (root / directory / "probe.h").write_bytes(b"header")
            for arch in ("x86", "x64", "arm64", ""):
                out = root / "out" / arch
                out.mkdir(exist_ok=True)
                for name in ("UCRT.winmd", "UCRT.roundtrip.winmd"):
                    (out / name).write_bytes(b"metadata")
                if arch:
                    (out / "generation.json").write_text(json.dumps({"architecture": arch}))
            environment = dict(os.environ, UCRT_TOOLCHAIN_SCRIPT=str(ROOT / "tools/ucrt-winmd/scripts/toolchain.ps1"))
            script = """
$ErrorActionPreference = 'Stop'
. $env:UCRT_TOOLCHAIN_SCRIPT
function Get-CrtSourceFiles([string]$Root) { Get-Item -LiteralPath (Join-Path $Root 'main.h') }
$root = (Get-Location).ProviderPath
$toolchain = @{ sdk_include = (Join-Path $root 'SDK'); msvc_include = (Join-Path $root 'MSVC'); win32_metadata = (Join-Path $root 'Windows.Win32.winmd') }
Write-CrtManifest -Root $root -Toolchain $toolchain -Checked $true -WinlexChecked $false
"""
            proc = subprocess.run(["pwsh", "-NoProfile", "-Command", script], cwd=root, env=environment, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            manifest = json.loads((root / "out/manifest.json").read_bytes())
            revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
            self.assertEqual(manifest["generator_revision"], revision)
            self.assertEqual(manifest["source_inputs"], [{"path": "main.h", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}])
            self.assertEqual(manifest["metadata_references"], [{"path": str(reference), "sha256": hashlib.sha256(reference.read_bytes()).hexdigest()}])
            (root / "source-provenance.json").write_text(json.dumps({"generator_revision": "a" * 40}))
            script = "function git { throw 'Git must not be used for extracted sources.' }\n" + script
            proc = subprocess.run(["pwsh", "-NoProfile", "-Command", script], cwd=root, env=environment, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            manifest = json.loads((root / "out/manifest.json").read_bytes())
            self.assertEqual(manifest["generator_revision"], "a" * 40)


if __name__ == "__main__":
    unittest.main()
