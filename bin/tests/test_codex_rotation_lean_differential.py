#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLASSIFIER = ROOT / "bin" / "codex-with-rotation-classify"
PROOFS = ROOT / "proofs"
SPEC = PROOFS / "Spec" / "CodexRotation.lean"
PROOF = PROOFS / "Proofs" / "CodexRotation.lean"
DIFF_MAIN = PROOFS / "DiffTest" / "CodexRotationMain.lean"

EVENTS = {
    "unknown": {"type": "turn.failed", "error": {"code": "unrecognized"}},
    "quota": {"type": "turn.failed", "error": {"code": "QuotaExceeded"}},
    "cyber": {
        "type": "turn.failed",
        "error": {"kind": "CyberPolicyResponse"},
    },
    "local_hook_deny": {"item": {"type": "approval_denied"}},
}


class CodexRotationLeanDifferentialTests(unittest.TestCase):
    diff_main: Path
    lean_environment: dict[str, str]
    lean_artifacts: tempfile.TemporaryDirectory[str]

    @classmethod
    def setUpClass(cls) -> None:
        cls.lean_artifacts = tempfile.TemporaryDirectory(
            prefix="codex-rotation-lean.", dir="/dev/shm"
        )
        artifact_root = Path(cls.lean_artifacts.name)
        source_root = artifact_root / "src"
        build_root = artifact_root / "build"
        for relative_directory in ("Spec", "Proofs", "DiffTest"):
            (source_root / relative_directory).mkdir(parents=True)
        (build_root / "Spec").mkdir(parents=True)
        (build_root / "Proofs").mkdir(parents=True)
        copied_sources = []
        for source in (SPEC, PROOF, DIFF_MAIN):
            copied_source = source_root / source.relative_to(PROOFS)
            copied_source.write_bytes(source.read_bytes())
            copied_sources.append(copied_source)
        cls.diff_main = copied_sources[2]
        cls.lean_environment = os.environ.copy()
        cls.lean_environment["ELAN_TOOLCHAIN"] = "leanprover/lean4:v4.29.1"
        cls.lean_environment["LEAN_PATH"] = str(build_root)

        for source, output in (
            (copied_sources[0], build_root / "Spec" / "CodexRotation.olean"),
            (copied_sources[1], build_root / "Proofs" / "CodexRotation.olean"),
        ):
            completed = subprocess.run(
                ["lean", "-R", str(source_root), "-o", str(output), str(source)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=cls.lean_environment,
                timeout=300,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr or completed.stdout)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.lean_artifacts.cleanup()

    def test_classifier_matches_lean_first_decision_and_tail_model(self) -> None:
        cases = (
            (),
            ("quota",),
            ("quota", "cyber"),
            ("unknown", "cyber", "quota"),
            ("cyber", "quota", "local_hook_deny"),
            tuple("unknown" for _index in range(60)),
        )
        with tempfile.TemporaryDirectory(prefix="codex-rotation-diff.") as raw_root:
            scratch = Path(raw_root)
            stderr_path = scratch / "stderr.log"
            stderr_path.write_bytes(b"")
            for case_index, signals in enumerate(cases):
                with self.subTest(signals=signals):
                    stdout_path = scratch / f"stdout-{case_index}.jsonl"
                    with stdout_path.open("w", encoding="utf-8") as stream:
                        for signal in signals:
                            stream.write(
                                json.dumps(EVENTS[signal], separators=(",", ":"))
                            )
                            stream.write("\n")

                    classifier = subprocess.run(
                        [
                            str(CLASSIFIER),
                            "classify",
                            str(stdout_path),
                            str(stderr_path),
                        ],
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        timeout=10,
                        check=False,
                    )
                    lean = subprocess.run(
                        ["lean", "--run", str(self.diff_main), *signals],
                        cwd=self.diff_main.parent.parent,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=self.lean_environment,
                        timeout=300,
                        check=False,
                    )

                    self.assertEqual(classifier.returncode, 0, classifier.stderr)
                    self.assertEqual(lean.returncode, 0, lean.stderr)
                    classifier_result = json.loads(classifier.stdout)
                    lean_lines = lean.stdout.splitlines()
                    self.assertEqual(classifier_result["class"], lean_lines[0])
                    self.assertEqual(
                        classifier_result["stdout_tail_lines"], int(lean_lines[1])
                    )


if __name__ == "__main__":
    unittest.main(verbosity=2)
