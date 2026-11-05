"""Prepare metadata from pinned packages, the Windows SDK and UCRT generation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN_SCRIPT = ROOT / "tools/ucrt-winmd/scripts/toolchain.ps1"


def check(data, expected):
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(f"SHA256 mismatch: {actual} != {expected}")


def download(source):
    package = ROOT / "tmp/deps" / f"{source['package'].lower()}.{source['version']}.nupkg"
    package.parent.mkdir(parents=True, exist_ok=True)
    if package.exists():
        check(package.read_bytes(), source["archive_sha256"])
        return package
    partial = package.with_suffix(".partial")
    try:
        with urllib.request.urlopen(source["url"], timeout=120) as response, partial.open("wb") as output:
            shutil.copyfileobj(response, output)
        check(partial.read_bytes(), source["archive_sha256"])
        partial.replace(package)
    finally:
        partial.unlink(missing_ok=True)
    return package


def prepare(name, source):
    package = download(source)
    directory = ROOT / "artifacts" / source.get("output", name)
    with zipfile.ZipFile(package) as archive:
        # Verify the complete selected set before replacing any output.
        contents = []
        if "duplicate_member" in source:
            duplicate = source["duplicate_member"]
            check(archive.read(duplicate["member"]), duplicate["sha256"])
            if duplicate["sha256"] not in {m["sha256"] for m in source["members"]}:
                raise ValueError("Duplicate member does not match selected output")
        seen = set()
        for member in source["members"]:
            relative = Path(member["file"])
            if relative.anchor or ".." in relative.parts or ":" in str(relative) or not relative.parts:
                raise ValueError(f"Unsafe output path: {relative}")
            key = str(relative).casefold()
            if key in seen:
                raise ValueError(f"Duplicate output path: {relative}")
            seen.add(key)
            data = archive.read(member["member"])
            check(data, member["sha256"])
            contents.append((relative, data))
    for relative, data in contents:
        destination = directory / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".partial")
        try:
            partial.write_bytes(data)
            partial.replace(destination)
        finally:
            partial.unlink(missing_ok=True)
    directory.mkdir(parents=True, exist_ok=True)
    provenance = directory / "sources" / f"{name}.json"
    provenance.parent.mkdir(parents=True, exist_ok=True)
    provenance.write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Verified {name}: {len(contents)} files from {source['package']} {source['version']}")


def import_ucrt(output):
    source = json.loads((ROOT / "sources/ucrt.json").read_text(encoding="utf-8"))
    inputs = {"UCRT.winmd": output / "UCRT.winmd", "manifest.json": output / "manifest.json", "LICENSE": ROOT / "tools/ucrt-winmd/LICENSE"}
    if set(inputs) != set(source["files"]):
        raise ValueError("Unexpected UCRT source file inventory")
    contents = {name: path.read_bytes() for name, path in inputs.items()}
    manifest = json.loads(contents["manifest.json"])
    outputs = [entry for entry in manifest["artifacts"] if entry["path"].replace("\\", "/") == "out/UCRT.winmd"]
    if len(outputs) != 1:
        raise ValueError("UCRT generator manifest must identify one merged output")
    check(contents["UCRT.winmd"], outputs[0]["sha256"])
    architectures = sorted(entry["architecture"] for entry in manifest["generation"])
    if architectures != ["arm64", "x64", "x86"]:
        raise ValueError("UCRT generation must cover x86, x64 and ARM64")
    if any(manifest["checks"].get(name) != "passed" for name in ("contracts", "ast_audit_and_clippy")):
        raise ValueError("Run the UCRT generator with -Check before importing")
    toolchain = manifest["toolchain"]
    source.update(
        generator_revision=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        sdk_version=Path(toolchain["sdk_include"]).name,
        msvc_version=Path(toolchain["msvc_include"]).parent.name,
        files={name: hashlib.sha256(data).hexdigest() for name, data in contents.items()},
    )
    record = json.dumps(source, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "sources/ucrt.json").write_text(record, encoding="utf-8", newline="\n")
    directory = ROOT / "artifacts/ucrt"
    contents["sources/ucrt.json"] = record.encode("utf-8")
    for name, data in contents.items():
        destination = directory / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_suffix(destination.suffix + ".partial")
        try:
            partial.write_bytes(data)
            partial.replace(destination)
        finally:
            partial.unlink(missing_ok=True)
    print("Verified ucrt: 3 generated files and provenance")


def find_windows_winmd(sdk_include=None):
    command = ["pwsh", "-NoProfile", "-File", str(TOOLCHAIN_SCRIPT)]
    if sdk_include is not None:
        command.extend(["-SdkInclude", str(sdk_include)])
    sdk_include = Path(subprocess.check_output(command, text=True, encoding="utf-8").strip())
    metadata = sdk_include.parent.parent / "UnionMetadata" / sdk_include.name / "Windows.winmd"
    if not metadata.is_file():
        raise ValueError(f"Windows SDK metadata not found: {metadata}")
    return metadata


def import_winrt(sdk_include=None):
    metadata = find_windows_winmd(sdk_include)
    data = metadata.read_bytes()
    directory = ROOT / "artifacts/winrt"
    destination = directory / "Windows.winmd"
    source = {
        "kind": "sdk",
        "sdk_version": metadata.parent.name,
        "sdk_member": metadata.relative_to(metadata.parents[2]).as_posix(),
        "files": {"Windows.winmd": hashlib.sha256(data).hexdigest()},
    }
    record = json.dumps(source, ensure_ascii=False, indent=2) + "\n"
    directory.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(".winmd.partial")
    try:
        partial.write_bytes(data)
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)
    provenance = directory / "sources/winrt.json"
    provenance.parent.mkdir(parents=True, exist_ok=True)
    provenance.write_text(record, encoding="utf-8", newline="\n")
    (ROOT / "sources/winrt.json").write_text(record, encoding="utf-8", newline="\n")
    print(f"Prepared winrt: Windows.winmd from SDK {source['sdk_version']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    manifests = {path.stem: path for path in sorted((ROOT / "sources").glob("*.json")) if json.loads(path.read_text(encoding="utf-8")).get("kind") != "generated"}
    parser.add_argument("--source", choices=manifests, action="append", help="prepare only selected source(s); default: all packages and SDK WinRT metadata")
    parser.add_argument("--ucrt-output", type=Path, help="also import the pinned UCRT generator output directory")
    parser.add_argument("--sdk-include", type=Path, help="SDK Include/<version> directory for WinRT; default: newest installed SDK")
    args = parser.parse_args()
    for name in args.source or manifests:
        source = json.loads(manifests[name].read_text(encoding="utf-8"))
        if source.get("kind") == "sdk":
            import_winrt(args.sdk_include)
        else:
            prepare(name, source)
    if args.ucrt_output:
        import_ucrt(args.ucrt_output)


if __name__ == "__main__":
    main()
