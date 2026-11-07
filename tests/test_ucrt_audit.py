import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("ucrt_audit", Path(__file__).resolve().parents[1] / "tools/ucrt-winmd/audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def test_detected_shape_errors_fail_but_coverage_gaps_remain_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / "out/x64"
            (out / "rdl").mkdir(parents=True)
            (out / "rdl/apis.rdl").write_text('extern "C" fn printf(value: i32);')
            tree = {"inner": [
                {"kind": "FunctionDecl", "name": "printf", "loc": {"file": "SDK/ucrt/stdio.h"},
                 "inner": [{"kind": "ParmVarDecl", "name": "value"}]},
                {"kind": "FunctionDecl", "name": "not_emitted"},
                {"kind": "RecordDecl", "name": "record", "completeDefinition": True,
                 "inner": [{"kind": "FieldDecl", "name": "first"}, {"kind": "FieldDecl", "name": "second"}]},
                {"kind": "RecordDecl", "name": "missing_record", "completeDefinition": True},
            ]}
            (out / "clang-ast.json").write_text(json.dumps(tree))
            (out / "clang-macros.txt").write_text("")
            config = {"sdk_include": "SDK", "msvc_include": "VC", "clang_path": "clang", "clang_args": []}
            for count, variadic, fields, failure in [
                (1, "false", "first,second", None),
                (99, "false", "first,second", "parameter-count-or-varargs-mismatch"),
                (1, "true", "first,second", "parameter-count-or-varargs-mismatch"),
                (1, "false", "second,first", "field-name-or-order-mismatch"),
            ]:
                with (out / "winmd-inventory.tsv").open("w", newline="") as stream:
                    writer = csv.DictWriter(stream, ["kind", "owner", "name", "parameter_count", "variadic", "fields"], delimiter="\t")
                    writer.writeheader()
                    writer.writerow({"kind": "method", "owner": "Apis", "name": "printf", "parameter_count": count, "variadic": variadic})
                    writer.writerow({"kind": "type", "name": "record", "fields": fields})
                with self.subTest(count=count, variadic=variadic, fields=fields), patch.object(audit, "ROOT", root), patch.object(audit, "run"):
                    if failure:
                        with self.assertRaisesRegex(ValueError, "WinMD shape mismatch"):
                            audit.audit("x64", config)
                    else:
                        audit.audit("x64", config)
                    report = json.loads((out / "coverage.json").read_text())
                    self.assertIn("not_emitted", [row["name"] for row in report["gaps"]])
                    self.assertIn("missing-function", report["winmd_shape_counts"])
                    self.assertIn("missing-record", report["winmd_shape_counts"])
                    if failure:
                        self.assertIn(failure, report["winmd_shape_counts"])


if __name__ == "__main__":
    unittest.main()
