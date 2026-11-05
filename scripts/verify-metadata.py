"""Validate prepared metadata using an explicitly selected Winlex CLI."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = {"win32": "CreateFileW", "wdk": "DRIVER_OBJECT", "winrt": "Uri", "ucrt": "printf", "winui": "Button", "win2d": "CanvasControl"}
DEPENDENCIES = {"wdk": ("win32",), "winui": ("winrt",), "win2d": ("winrt", "winui")}


def query(cli, files, *arguments):
    result = subprocess.run([str(cli), *map(str, files), *arguments, "--json"], capture_output=True, text=True, encoding="utf-8", check=True)
    data = json.loads(result.stdout)
    if not data.get("ok"):
        raise ValueError(f"Winlex query failed: {arguments}: {data}")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--winlex", type=Path, required=True)
    args = parser.parse_args()
    cli = args.winlex.resolve(strict=True)
    results = {}
    for name, sample in SAMPLES.items():
        directory = ROOT / "artifacts" / name
        own = sorted(p for p in directory.iterdir() if p.suffix.lower() == ".winmd")
        if not own:
            raise ValueError(f"{name}: no metadata files")
        for file in own:
            query(cli, [file], "summary")
        files = list(own)
        for dep in DEPENDENCIES.get(name, ()):
            dependency = [p for p in sorted((ROOT / "artifacts" / dep).iterdir()) if p.suffix.lower() == ".winmd"]
            if not dependency:
                raise ValueError(f"{name}: missing dependency {dep}")
            files.extend(dependency)
        summary = query(cli, files, "summary")
        search = query(cli, files, "search", sample, "--name", "--limit", "100")
        matches = [m for m in search["result"]["matches"] if m["id"]["source_id"] < len(own) and m["kind"] != "type_reference"]
        if not matches:
            raise ValueError(f"{directory.name}: missing representative declaration {sample}")
        identity = matches[0]["id"]
        selector = f"{identity['source_id']}::0x{identity['token']:08X}"
        declaration = query(cli, files, "show", selector)
        results[name] = {"files": len(files), "summary": summary, "search": search, "declaration": declaration}
        print(f"PASS {name}: parsed {len(own)} standalone; loaded {len(files)} in set; queried and displayed {sample}", flush=True)
    output = ROOT / "tmp/verification"
    output.mkdir(parents=True, exist_ok=True)
    (output / "winlex.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
