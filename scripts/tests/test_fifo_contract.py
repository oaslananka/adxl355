from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class FifoContractTests(unittest.TestCase):
    def test_authoritative_vectors_generate_c_header(self) -> None:
        subprocess.run(
            [sys.executable, "spec/generate_fifo_vectors_header.py", "--check"],
            cwd=ROOT,
            check=True,
        )

    def test_vectors_cover_required_fifo_boundaries(self) -> None:
        fifo = json.loads((ROOT / "spec/test_vectors.json").read_text())["fifo"]
        self.assertEqual(fifo["max_locations"], 96)
        self.assertEqual(fifo["locations_per_sample"], 3)
        errors = {vector["error"] for vector in fifo["invalid_samples"]}
        self.assertEqual(errors, {"length", "empty", "format"})
        lengths = {len(vector["bytes"]) for vector in fifo["invalid_samples"]}
        self.assertTrue({8, 9, 10}.issubset(lengths))

    def test_c_fifo_core_uses_no_dynamic_allocation(self) -> None:
        source = (ROOT / "c/src/adxl355.c").read_text()
        start = source.index("adxl355_status_t adxl355_read_fifo_samples")
        end = source.index(
            "/* ---------------------------------------------------------------------------\n * Utility",
            start,
        )
        fifo_source = source[start:end]
        for forbidden in ("malloc(", "calloc(", "realloc(", "free("):
            self.assertNotIn(forbidden, fifo_source)


if __name__ == "__main__":
    unittest.main()
