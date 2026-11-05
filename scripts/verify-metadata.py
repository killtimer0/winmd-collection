"""Verify metadata integrity, write delivery summaries and optionally query Winlex."""
import argparse
import json
from pathlib import Path
import subprocess
from metadata import SOURCES, collect, read_sources, write_summary

ROOT = Path(__file__).resolve().parents[1]


def query(cli, files, *arguments):
    result = subprocess.run([str(cli), *map(str, files), *arguments, "--json"], capture_output=True, text=True, encoding="utf-8", check=True)
    data = json.loads(result.stdout)
    if not data.get("ok"):
        raise ValueError(f"Winlex query failed: {arguments}: {data}")
    return data


def verify_queries(cli, groups):
    results = {}
    for name, (sample, dependencies) in SOURCES.items():
        own = sorted(groups[name])
        for file in own:
            query(cli, [file], "summary")
        files = list(own)
        for dep in dependencies:
            files.extend(sorted(groups[dep]))
        summary = query(cli, files, "summary")
        search = query(cli, files, "search", sample, "--name", "--limit", "100")
        matches = [m for m in search["result"]["matches"] if m["id"]["source_id"] < len(own) and m["kind"] != "type_reference"]
        if not matches:
            raise ValueError(f"{name}: missing representative declaration {sample}")
        identity = matches[0]["id"]
        selector = f"{identity['source_id']}::0x{identity['token']:08X}"
        declaration = query(cli, files, "show", selector)
        results[name] = {"files": len(files), "summary": summary, "search": search, "declaration": declaration}
        print(f"PASS {name}: parsed {len(own)} standalone; loaded {len(files)} in set; queried and displayed {sample}", flush=True)
    output = ROOT / "tmp/verification"
    output.mkdir(parents=True, exist_ok=True)
    (output / "winlex.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--winlex", type=Path, help="also verify queries using this Winlex CLI")
    args = parser.parse_args()
    sources = read_sources(ROOT)
    entries, groups = collect(ROOT, sources)
    if args.winlex:
        verify_queries(args.winlex.resolve(strict=True), groups)
    write_summary(ROOT, sources, entries)
    print("Wrote SOURCES.md, licenses/README.md and SHA256SUMS")


if __name__ == "__main__":
    main()
