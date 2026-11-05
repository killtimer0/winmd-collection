"""Source inventories and output handling shared by preparation and verification."""
import hashlib
import json
from pathlib import PurePosixPath, PureWindowsPath

SOURCES = {
    "win32": ("CreateFileW", ()), "wdk": ("DRIVER_OBJECT", ("win32",)),
    "winrt": ("Uri", ()), "ucrt": ("printf", ()),
    "winui": ("Button", ("winrt",)), "win2d": ("CanvasControl", ("winrt", "winui")),
}
SDK_URL = "https://developer.microsoft.com/windows/downloads/windows-sdk/"
LICENSE_NOTES = """# 许可说明

下载包的许可、NOTICE 和依赖说明按来源保留在本目录中。
WinRT 的 Windows.winmd 适用所用 Windows SDK 的许可。

UCRT 生成器源码采用 GPL-3.0-only，许可原文见 ucrt/generator-LICENSE。
生成的 UCRT 元数据来自 Microsoft UCRT／VCRuntime 头文件，再分发权限尚未确认。
"""


def read_sources(root):
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((root / "sources").glob("*.json"))}


def source_files(source):
    return source["files"].items() if "files" in source else [(m["file"], m["sha256"]) for m in source["members"]]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check(data, expected):
    actual = digest(data)
    if actual != expected:
        raise ValueError(f"SHA256 mismatch: {actual} != {expected}")


def output_paths(directory, names):
    directory = directory.resolve()
    keys = {"sha256sums", "sources.md", "licenses/readme.md"}
    paths = []
    for name in names:
        posix, windows = PurePosixPath(name), PureWindowsPath(name)
        if not posix.parts or posix.is_absolute() or windows.anchor or ".." in posix.parts or ".." in windows.parts or ":" in name or "\\" in name:
            raise ValueError(f"Unsafe output path: {name}")
        key = posix.as_posix().casefold()
        if any(key == old or key.startswith(old + "/") or old.startswith(key + "/") for old in keys):
            raise ValueError(f"Colliding output path: {name}")
        keys.add(key)
        path = directory / posix
        if not path.resolve().is_relative_to(directory):
            raise ValueError(f"Output escapes artifact directory: {path}")
        paths.append(path)
    return paths


def write_files(entries):
    for path, data in entries.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".partial")
        try:
            partial.write_bytes(data)
            partial.replace(path)
        finally:
            partial.unlink(missing_ok=True)


def collect(root, sources):
    entries, groups, records = {}, {name: [] for name in SOURCES}, []
    for name, source in sources.items():
        group = source.get("output", name)
        if group not in groups:
            raise ValueError(f"Unknown artifact group: {group}")
        records.extend((group, relative, expected) for relative, expected in source_files(source))
    paths = output_paths(root / "artifacts", (relative for _, relative, _ in records))
    for (group, _, expected), path in zip(records, paths):
        data = path.read_bytes()
        check(data, expected)
        entries[path] = data
        if path.suffix.lower() == ".winmd":
            groups[group].append(path)
    missing = [name for name, files in groups.items() if not files]
    if missing:
        raise ValueError(f"Missing metadata records: {missing}")
    return entries, groups


def write_summary(root, sources, entries):
    sections = ["# 元数据来源", "", "许可见 [licenses/README.md](licenses/README.md)。", ""]
    for name, source in sources.items():
        sections.extend([f"## {name}", ""])
        if source.get("kind") == "sdk":
            details = [f"Windows SDK：{source['sdk_version']}", f"来源：{SDK_URL}", f"SDK 内位置：`{source['sdk_member']}`"]
        elif source.get("kind") == "generated":
            details = ["生成器：本仓库的 `tools/ucrt-winmd/`", f"源码版本：`{source['generator_revision']}`",
                       f"Windows SDK：{source['sdk_version']}；MSVC：{source['msvc_version']}", f"SDK 来源：{SDK_URL}",
                       "MSVC 来源：https://visualstudio.microsoft.com/downloads/", f"架构：{', '.join(source['architectures'])}",
                       f"生成清单 SHA-256：`{source['generation_manifest_sha256']}`", source['constraints']]
        else:
            details = [f"包：{source['package']} {source['version']}", f"来源：{source['url']}", f"包 SHA-256：`{source['archive_sha256']}`"]
        dependencies = SOURCES[source.get("output", name)][1]
        if dependencies:
            details.append(f"依赖：{', '.join(dependencies)}")
        sections.extend(f"- {detail}" for detail in details)
        sections.extend(f"- [{file}]({file})" for file, _ in source_files(source))
        sections.append("")
    output = (root / "artifacts").resolve()
    summaries = {output / "SOURCES.md": "\n".join(sections).encode("utf-8"), output / "licenses/README.md": LICENSE_NOTES.encode("utf-8")}
    inventory = entries | summaries
    sums = "".join(f"{digest(data)}  {path.relative_to(output).as_posix()}\n" for path, data in sorted(inventory.items()))
    write_files(summaries | {output / "SHA256SUMS": sums.encode("utf-8")})
