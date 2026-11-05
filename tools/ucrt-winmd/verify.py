import json
from pathlib import Path
import subprocess
import struct
import argparse

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description='Optional Winlex integration checks; not required for generation.')
parser.add_argument('--winlex', type=Path, required=True, help='Path to a compatible Winlex CLI executable')
exe = parser.parse_args().winlex.resolve()
if not exe.is_file():
    parser.error('Winlex executable not found.')
out = root / 'verification'
out.mkdir(exist_ok=True)


def query(label, *args):
    result = subprocess.run([str(exe), str(root / 'out/UCRT.winmd'), *args, '--json'],
                            capture_output=True, text=True, encoding='utf-8', check=True)
    (out / f'{label}.json').write_text(result.stdout, encoding='utf-8')
    data = json.loads(result.stdout)
    assert data['ok'], data
    return data['result']


for name, fixed in [('printf', 1), ('fprintf', 2), ('sprintf', 2), ('snprintf', 3),
                    ('scanf', 1), ('sscanf', 2), ('vprintf', 2), ('vsnprintf', 4)]:
    result = query(name, 'show', name)
    assert len(result['parameters']) == fixed
    assert result['signature_flags'] & 15 == (0 if name.startswith('v') else 5)
    assert result['return_type'] == {'kind': 'primitive', 'name': 'I32'}
    assert result['import'] is None
    abi = next(a for a in result['attributes'] if a['name'] == 'NativeCallingConventionAttribute')
    assert abi['arguments'][0]['value'] == {'kind': 'string', 'value': 'C'}

for name in ['malloc', 'free', 'fopen', 'qsort']:
    result = query(name, 'show', name)
    assert result['import'] is None
    abi = next(a for a in result['attributes'] if a['name'] == 'NativeCallingConventionAttribute')
    assert abi['arguments'][0]['value'] == {'kind': 'string', 'value': 'C'}
    assert result['signature_flags'] & 15 == 0
query('EOF', 'show', 'EOF')
query('EINVAL', 'show', 'EINVAL')

# Compile assertions against this run's headers, not a previous SDK's layout.
config = json.loads((root / 'out/toolchain.json').read_text(encoding='utf-8'))
for arch, target in [('x86', 'i686-pc-windows-msvc'), ('x64', 'x86_64-pc-windows-msvc'),
                     ('arm64', 'aarch64-pc-windows-msvc')]:
    assertions = ['#include "../main.h"', '#include <limits.h>']
    for name, c_type in [('FILE', 'FILE'), ('tm', 'struct tm'),
                         ('_stat64', 'struct _stat64'), ('_stat32', 'struct _stat32')]:
        result = query(f'{arch}-{name}', 'layout', 'Ucrt.CRuntime.' + name, '--arch', arch)
        assertions.append(f'_Static_assert(sizeof({c_type}) * CHAR_BIT == {result["size_bits"]}, "{name} size");')
        assertions.append(f'_Static_assert(_Alignof({c_type}) * CHAR_BIT == {result["alignment_bits"]}, "{name} alignment");')
        for field in result['fields']:
            assertions.append(f'_Static_assert(offsetof({c_type}, {field["name"]}) * CHAR_BIT == {field["offset_bits"]}, "{name}.{field["name"]} offset");')
    probe = out / f'{arch}-native-layout.c'
    probe.write_text('\n'.join(assertions) + '\n', encoding='utf-8')
    result = subprocess.run([config['clang_path'], *config['clang_args'], '--target=' + target,
                             '-fsyntax-only', str(probe)], capture_output=True, text=True, encoding='utf-8')
    (out / f'{arch}-native-layout.log').write_text(result.stdout + result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(f'{arch}: native layout comparison failed:\n{result.stdout}{result.stderr}')
query('summary', 'summary')

for filename in [f'{arch}/{name}' for arch in ['x86', 'x64', 'arm64']
                 for name in ['UCRT.winmd', 'UCRT.roundtrip.winmd']] + ['UCRT.winmd', 'UCRT.roundtrip.winmd']:
    data = (root / 'out' / filename).read_bytes()
    start = data.index(b'BSJB')
    version_len = struct.unpack_from('<I', data, start + 12)[0]
    header = start + 16 + version_len
    streams = struct.unpack_from('<H', data, header + 2)[0]
    pos = header + 4
    for _ in range(streams):
        offset, size = struct.unpack_from('<II', data, pos)
        end = data.index(b'\0', pos + 8)
        name = data[pos + 8:end]
        pos = (end + 4) & ~3
        if name == b'#~':
            tables = start + offset
            valid = struct.unpack_from('<Q', data, tables + 8)[0]
            row_pos = tables + 24
            counts = {}
            for table in range(64):
                if valid & (1 << table):
                    counts[table] = struct.unpack_from('<I', data, row_pos)[0]
                    row_pos += 4
            assert counts.get(26, 0) == 0, ('ModuleRef', filename)
            assert counts.get(28, 0) == 0, ('ImplMap', filename)
            break
    else:
        raise AssertionError('missing metadata tables')
    assert b'.lib\0' not in data.lower()
    assert b'api-ms-win-crt-' not in data

print('PASS: declaration signatures/ABIs, constants, 12 native layout comparisons; zero ModuleRef/ImplMap in original and roundtrip')
