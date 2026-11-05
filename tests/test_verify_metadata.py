import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
spec = importlib.util.spec_from_file_location("verify", Path(__file__).resolve().parents[1] / "scripts/verify-metadata.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class VerificationTests(unittest.TestCase):
    def test_integrity_and_summary_without_winlex(self):
        sources, entries, groups = {"source": "record"}, {}, {}
        with patch.object(sys, "argv", ["verify-metadata.py"]), \
             patch.object(verify, "read_sources", return_value=sources), \
             patch.object(verify, "collect", return_value=(entries, groups)) as collect, \
             patch.object(verify, "write_summary") as summary, \
             patch.object(verify, "verify_queries") as queries:
            verify.main()
            collect.assert_called_once_with(verify.ROOT, sources)
            summary.assert_called_once_with(verify.ROOT, sources, entries)
            queries.assert_not_called()

    def test_explicit_winlex_failure_prevents_summary(self):
        cli = Path(sys.executable)
        with patch.object(sys, "argv", ["verify-metadata.py", "--winlex", str(cli)]), \
             patch.object(verify, "read_sources", return_value={}), \
             patch.object(verify, "collect", return_value=({}, {})), \
             patch.object(verify, "write_summary") as summary, \
             patch.object(verify, "verify_queries", side_effect=ValueError("query failed")) as queries:
            with self.assertRaisesRegex(ValueError, "query failed"):
                verify.main()
            queries.assert_called_once_with(cli.resolve(), {})
            summary.assert_not_called()


if __name__ == "__main__":
    unittest.main()
