"""Download and verify pinned Win32 metadata independently of Winlex."""
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def check(data, expected):
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ValueError(f"SHA256 mismatch: {actual} != {expected}")


def extract(package, source, destination):
    with zipfile.ZipFile(package) as archive:
        names = [name for name in archive.namelist() if name.rsplit("/", 1)[-1] == source["file"]]
        if len(names) != 1:
            raise ValueError(f"Expected one WinMD in {package}, found {names}")
        data = archive.read(names[0])
    check(data, source["sha256"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".partial")
    try:
        partial.write_bytes(data)
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def main():
    source = json.loads((ROOT / "sources/win32.json").read_text(encoding="utf-8"))
    destination = ROOT / "artifacts/win32" / source["file"]
    if destination.exists():
        check(destination.read_bytes(), source["sha256"])
    else:
        package = ROOT / "tmp/deps" / f"win32metadata-{source['version']}.nupkg"
        package.parent.mkdir(parents=True, exist_ok=True)
        if not package.exists():
            partial = package.with_suffix(".partial")
            try:
                with urllib.request.urlopen(source["url"], timeout=120) as response, partial.open("wb") as output:
                    shutil.copyfileobj(response, output)
                partial.replace(package)
            finally:
                partial.unlink(missing_ok=True)
        extract(package, source, destination)
    print(f"Verified {destination}")


if __name__ == "__main__":
    main()
