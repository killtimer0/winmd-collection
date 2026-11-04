"""Package only metadata and provenance verified against tracked source records."""
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("win32", "wdk", "winrt", "ucrt", "winui", "win2d")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(value):
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if not value or posix.is_absolute() or windows.anchor or ".." in posix.parts or ".." in windows.parts or ":" in value or "\\" in value:
        raise ValueError(f"Unsafe path: {value}")
    return posix.as_posix()


def collect(root):
    groups = {name: {} for name in SOURCES}
    keys = {name: set() for name in SOURCES}

    def add(name, relative, expected=None, record=None):
        relative = safe_path(relative)
        key = relative.casefold()
        if key == "sha256sums" or any(key == old or key.startswith(old + "/") or old.startswith(key + "/") for old in keys[name]):
            raise ValueError(f"Colliding output path: {name}/{relative}")
        keys[name].add(key)
        base = (root / "artifacts" / name).resolve()
        path = base / relative
        if not path.resolve().is_relative_to(base):
            raise ValueError(f"Output escapes artifact directory: {path}")
        data = path.read_bytes()
        if expected is not None and digest(data) != expected:
            raise ValueError(f"SHA256 mismatch: {path}")
        if record is not None and json.loads(data) != record:
            raise ValueError(f"Provenance mismatch: {path}")
        groups[name][relative] = data

    for path in sorted((root / "sources").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        name = record.get("output", path.stem)
        if name not in groups:
            raise ValueError(f"Unknown artifact group: {name}")
        if record.get("kind") == "generated":
            for relative, expected in record["files"].items():
                add(name, relative, expected)
        else:
            for member in record["members"]:
                add(name, member["file"], member["sha256"])
        add(name, f"sources/{path.name}", record=record)
    for name, files in groups.items():
        if not any(p.lower().endswith(".winmd") for p in files):
            raise ValueError(f"Missing metadata record: {name}")
    return groups


def main():
    output = ROOT / "artifacts"
    groups = collect(ROOT)
    zip_hashes = []
    for name, entries in groups.items():
        inventory = "".join(f"{digest(data)}  {path}\n" for path, data in sorted(entries.items()))
        sums = output / name / "SHA256SUMS"
        destination = output / f"{name}.zip"
        partial = destination.with_suffix(".zip.partial")
        try:
            with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path, data in sorted(entries.items()):
                    archive.writestr(f"{name}/{path}", data)
                archive.writestr(f"{name}/SHA256SUMS", inventory.encode("utf-8"))
            partial.replace(destination)
        finally:
            partial.unlink(missing_ok=True)
        sums.write_text(inventory, encoding="utf-8", newline="\n")
        line = f"{digest(destination.read_bytes())}  {destination.name}"
        zip_hashes.append(line)
        print(line)
    (output / "SHA256SUMS").write_text("\n".join(zip_hashes) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
