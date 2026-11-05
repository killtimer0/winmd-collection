"""Prepare metadata from pinned packages, the Windows SDK and UCRT generation."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from metadata import check, digest, output_paths, read_sources, write_files

ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN_SCRIPT = ROOT / "tools/ucrt-winmd/scripts/toolchain.ps1"


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


def extract(source, directory):
    package = download(source)
    with zipfile.ZipFile(package) as archive:
        # Verify the complete selected set before replacing any output.
        contents = {}
        if "duplicate_member" in source:
            duplicate = source["duplicate_member"]
            check(archive.read(duplicate["member"]), duplicate["sha256"])
            if duplicate["sha256"] not in {m["sha256"] for m in source["members"]}:
                raise ValueError("Duplicate member does not match selected output")
        paths = output_paths(directory, (member["file"] for member in source["members"]))
        for member, path in zip(source["members"], paths):
            data = archive.read(member["member"])
            check(data, member["sha256"])
            contents[path] = data
    return contents


def prepare(name, source):
    contents = extract(source, ROOT / "artifacts")
    write_files(contents)
    print(f"Verified {name}: {len(contents)} files from {source['package']} {source['version']}")


def merge_winui(source, webview, sdk_include=None):
    metadata = find_windows_winmd(sdk_include)
    sdk = metadata.parents[2]
    tool = sdk / "bin" / metadata.parent.name / "x64/mdmerge.exe"
    work = ROOT / "tmp"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as temp:
        directory = Path(temp).resolve()
        inputs = directory / "input"
        output_paths(inputs, (m["file"] for p in source["packages"] for m in p["members"]))
        contents = {}
        for package in source["packages"]:
            contents.update(extract(package, inputs))
        write_files(contents)
        references = directory / "references"
        write_files(extract(webview, references))
        subprocess.run([str(tool), "-i", str(inputs), "-o", str(directory / "output"), "-n", "1",
                        "-partial", "-metadata_dir", str(metadata.parent), "-metadata_dir", str(references), "-v"], check=True)
        delivery = {"Microsoft.winmd": (directory / "output/Microsoft.winmd").read_bytes()}
        delivery.update((p.relative_to(inputs).as_posix(), data) for p, data in contents.items() if p.suffix.lower() != ".winmd")
        source.update(sdk_version=metadata.parent.name, mdmerge_sha256=digest(tool.read_bytes()),
                      files={name: digest(data) for name, data in delivery.items()})
        record = (json.dumps(source, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        write_files({ROOT / "artifacts" / name: data for name, data in delivery.items()} | {ROOT / "sources/winui.json": record})
    print("Prepared winui: Microsoft.winmd from Windows App SDK components")


def import_ucrt(output):
    source = json.loads((ROOT / "sources/ucrt.json").read_text(encoding="utf-8"))
    inputs = {"UCRT.winmd": output / "UCRT.winmd", "licenses/ucrt/generator-LICENSE": ROOT / "tools/ucrt-winmd/LICENSE"}
    contents = {name: path.read_bytes() for name, path in inputs.items()}
    manifest_data = (output / "manifest.json").read_bytes()
    manifest = json.loads(manifest_data)
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
        generation_manifest_sha256=digest(manifest_data),
        files={name: digest(data) for name, data in contents.items()},
    )
    record = json.dumps(source, ensure_ascii=False, indent=2) + "\n"
    (ROOT / "sources/ucrt.json").write_text(record, encoding="utf-8", newline="\n")
    write_files({ROOT / "artifacts" / name: data for name, data in contents.items()})
    print("Verified ucrt: generated metadata and generator license")


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
    source = {
        "kind": "sdk",
        "sdk_version": metadata.parent.name,
        "sdk_member": metadata.relative_to(metadata.parents[2]).as_posix(),
        "files": {"Windows.winmd": digest(data)},
    }
    record = json.dumps(source, ensure_ascii=False, indent=2) + "\n"
    write_files({ROOT / "artifacts/Windows.winmd": data})
    (ROOT / "sources/winrt.json").write_text(record, encoding="utf-8", newline="\n")
    print(f"Prepared winrt: Windows.winmd from SDK {source['sdk_version']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sources = {name: source for name, source in read_sources(ROOT).items() if source.get("kind") != "generated"}
    parser.add_argument("--source", choices=sources, action="append", help="prepare only selected source(s); default: all packages and SDK WinRT metadata")
    parser.add_argument("--ucrt-output", type=Path, help="also import the checked UCRT generator output directory")
    parser.add_argument("--sdk-include", type=Path, help="SDK Include/<version> directory for WinRT and mdmerge; default: newest installed SDK")
    args = parser.parse_args()
    for name in args.source or sources:
        source = sources[name]
        if source.get("kind") == "sdk":
            import_winrt(args.sdk_include)
        elif source.get("kind") == "merged":
            merge_winui(source, sources["webview2"], args.sdk_include)
        else:
            prepare(name, source)
    if args.ucrt_output:
        import_ucrt(args.ucrt_output)


if __name__ == "__main__":
    main()
