#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import tomllib
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BIN_DIR = Path(__file__).resolve().parents[1]
WRAPPER = Path(
    os.environ.get("CODEX_ROTATION_WRAPPER", BIN_DIR / "codex-with-rotation")
)
CLASSIFIER = Path(
    os.environ.get(
        "CODEX_ROTATION_CLASSIFIER", BIN_DIR / "codex-with-rotation-classify"
    )
)
MARKER = Path(os.environ.get("CODEX_ISSUE_MARKER", BIN_DIR / "codex-issue-marker"))
GATE = BIN_DIR.parent / "hooks" / "codex-first-gate.sh"
BOOTSTRAP = BIN_DIR / "bootstrap-config"
ROLES_FILE = BIN_DIR.parent / "lib" / "codex-roles.txt"
RUNNER = BIN_DIR.parent / "hooks" / "tests" / "run.sh"
CONFIG_TEMPLATE = BIN_DIR.parent / "config.example.toml"
DOC = BIN_DIR.parent / "docs" / "codex-with-rotation.md"
AGENTS = BIN_DIR.parent / "AGENTS.md"

POOL_NAMES = ("auth.json", "auth.json-danusya", "auth.json-xaionaro")
CYBER_VARIANTS = (
    "CyberPolicyResponse",
    "cyber_policy",
    "HighRiskCyberActivity",
    "high_risk_cyber_activity",
)
QUOTA_VARIANTS = (
    "UsageLimitReached",
    "usage_limit_reached",
    "RateLimitReached",
    "rate_limit_reached",
    "SessionBudgetExceeded",
    "session_budget_exceeded",
    "QuotaExceeded",
    "quota_exceeded",
    "UsageNotIncluded",
    "usage_not_included",
)
DENYING_GUARDIAN_RISK_LEVELS = ("high", "critical", "severe")
INVALID_SESSION_IDS = (".", "..", "../etc", "foo/../bar", "foo/", "/etc")
VALID_SESSION_ID = "session_2676a827-b749-44d6-a0f1-a8bd175e5b13"
CAPABILITY_TOKEN_LIMITATION = (
    "Markers are session-scoped capability tokens, not task-bound "
    "authorizations; they defend against accidental Kimi-quota consumption, "
    "not against orchestrator bugs or hostile same-UID processes. An "
    "orchestrator that issues a marker for task A and then calls Agent for "
    "unrelated task B will consume the marker on B."
)
CORRECT_GATE_STANZA = textwrap.dedent(
    """
    [[hooks]]
    event = "PreToolUse"
    matcher = "^(Agent|AgentSwarm)$"
    command = "codex-first-gate.sh"
    """
).lstrip()

JsonObject = dict[str, Any]


MOCK_CODEX = textwrap.dedent(
    r"""
    #!/usr/bin/env python3
    import fcntl
    import hashlib
    import json
    import os
    import stat
    import sys
    import time
    from pathlib import Path


    def locked_read_modify(path, operation):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+", encoding="utf-8") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            stream.seek(0)
            result = operation(stream)
            stream.flush()
            os.fsync(stream.fileno())
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            return result


    def consume_response(path):
        def consume(stream):
            raw = stream.read()
            plan = json.loads(raw) if raw else []
            if not plan:
                raise RuntimeError("mock response plan exhausted")
            response = plan.pop(0)
            stream.seek(0)
            stream.truncate()
            json.dump(plan, stream)
            return response

        return locked_read_modify(path, consume)


    def append_log(path, record):
        def append(stream):
            stream.seek(0, os.SEEK_END)
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")

        locked_read_modify(path, append)


    def barrier(path, target):
        def increment(stream):
            raw = stream.read().strip()
            count = int(raw) if raw else 0
            count += 1
            stream.seek(0)
            stream.truncate()
            stream.write(str(count))
            return count

        locked_read_modify(path, increment)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            def observe(stream):
                raw = stream.read().strip()
                return int(raw) if raw else 0

            if locked_read_modify(path, observe) >= target:
                return
            time.sleep(0.01)
        raise RuntimeError("mock barrier timed out")


    codex_home = Path(os.environ["CODEX_HOME"])
    with (codex_home / "auth.json").open("r", encoding="utf-8") as stream:
        account_id = json.load(stream)["tokens"]["account_id"]

    stdin_bytes = sys.stdin.buffer.read()
    append_log(
        Path(os.environ["MOCK_LOG_PATH"]),
        {
            "account_id": account_id,
            "auth_mode": stat.S_IMODE((codex_home / "auth.json").stat().st_mode),
            "argv": sys.argv[1:],
            "stdin_sha256": hashlib.sha256(stdin_bytes).hexdigest(),
            "stdin_length": len(stdin_bytes),
        },
    )

    response = consume_response(Path(os.environ["MOCK_PLAN_PATH"]))
    if "signal" in response:
        Path(response["signal"]).touch()
    if "wait_for" in response:
        deadline = time.monotonic() + 8
        wait_path = Path(response["wait_for"])
        while time.monotonic() < deadline and not wait_path.exists():
            time.sleep(0.01)
        if not wait_path.exists():
            raise RuntimeError("mock release timed out")
    if "barrier_path" in response:
        barrier(Path(response["barrier_path"]), int(response["barrier_target"]))

    outputs = response.get("stdout")
    if outputs is None:
        outputs = [{"type": "turn.completed"}]
    for output in outputs:
        if isinstance(output, str):
            print(output)
        else:
            print(json.dumps(output, separators=(",", ":")))
    if response.get("stderr"):
        print(response["stderr"], file=sys.stderr)
    raise SystemExit(int(response.get("exit", 0)))
    """
).lstrip()


def event_response(event: JsonObject, *, exit_code: int = 9) -> JsonObject:
    return {"stdout": [event], "exit": exit_code}


def success_response() -> JsonObject:
    return {"stdout": [{"type": "turn.completed", "result": "ok"}], "exit": 0}


def run_classifier(
    fixture: WrapperFixture,
    stdout_lines: tuple[JsonObject | str, ...],
    *,
    stderr_lines: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    stdout_path = fixture.root / "classifier.stdout.jsonl"
    stderr_path = fixture.root / "classifier.stderr.log"
    stdout_path.write_text(
        "\n".join(
            line
            if isinstance(line, str)
            else json.dumps(line, separators=(",", ":"))
            for line in stdout_lines
        )
        + "\n",
        encoding="utf-8",
    )
    stderr_path.write_text(
        "\n".join(stderr_lines) + ("\n" if stderr_lines else ""),
        encoding="utf-8",
    )
    return subprocess.run(
        [str(CLASSIFIER), "classify", str(stdout_path), str(stderr_path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )


def status_from(result: subprocess.CompletedProcess[bytes]) -> JsonObject:
    lines = result.stderr.decode("utf-8", errors="replace").splitlines()
    if not lines:
        raise AssertionError("wrapper emitted no stderr status")
    return json.loads(lines[0])


def exact_task_sig(stdin_bytes: bytes, arguments: tuple[str, ...]) -> str:
    encoded = (
        f"{len(stdin_bytes)}:".encode()
        + stdin_bytes
        + f"_{len(arguments)}:".encode()
        + b"".join(os.fsencode(argument) for argument in arguments)
    )
    return hashlib.sha256(encoded).hexdigest()


def utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


class WrapperFixture:
    def __init__(
        self,
        accounts: tuple[str, ...] = ("account-a", "account-b", "account-c"),
    ) -> None:
        scratch_root = Path.home() / "tmp"
        scratch_root.mkdir(parents=True, exist_ok=True)
        self._temporary = tempfile.TemporaryDirectory(
            prefix="codex-rotation-test.", dir=scratch_root
        )
        self.root = Path(self._temporary.name)
        self.home = self.root / "home"
        self.state_dir = self.root / "state"
        self.fake_bin = self.root / "bin"
        self.plan_path = self.root / "plan.json"
        self.log_path = self.root / "invocations.jsonl"
        self.home.mkdir(mode=0o700)
        self.state_dir.mkdir(mode=0o700)
        self.fake_bin.mkdir(mode=0o700)
        (self.state_dir / "hooks").mkdir()
        (self.state_dir / "config.toml").write_text("", encoding="utf-8")

        for pool_name, account_id in zip(POOL_NAMES, accounts, strict=False):
            auth_path = self.state_dir / pool_name
            auth_path.write_text(
                json.dumps({"tokens": {"account_id": account_id}}), encoding="utf-8"
            )
            auth_path.chmod(0o640)

        mock_path = self.fake_bin / "codex"
        mock_path.write_text(MOCK_CODEX, encoding="utf-8")
        mock_path.chmod(0o755)

    def cleanup(self) -> None:
        self._temporary.cleanup()

    def environment(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        environment = os.environ.copy()
        environment.pop("CODEX_KIMI_FORCE", None)
        environment.update(
            {
                "HOME": str(self.home),
                "CODEX_ROTATE_STATE_DIR": str(self.state_dir),
                "MOCK_PLAN_PATH": str(self.plan_path),
                "MOCK_LOG_PATH": str(self.log_path),
                "PATH": f"{self.fake_bin}{os.pathsep}{environment['PATH']}",
            }
        )
        if extra:
            environment.update(extra)
        return environment

    def set_plan(self, responses: list[JsonObject]) -> None:
        self.plan_path.write_text(json.dumps(responses), encoding="utf-8")
        self.log_path.write_text("", encoding="utf-8")

    def run(
        self,
        responses: list[JsonObject],
        *,
        stdin: bytes = b"task",
        arguments: tuple[str, ...] = (),
        label: str | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        self.set_plan(responses)
        return self.run_existing_plan(
            stdin=stdin,
            arguments=arguments,
            label=label,
            extra_environment=extra_environment,
        )

    def run_existing_plan(
        self,
        *,
        stdin: bytes = b"task",
        arguments: tuple[str, ...] = (),
        label: str | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        command = [str(WRAPPER)]
        if label is not None:
            command.extend(("--label", label))
        command.extend(("--", *arguments))
        return subprocess.run(
            command,
            input=stdin,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.environment(extra_environment),
            timeout=20,
            check=False,
        )

    def initialize_state(self) -> subprocess.CompletedProcess[bytes]:
        return self.run([], extra_environment={"CODEX_KIMI_FORCE": "1"})

    def state(self) -> JsonObject:
        return json.loads((self.state_dir / ".auth-active").read_text(encoding="utf-8"))

    def replace_state(self, state_data: JsonObject) -> None:
        temporary = self.state_dir / ".auth-active.test-tmp"
        temporary.write_text(json.dumps(state_data), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(self.state_dir / ".auth-active")

    def invocations(self) -> list[JsonObject]:
        if not self.log_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.log_path.read_text(encoding="utf-8").splitlines()
            if line
        ]


class WrapperTestCase(unittest.TestCase):
    def fixture(
        self, accounts: tuple[str, ...] = ("account-a", "account-b", "account-c")
    ) -> WrapperFixture:
        fixture = WrapperFixture(accounts)
        self.addCleanup(fixture.cleanup)
        return fixture


class TaskSignatureTests(WrapperTestCase):
    def test_signature_matches_exact_length_prefixed_definition(self) -> None:
        fixture = self.fixture()
        stdin = b"ab\x00cd\n"
        arguments = ("alpha", "beta gamma", "")
        result = fixture.run([success_response()], stdin=stdin, arguments=arguments)

        self.assertEqual(result.returncode, 0)
        status = status_from(result)
        self.assertEqual(status["task_sig"], exact_task_sig(stdin, arguments))
        self.assertRegex(status["task_sig"], r"^[0-9a-f]{64}$")
        invocation = fixture.invocations()[0]
        self.assertEqual(invocation["stdin_length"], len(stdin))
        self.assertEqual(invocation["stdin_sha256"], hashlib.sha256(stdin).hexdigest())
        self.assertEqual(
            invocation["argv"], ["exec", "--ephemeral", "--json", *arguments]
        )

    def test_label_is_reported_without_changing_task_signature(self) -> None:
        fixture = self.fixture()
        stdin = b"labelled task"
        arguments = ("--sandbox", "read-only")

        result = fixture.run(
            [success_response()],
            stdin=stdin,
            arguments=arguments,
            label="critic-B correlation",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        status = status_from(result)
        self.assertEqual(status["label"], "critic-B correlation")
        self.assertEqual(status["task_sig"], exact_task_sig(stdin, arguments))


class ClassifierProcessTests(WrapperTestCase):
    def test_classifier_is_executable_sibling_without_embedded_heredoc(self) -> None:
        self.assertTrue(CLASSIFIER.is_file())
        self.assertEqual(stat.S_IMODE(CLASSIFIER.stat().st_mode), 0o755)
        self.assertEqual(
            CLASSIFIER.read_text(encoding="utf-8").splitlines()[0],
            "#!/usr/bin/env python3",
        )
        wrapper_text = WRAPPER.read_text(encoding="utf-8")
        self.assertNotIn("<<'PY'", wrapper_text)
        self.assertIn("codex-with-rotation-classify", wrapper_text)

    def test_streaming_classification_of_100k_lines_stays_below_50_mib(self) -> None:
        fixture = self.fixture()
        stdout_path = fixture.root / "large.stdout.jsonl"
        stderr_path = fixture.root / "large.stderr.log"
        rss_path = fixture.root / "classifier.max-rss-kib"
        line = b'{"type":"turn.completed","result":"bounded"}\n'
        with stdout_path.open("wb") as stream:
            for _index in range(100_000):
                stream.write(line)
        stderr_path.write_bytes(b"")

        result = subprocess.run(
            [
                "/usr/bin/time",
                "-f",
                "%M",
                "-o",
                str(rss_path),
                sys.executable,
                str(CLASSIFIER),
                "classify",
                str(stdout_path),
                str(stderr_path),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["class"], "unknown")
        self.assertEqual(summary["stdout_tail_lines"], 50)
        self.assertEqual(summary["stderr_tail_lines"], 0)
        peak_rss_kib = int(rss_path.read_text(encoding="ascii").strip())
        self.assertLess(peak_rss_kib, 50 * 1024)

    def test_streaming_classification_consumes_the_full_stream(self) -> None:
        fixture = self.fixture()
        stdout_path = fixture.root / "decisive.stdout.jsonl"
        stderr_path = fixture.root / "decisive.stderr.log"
        stdout_path.write_text(
            "\n".join(
                (
                    '{"type":"turn.failed","error":{"code":"QuotaExceeded"}}',
                    "not-json-after-decision",
                    '{"type":"turn.failed","error":{"kind":"CyberPolicyResponse"}}',
                )
            )
            + "\n",
            encoding="utf-8",
        )
        stderr_path.write_bytes(b"")

        result = subprocess.run(
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

        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["class"], "cyber")
        self.assertTrue(summary["has_malformed_line"])
        self.assertEqual(summary["stdout_tail_lines"], 3)

    def test_stderr_local_hook_still_consumes_the_stdout_stream(self) -> None:
        fixture = self.fixture()
        quota = {"type": "turn.failed", "error": {"code": "QuotaExceeded"}}
        cyber = {
            "type": "turn.failed",
            "error": {"kind": "CyberPolicyResponse"},
        }

        result = run_classifier(
            fixture,
            (quota, "not-json", cyber),
            stderr_lines=(
                "before marker",
                "Command blocked by PreToolUse hook: fixture",
                "after marker",
            ),
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["class"], "local_hook_deny")
        self.assertTrue(summary["has_malformed_line"])
        self.assertEqual(summary["stdout_tail_lines"], 3)
        self.assertEqual(summary["stderr_tail_lines"], 3)


class ClassificationTests(WrapperTestCase):
    def test_stream_precedence_is_independent_of_arrival_order(self) -> None:
        quota = {"type": "turn.failed", "error": {"code": "QuotaExceeded"}}
        cyber = {
            "type": "turn.failed",
            "error": {"kind": "CyberPolicyResponse"},
        }
        local = {"item": {"type": "approval_denied"}}
        cases = (
            ((quota, cyber), "cyber"),
            ((cyber, quota), "cyber"),
            ((quota, local), "local_hook_deny"),
            ((local, quota), "local_hook_deny"),
            ((cyber, local), "local_hook_deny"),
            ((local, cyber), "local_hook_deny"),
        )

        for events, expected_class in cases:
            with self.subTest(events=events, expected_class=expected_class):
                fixture = self.fixture()
                result = run_classifier(fixture, events)

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)["class"], expected_class)

    def test_every_cyber_variant_in_both_casings_retries_same_account(self) -> None:
        for canonical in CYBER_VARIANTS:
            for variant in (canonical, canonical.upper()):
                with self.subTest(variant=variant):
                    fixture = self.fixture()
                    event = {"type": "turn.failed", "error": {"kind": variant}}
                    result = fixture.run([event_response(event), success_response()])
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(
                        [call["account_id"] for call in fixture.invocations()],
                        ["account-a", "account-a"],
                    )

    def test_guardian_variants_and_denial_fields_in_both_casings(self) -> None:
        for guardian in ("GuardianAssessmentEvent", "guardian_assessment_event"):
            for variant in (guardian, guardian.upper()):
                for field in ("decision_source", "rationale"):
                    with self.subTest(variant=variant, field=field):
                        fixture = self.fixture()
                        event = {
                            "type": "error",
                            "detail": {"type": variant, field: "Policy BLOCK decision"},
                        }
                        result = fixture.run(
                            [event_response(event), success_response()]
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(
                            [call["account_id"] for call in fixture.invocations()],
                            ["account-a", "account-a"],
                        )

    def test_guardian_denying_risk_level_only_is_cyber(self) -> None:
        for risk_level in DENYING_GUARDIAN_RISK_LEVELS:
            with self.subTest(risk_level=risk_level):
                fixture = self.fixture()
                event = {
                    "type": "turn.failed",
                    "detail": {
                        "type": "GuardianAssessmentEvent",
                        "risk_level": risk_level,
                    },
                }

                result = fixture.run([event_response(event), success_response()])

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    [call["account_id"] for call in fixture.invocations()],
                    ["account-a", "account-a"],
                )

    def test_guardian_low_risk_level_only_is_unknown(self) -> None:
        fixture = self.fixture()
        event = {
            "type": "turn.failed",
            "detail": {
                "type": "guardian_assessment_event",
                "risk_level": "low",
            },
        }

        result = fixture.run([event_response(event)])

        self.assertEqual(result.returncode, 76, result.stderr)
        self.assertEqual(status_from(result)["class"], "unknown")
        self.assertEqual(
            [call["account_id"] for call in fixture.invocations()], ["account-a"]
        )

    def test_every_quota_variant_in_both_casings_rotates(self) -> None:
        for canonical in QUOTA_VARIANTS:
            for variant in (canonical, canonical.upper()):
                with self.subTest(variant=variant):
                    fixture = self.fixture()
                    event = {"type": "turn.failed", "error": {"code": variant}}
                    result = fixture.run([event_response(event), success_response()])
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(fixture.state()["active_account_id"], "account-b")

    def test_http_429_rotates(self) -> None:
        fixture = self.fixture()
        event = {
            "type": "error",
            "error": {"codex_error_http_status_code": 429},
        }
        result = fixture.run([event_response(event), success_response()])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(fixture.state()["active_account_id"], "account-b")

    def test_local_hook_variants_in_both_casings_retry_same_account(self) -> None:
        events = (
            {"item": {"type": "approval_denied"}},
            {"item": {"type": "APPROVAL_DENIED"}},
            {
                "item": {
                    "type": "CommandExecutionApproval",
                    "decision": "denied",
                }
            },
            {
                "item": {
                    "type": "COMMANDEXECUTIONAPPROVAL",
                    "decision": "DENIED",
                }
            },
        )
        for event in events:
            with self.subTest(event=event):
                fixture = self.fixture()
                result = fixture.run([event_response(event), success_response()])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    [call["account_id"] for call in fixture.invocations()],
                    ["account-a", "account-a"],
                )

    def test_local_hook_stderr_substring_retries(self) -> None:
        fixture = self.fixture()
        blocked = {
            "stdout": [],
            "stderr": "Command blocked by PreToolUse hook: fixture",
            "exit": 9,
        }
        result = fixture.run([blocked, success_response()])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(fixture.invocations()), 2)

    def test_malformed_line_fails_closed_with_raw_tail(self) -> None:
        fixture = self.fixture()
        result = fixture.run(
            [{"stdout": ["not-json"], "stderr": "raw-error", "exit": 4}]
        )

        self.assertEqual(result.returncode, 76)
        self.assertEqual(status_from(result)["class"], "unknown")
        self.assertIn(b"not-json", result.stderr)
        self.assertIn(b"raw-error", result.stderr)

    def test_mixed_event_obeys_local_then_cyber_then_quota_precedence(self) -> None:
        local_fixture = self.fixture()
        local_event = {
            "type": "turn.failed",
            "item": {"type": "approval_denied"},
            "error": {"cyber": "CyberPolicyResponse", "quota": "QuotaExceeded"},
        }
        local_result = local_fixture.run(
            [event_response(local_event), event_response(local_event)]
        )
        self.assertEqual(local_result.returncode, 73)
        self.assertEqual(status_from(local_result)["class"], "local_hook_deny_exceeded")
        self.assertEqual(local_fixture.state()["active_account_id"], "account-a")

        cyber_fixture = self.fixture()
        cyber_event = {
            "type": "error",
            "error": {"cyber": "CyberPolicyResponse", "quota": "QuotaExceeded"},
        }
        cyber_result = cyber_fixture.run(
            [event_response(cyber_event), event_response(cyber_event)]
        )
        self.assertEqual(cyber_result.returncode, 75)
        self.assertEqual(status_from(cyber_result)["class"], "cyber_escalate")
        self.assertEqual(cyber_fixture.state()["active_account_id"], "account-a")


class RotationStateMachineTests(WrapperTestCase):
    def test_three_distinct_accounts_rotate_and_preserve_pool_modes(self) -> None:
        fixture = self.fixture()
        before_modes = {
            name: stat.S_IMODE((fixture.state_dir / name).stat().st_mode)
            for name in POOL_NAMES
        }
        before_bytes = {
            name: (fixture.state_dir / name).read_bytes() for name in POOL_NAMES
        }
        quota = event_response(
            {"type": "turn.failed", "error": {"code": "QuotaExceeded"}}
        )

        result = fixture.run([quota, success_response()])

        self.assertEqual(result.returncode, 0, result.stderr)
        state = fixture.state()
        self.assertEqual(state["active_account_id"], "account-b")
        self.assertIn("account-a", state["cooldowns"])
        self.assertTrue(
            all(call["auth_mode"] == 0o600 for call in fixture.invocations())
        )
        self.assertEqual(
            before_modes,
            {
                name: stat.S_IMODE((fixture.state_dir / name).stat().st_mode)
                for name in POOL_NAMES
            },
        )
        self.assertEqual(
            before_bytes,
            {name: (fixture.state_dir / name).read_bytes() for name in POOL_NAMES},
        )

    def test_state_writes_prune_expired_cooldowns_and_cyber_tasks(self) -> None:
        fixture = self.fixture()
        self.assertEqual(fixture.initialize_state().returncode, 75)
        state = fixture.state()
        now = datetime.now(timezone.utc)
        state["cooldowns"]["expired-account"] = {
            "until_utc": utc_text(now - timedelta(seconds=1)),
            "variant": "fixture",
            "observed_utc": utc_text(now - timedelta(seconds=601)),
        }
        state["cooldowns"]["fresh-account"] = {
            "until_utc": utc_text(now + timedelta(seconds=600)),
            "variant": "fixture",
            "observed_utc": utc_text(now),
        }
        state["cyber_streaks"]["tasks"]["expired-task"] = {
            "count": 1,
            "last_observed_utc": utc_text(now - timedelta(seconds=601)),
            "variant": "CyberPolicyResponse",
        }
        state["cyber_streaks"]["tasks"]["fresh-task"] = {
            "count": 1,
            "last_observed_utc": utc_text(now),
            "variant": "CyberPolicyResponse",
        }
        fixture.replace_state(state)
        quota = event_response(
            {"type": "turn.failed", "error": {"code": "QuotaExceeded"}}
        )

        result = fixture.run([quota, success_response()])

        self.assertEqual(result.returncode, 0, result.stderr)
        written_state = fixture.state()
        self.assertNotIn("expired-account", written_state["cooldowns"])
        self.assertIn("fresh-account", written_state["cooldowns"])
        tasks = written_state["cyber_streaks"]["tasks"]
        self.assertNotIn("expired-task", tasks)
        self.assertIn("fresh-task", tasks)

    def test_all_alternative_accounts_cooling_exits_72(self) -> None:
        fixture = self.fixture()
        self.assertEqual(fixture.initialize_state().returncode, 75)
        state = fixture.state()
        future = utc_text(datetime.now(timezone.utc) + timedelta(hours=1))
        for account_id in ("account-b", "account-c"):
            state["cooldowns"][account_id] = {
                "until_utc": future,
                "variant": "fixture",
                "observed_utc": utc_text(datetime.now(timezone.utc)),
            }
        fixture.replace_state(state)
        quota = event_response(
            {"type": "turn.failed", "error": {"code": "QuotaExceeded"}}
        )

        result = fixture.run([quota])

        self.assertEqual(result.returncode, 72)
        self.assertEqual(status_from(result)["class"], "quota_exhausted")

    def test_single_distinct_account_exits_74_only_when_rotation_needed(self) -> None:
        fixture = self.fixture(("same-account", "same-account", "same-account"))
        success = fixture.run([success_response()])
        self.assertEqual(success.returncode, 0, success.stderr)

        quota = event_response(
            {"type": "turn.failed", "error": {"code": "QuotaExceeded"}}
        )
        failure = fixture.run([quota])
        self.assertEqual(failure.returncode, 74)
        self.assertEqual(status_from(failure)["class"], "no_eligible_credential")

    def test_failed_id_guard_does_not_overwrite_concurrent_rotation(self) -> None:
        fixture = self.fixture()
        self.assertEqual(fixture.initialize_state().returncode, 75)
        signal = fixture.root / "mock-started"
        release = fixture.root / "release-mock"
        quota = event_response(
            {"type": "turn.failed", "error": {"code": "QuotaExceeded"}}
        )
        quota.update({"signal": str(signal), "wait_for": str(release)})
        fixture.set_plan([quota, success_response()])

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fixture.run_existing_plan)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and not signal.exists():
                time.sleep(0.01)
            self.assertTrue(
                signal.exists(), "mock Codex did not reach synchronization point"
            )
            state = fixture.state()
            state["active_account_id"] = "account-b"
            fixture.replace_state(state)
            release.touch()
            result = future.result(timeout=12)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(fixture.state()["active_account_id"], "account-b")
        self.assertEqual(
            [call["account_id"] for call in fixture.invocations()],
            ["account-a", "account-b"],
        )

    def test_cyber_retry_keeps_pinned_account_during_concurrent_rotation(self) -> None:
        fixture = self.fixture()
        self.assertEqual(fixture.initialize_state().returncode, 75)
        signal = fixture.root / "cyber-started"
        release = fixture.root / "release-cyber"
        cyber = event_response(
            {"type": "turn.failed", "error": {"kind": "CyberPolicyResponse"}}
        )
        cyber.update({"signal": str(signal), "wait_for": str(release)})
        fixture.set_plan([cyber, success_response()])

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fixture.run_existing_plan)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and not signal.exists():
                time.sleep(0.01)
            self.assertTrue(
                signal.exists(), "mock Codex did not reach synchronization point"
            )
            state = fixture.state()
            state["active_account_id"] = "account-b"
            fixture.replace_state(state)
            release.touch()
            result = future.result(timeout=12)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(fixture.state()["active_account_id"], "account-b")
        self.assertEqual(
            [call["account_id"] for call in fixture.invocations()],
            ["account-a", "account-a"],
        )

    def test_wraparound_moves_last_account_to_first(self) -> None:
        fixture = self.fixture()
        self.assertEqual(fixture.initialize_state().returncode, 75)
        state = fixture.state()
        state["active_account_id"] = "account-c"
        fixture.replace_state(state)
        quota = event_response(
            {"type": "turn.failed", "error": {"code": "QuotaExceeded"}}
        )

        result = fixture.run([quota, success_response()])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(fixture.state()["active_account_id"], "account-a")
        self.assertEqual(
            [call["account_id"] for call in fixture.invocations()],
            ["account-c", "account-a"],
        )


class CyberStreakTests(WrapperTestCase):
    def test_first_hit_retries_then_success_resets_streak(self) -> None:
        fixture = self.fixture()
        cyber = event_response(
            {"type": "turn.failed", "error": {"kind": "CyberPolicyResponse"}}
        )

        result = fixture.run([cyber, success_response()])

        self.assertEqual(result.returncode, 0, result.stderr)
        status = status_from(result)
        self.assertEqual(status["attempts"], 2)
        self.assertNotIn(
            status["task_sig"], fixture.state()["cyber_streaks"]["tasks"]
        )

    def test_second_hit_within_window_exits_75(self) -> None:
        fixture = self.fixture()
        cyber = event_response(
            {"type": "turn.failed", "error": {"kind": "CyberPolicyResponse"}}
        )

        result = fixture.run([cyber, cyber])

        self.assertEqual(result.returncode, 75)
        status = status_from(result)
        self.assertEqual(status["class"], "cyber_escalate")
        self.assertRegex(status["task_sig"], r"^[0-9a-f]{64}$")
        task = fixture.state()["cyber_streaks"]["tasks"][status["task_sig"]]
        self.assertEqual(task["count"], 2)

    def test_non_cyber_class_resets_existing_streak(self) -> None:
        fixture = self.fixture()
        self.assertEqual(fixture.initialize_state().returncode, 75)
        stdin = b"same-task"
        task_sig = exact_task_sig(stdin, ())
        state = fixture.state()
        state["cyber_streaks"]["tasks"][task_sig] = {
            "count": 1,
            "last_observed_utc": utc_text(datetime.now(timezone.utc)),
            "variant": "CyberPolicyResponse",
        }
        fixture.replace_state(state)
        local = event_response({"item": {"type": "approval_denied"}})

        result = fixture.run([local, local], stdin=stdin)

        self.assertEqual(result.returncode, 73)
        self.assertNotIn(task_sig, fixture.state()["cyber_streaks"]["tasks"])

    def test_streak_older_than_600_seconds_restarts_at_one(self) -> None:
        fixture = self.fixture()
        self.assertEqual(fixture.initialize_state().returncode, 75)
        stdin = b"aged-task"
        task_sig = exact_task_sig(stdin, ())
        state = fixture.state()
        state["cyber_streaks"]["tasks"][task_sig] = {
            "count": 1,
            "last_observed_utc": utc_text(
                datetime.now(timezone.utc) - timedelta(seconds=601)
            ),
            "variant": "CyberPolicyResponse",
        }
        fixture.replace_state(state)
        cyber = event_response(
            {"type": "turn.failed", "error": {"kind": "CyberPolicyResponse"}}
        )

        result = fixture.run([cyber, success_response()], stdin=stdin)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(task_sig, fixture.state()["cyber_streaks"]["tasks"])


class LocalHookTests(WrapperTestCase):
    def test_first_local_hook_retries_and_second_exits_73(self) -> None:
        local = event_response({"item": {"type": "approval_denied"}})

        retry_fixture = self.fixture()
        retry_result = retry_fixture.run([local, success_response()])
        self.assertEqual(retry_result.returncode, 0, retry_result.stderr)
        self.assertEqual(status_from(retry_result)["attempts"], 2)

        deny_fixture = self.fixture()
        deny_result = deny_fixture.run([local, local])
        self.assertEqual(deny_result.returncode, 73)
        self.assertEqual(
            status_from(deny_result)["class"], "local_hook_deny_exceeded"
        )


class ExitCodeTests(WrapperTestCase):
    def assert_status(
        self,
        result: subprocess.CompletedProcess[bytes],
        expected_exit: int,
        expected_class: str,
    ) -> None:
        self.assertEqual(result.returncode, expected_exit, result.stderr)
        status = status_from(result)
        self.assertEqual(status["wrapper"], "codex-with-rotation")
        self.assertEqual(status["class"], expected_class)
        self.assertIn("codex_exit", status)

    def test_all_wrapper_exit_codes_have_status_json(self) -> None:
        success_fixture = self.fixture()
        self.assert_status(success_fixture.run([success_response()]), 0, "success")

        usage = subprocess.run(
            [str(WRAPPER)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
        self.assert_status(usage, 1, "generic_failure")

        budget_fixture = self.fixture()
        local = event_response({"item": {"type": "approval_denied"}})
        cyber = event_response(
            {"type": "turn.failed", "error": {"kind": "CyberPolicyResponse"}}
        )
        quota = event_response(
            {"type": "turn.failed", "error": {"code": "QuotaExceeded"}}
        )
        self.assert_status(
            budget_fixture.run([local, cyber, quota]), 70, "launch_budget_exhausted"
        )

        corrupt_fixture = self.fixture()
        state_path = corrupt_fixture.state_dir / ".auth-active"
        state_path.write_text("not-json", encoding="utf-8")
        state_path.chmod(0o600)
        self.assert_status(
            corrupt_fixture.run([success_response()]), 71, "wrapper_failure"
        )

        exhausted_fixture = self.fixture()
        self.assertEqual(exhausted_fixture.initialize_state().returncode, 75)
        exhausted_state = exhausted_fixture.state()
        future = utc_text(datetime.now(timezone.utc) + timedelta(hours=1))
        for account_id in ("account-b", "account-c"):
            exhausted_state["cooldowns"][account_id] = {
                "until_utc": future,
                "variant": "fixture",
                "observed_utc": utc_text(datetime.now(timezone.utc)),
            }
        exhausted_fixture.replace_state(exhausted_state)
        self.assert_status(exhausted_fixture.run([quota]), 72, "quota_exhausted")

        local_fixture = self.fixture()
        self.assert_status(
            local_fixture.run([local, local]), 73, "local_hook_deny_exceeded"
        )

        single_fixture = self.fixture(("only", "only", "only"))
        self.assert_status(
            single_fixture.run([quota]), 74, "no_eligible_credential"
        )

        cyber_fixture = self.fixture()
        self.assert_status(
            cyber_fixture.run([cyber, cyber]), 75, "cyber_escalate"
        )

        force_fixture = self.fixture()
        self.assert_status(
            force_fixture.run([], extra_environment={"CODEX_KIMI_FORCE": "1"}),
            75,
            "force_kimi",
        )

        unknown_fixture = self.fixture()
        unknown = event_response(
            {"type": "turn.failed", "error": {"code": "unrecognized"}}
        )
        self.assert_status(unknown_fixture.run([unknown]), 76, "unknown")

    def test_exit_71_preserves_private_diagnostics_and_reports_path(self) -> None:
        fixture = self.fixture()
        hook_path = fixture.state_dir / "hooks" / "pre-tool.sh"
        hook_path.write_text("hook fixture\n", encoding="utf-8")
        plugins_path = fixture.state_dir / "plugins"
        plugins_path.mkdir()
        plugin_path = plugins_path / "plugin.toml"
        plugin_path.write_text("plugin fixture\n", encoding="utf-8")
        (fixture.fake_bin / "codex").unlink()
        proof_root = fixture.root / "proof-root"

        result = fixture.run(
            [success_response()],
            extra_environment={
                "SESSION_ID": VALID_SESSION_ID,
                "KIMI_PROOF_ROOT": str(proof_root),
                "PATH": "/usr/bin:/bin",
            },
        )

        self.assertEqual(result.returncode, 71, result.stderr)
        failures = (
            proof_root
            / VALID_SESSION_ID
            / "codex-with-rotation-failures"
        )
        preserved = list(failures.iterdir()) if failures.is_dir() else []
        self.assertEqual(len(preserved), 1)
        self.assertEqual(stat.S_IMODE(preserved[0].stat().st_mode), 0o700)
        attempts = list(preserved[0].glob("attempt-1.*"))
        self.assertEqual(len(attempts), 1)
        attempt_home = attempts[0]
        self.assertEqual(stat.S_IMODE(attempt_home.stat().st_mode), 0o700)
        for directory in (attempt_home / "hooks", attempt_home / "plugins"):
            self.assertTrue(directory.is_dir())
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        for private_file in (
            attempt_home / "auth.json",
            attempt_home / "config.toml",
            attempt_home / "hooks" / hook_path.name,
            attempt_home / "plugins" / plugin_path.name,
        ):
            self.assertTrue(private_file.is_file())
            self.assertEqual(stat.S_IMODE(private_file.stat().st_mode), 0o600)
        reason_path = preserved[0] / "wrapper-error.log"
        self.assertEqual(stat.S_IMODE(reason_path.stat().st_mode), 0o600)
        self.assertIn(
            "could not launch Codex",
            reason_path.read_text(encoding="utf-8"),
        )
        self.assertIn(os.fsencode(preserved[0]), result.stderr)
        remaining = list((fixture.home / "tmp").glob("codex-with-rotation.*"))
        self.assertEqual(remaining, [])

    def test_exit_71_keeps_private_tmp_diagnostics_if_move_fails(self) -> None:
        fixture = self.fixture()
        (fixture.state_dir / "config.toml").unlink()

        result = fixture.run(
            [success_response()],
            extra_environment={
                "SESSION_ID": "diagnostic-fallback-session",
                "KIMI_PROOF_ROOT": "/",
            },
        )

        self.assertEqual(result.returncode, 71, result.stderr)
        remaining = list((fixture.home / "tmp").glob("codex-with-rotation.*"))
        self.assertEqual(len(remaining), 1)
        self.assertEqual(stat.S_IMODE(remaining[0].stat().st_mode), 0o700)
        self.assertTrue((remaining[0] / "wrapper-error.log").is_file())
        self.assertIn(os.fsencode(remaining[0]), result.stderr)

    def test_exit_71_rejects_invalid_diagnostic_session_ids(self) -> None:
        for session_id in INVALID_SESSION_IDS:
            with self.subTest(session_id=session_id):
                fixture = self.fixture()
                (fixture.state_dir / "config.toml").unlink()
                proof_root = fixture.root / "invalid-session-proof"

                result = fixture.run(
                    [success_response()],
                    extra_environment={
                        "SESSION_ID": session_id,
                        "KIMI_PROOF_ROOT": str(proof_root),
                    },
                )

                self.assertEqual(result.returncode, 71, result.stderr)
                self.assertFalse(proof_root.exists())
                remaining = list(
                    (fixture.home / "tmp").glob("codex-with-rotation.*")
                )
                self.assertEqual(len(remaining), 1)
                self.assertEqual(stat.S_IMODE(remaining[0].stat().st_mode), 0o700)


class AtomicityTests(WrapperTestCase):
    def test_parallel_quota_failures_do_not_double_rotate(self) -> None:
        fixture = self.fixture()
        self.assertEqual(fixture.initialize_state().returncode, 75)
        barrier_path = fixture.root / "quota-barrier"
        quota_event = {
            "type": "turn.failed",
            "error": {"code": "QuotaExceeded"},
        }
        quota_one = event_response(quota_event)
        quota_one.update({"barrier_path": str(barrier_path), "barrier_target": 2})
        quota_two = dict(quota_one)
        fixture.set_plan([quota_one, quota_two, success_response(), success_response()])

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(fixture.run_existing_plan) for _ in range(2)]
            results = [future.result(timeout=20) for future in futures]

        self.assertEqual([result.returncode for result in results], [0, 0])
        state = fixture.state()
        self.assertEqual(state["active_account_id"], "account-b")
        self.assertIn("account-a", state["cooldowns"])
        accounts = [call["account_id"] for call in fixture.invocations()]
        self.assertEqual(accounts.count("account-a"), 2)
        self.assertEqual(accounts.count("account-b"), 2)


class MarkerIssuerTests(WrapperTestCase):
    def run_marker(
        self,
        fixture: WrapperFixture,
        *arguments: str,
        session_id: str = "session-test",
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        overrides = {"KIMI_SESSION_ID": session_id}
        if extra_environment:
            overrides.update(extra_environment)
        environment = fixture.environment(overrides)
        return subprocess.run(
            [str(MARKER), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            timeout=10,
            check=False,
        )

    def test_cyber_marker_has_task_signature_name(self) -> None:
        fixture = self.fixture()
        task_sig = "a" * 64

        result = self.run_marker(
            fixture, "--cyber", task_sig, session_id=VALID_SESSION_ID
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        marker_path = Path(result.stdout.strip())
        self.assertEqual(marker_path.name, task_sig)
        self.assertTrue(marker_path.is_file())

    def test_invalid_session_ids_are_rejected(self) -> None:
        for session_id in INVALID_SESSION_IDS:
            with self.subTest(session_id=session_id):
                fixture = self.fixture()

                result = self.run_marker(
                    fixture,
                    "--cyber",
                    "e" * 64,
                    session_id=session_id,
                )

                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")

    def test_orchestration_marker_has_role_and_64_bit_nonce(self) -> None:
        fixture = self.fixture()

        result = self.run_marker(fixture, "--orchestration", "critic-A")

        self.assertEqual(result.returncode, 0, result.stderr)
        marker_path = Path(result.stdout.strip())
        self.assertRegex(marker_path.name, r"^orchestration-critic-A-[0-9a-f]{16}$")
        self.assertTrue(marker_path.is_file())

    def test_concurrent_identical_cyber_issue_calls_both_succeed(self) -> None:
        fixture = self.fixture()
        task_sig = "b" * 64

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(self.run_marker, fixture, "--cyber", task_sig)
                for _ in range(2)
            ]
            results = [future.result(timeout=10) for future in futures]

        self.assertEqual([result.returncode for result in results], [0, 0])
        self.assertEqual(results[0].stdout.strip(), results[1].stdout.strip())
        self.assertTrue(Path(results[0].stdout.strip()).is_file())

    def test_marker_honors_kimi_proof_root(self) -> None:
        fixture = self.fixture()
        proof_root = fixture.root / "test-proof"

        result = self.run_marker(
            fixture,
            "--cyber",
            "c" * 64,
            extra_environment={"KIMI_PROOF_ROOT": str(proof_root)},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        marker_path = Path(result.stdout.strip())
        self.assertTrue(marker_path.is_relative_to(proof_root))
        self.assertTrue(marker_path.is_file())
        allowed = GateTests.run_gate_for_fixture(
            fixture,
            "session-test",
            extra_environment={"KIMI_PROOF_ROOT": str(proof_root)},
        )
        self.assertEqual(allowed.returncode, 0)
        self.assertEqual(allowed.stdout, "")
        self.assertFalse(marker_path.exists())

    def test_role_file_drives_issuer_help_and_gate_acceptance(self) -> None:
        fixture = self.fixture()
        roles = ROLES_FILE.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(roles), 7)
        self.assertEqual(len(set(roles)), len(roles))
        self.assertTrue(
            all(
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", role)
                for role in roles
            )
        )

        issuer_text = MARKER.read_text(encoding="utf-8")
        gate_text = GATE.read_text(encoding="utf-8")
        self.assertIn("codex-roles.txt", issuer_text)
        self.assertIn("codex-roles.txt", gate_text)
        for role in roles:
            self.assertNotIn(role, issuer_text)
            self.assertNotIn(role, gate_text)

            session_id = f"role-{role}"
            marker = self.run_marker(
                fixture,
                "--orchestration",
                role,
                session_id=session_id,
            )
            self.assertEqual(marker.returncode, 0, marker.stderr)
            allowed = GateTests.run_gate_for_fixture(fixture, session_id)
            self.assertEqual(allowed.returncode, 0)
            self.assertEqual(allowed.stdout, "")

        help_result = subprocess.run(
            [str(MARKER), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertTrue(all(role in help_result.stdout for role in roles))


class GateTests(WrapperTestCase):
    @staticmethod
    def run_gate_for_fixture(
        fixture: WrapperFixture,
        session_id: str,
        *,
        payload: JsonObject | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        gate_input = {"session_id": session_id}
        if payload:
            gate_input.update(payload)
        return subprocess.run(
            [str(GATE)],
            input=json.dumps(gate_input),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=fixture.environment(extra_environment),
            timeout=20,
            check=False,
        )

    def run_gate(
        self,
        fixture: WrapperFixture,
        session_id: str,
        *,
        payload: JsonObject | None = None,
        extra_environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return self.run_gate_for_fixture(
            fixture,
            session_id,
            payload=payload,
            extra_environment=extra_environment,
        )

    def test_gate_denies_without_marker_and_claims_marker_once(self) -> None:
        fixture = self.fixture()
        session_id = "gate-session"
        denied = self.run_gate(fixture, session_id)
        self.assertEqual(denied.returncode, 0)
        self.assertEqual(
            json.loads(denied.stdout)["hookSpecificOutput"]["permissionDecision"],
            "deny",
        )

        marker_result = subprocess.run(
            [
                str(MARKER),
                "--session",
                session_id,
                "--orchestration",
                "critic-B",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=fixture.environment(),
            timeout=10,
            check=False,
        )
        self.assertEqual(marker_result.returncode, 0, marker_result.stderr)
        marker_path = Path(marker_result.stdout.strip())

        allowed = self.run_gate(fixture, session_id)
        self.assertEqual(allowed.returncode, 0)
        self.assertEqual(allowed.stdout, "")
        self.assertFalse(marker_path.exists())

        denied_again = self.run_gate(fixture, session_id)
        self.assertEqual(
            json.loads(denied_again.stdout)["hookSpecificOutput"][
                "permissionDecision"
            ],
            "deny",
        )

    def test_invalid_session_ids_cannot_claim_normalized_markers(self) -> None:
        for session_id in INVALID_SESSION_IDS:
            with self.subTest(session_id=session_id):
                fixture = self.fixture()
                proof_root = fixture.root / "gate-proof"
                normalized_session = Path(
                    os.path.normpath(f"{proof_root}/{session_id}")
                )
                marker_dir = normalized_session / "cyber-escalation"
                marker_dir.mkdir(parents=True)
                marker_path = marker_dir / ("f" * 64)
                marker_path.write_text(f"{int(time.time())}\n", encoding="ascii")

                denied = self.run_gate(
                    fixture,
                    session_id,
                    extra_environment={"KIMI_PROOF_ROOT": str(proof_root)},
                )

                self.assertEqual(denied.returncode, 0, denied.stderr)
                self.assertNotEqual(
                    denied.stdout,
                    "",
                    "invalid session ID claimed a normalized marker",
                )
                self.assertEqual(
                    json.loads(denied.stdout)["hookSpecificOutput"][
                        "permissionDecision"
                    ],
                    "deny",
                )
                self.assertTrue(marker_path.exists())


class BootstrapIntegrationTests(WrapperTestCase):
    def run_bootstrap(
        self,
        fixture: WrapperFixture,
        data_root: Path,
        *arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(BOOTSTRAP), *arguments],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=fixture.environment({"KIMI_CODE_HOME": str(data_root)}),
            timeout=10,
            check=False,
        )

    @staticmethod
    def gate_hooks(config_path: Path) -> list[JsonObject]:
        hooks = tomllib.loads(config_path.read_text(encoding="utf-8")).get(
            "hooks", []
        )
        return [
            hook
            for hook in hooks
            if isinstance(hook, dict)
            and "codex-first-gate.sh" in str(hook.get("command", ""))
        ]

    def test_correct_gate_stanza_is_a_byte_for_byte_noop(self) -> None:
        fixture = self.fixture()
        data_root = fixture.root / "bootstrap-correct"
        data_root.mkdir(mode=0o755)
        config_path = data_root / "config.toml"
        original = (
            "# existing\r\n" + CORRECT_GATE_STANZA.replace("\n", "\r\n")
        ).encode()
        config_path.write_bytes(original)

        result = self.run_bootstrap(fixture, data_root)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(config_path.read_bytes(), original)
        self.assertEqual(len(self.gate_hooks(config_path)), 1)

    def test_commented_out_gate_stanza_is_not_installed(self) -> None:
        fixture = self.fixture()
        data_root = fixture.root / "bootstrap-commented"
        data_root.mkdir(mode=0o755)
        config_path = data_root / "config.toml"
        original = textwrap.dedent(
            """
            # [[hooks]]
            # event = "PreToolUse"
            # matcher = "^(Agent|AgentSwarm)$"
            # command = "codex-first-gate.sh"
            """
        ).lstrip()
        config_path.write_text(original, encoding="utf-8")

        result = self.run_bootstrap(fixture, data_root)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(config_path.read_text(encoding="utf-8").startswith(original))
        self.assertEqual(len(self.gate_hooks(config_path)), 1)

    def test_wrong_gate_matcher_is_replaced(self) -> None:
        fixture = self.fixture()
        data_root = fixture.root / "bootstrap-wrong-matcher"
        data_root.mkdir(mode=0o755)
        config_path = data_root / "config.toml"
        config_path.write_text(
            CORRECT_GATE_STANZA.replace(
                "^(Agent|AgentSwarm)$", "^(Edit|Write)$"
            ),
            encoding="utf-8",
        )

        result = self.run_bootstrap(fixture, data_root)

        self.assertEqual(result.returncode, 0, result.stderr)
        gate_hooks = self.gate_hooks(config_path)
        self.assertEqual(len(gate_hooks), 1)
        matcher = re.compile(str(gate_hooks[0]["matcher"]))
        self.assertIsNotNone(matcher.fullmatch("Agent"))
        self.assertIsNotNone(matcher.fullmatch("AgentSwarm"))

    def test_duplicate_correct_gate_stanzas_are_deduplicated(self) -> None:
        fixture = self.fixture()
        data_root = fixture.root / "bootstrap-duplicate"
        data_root.mkdir(mode=0o755)
        config_path = data_root / "config.toml"
        config_path.write_text(
            CORRECT_GATE_STANZA + "\n" + CORRECT_GATE_STANZA,
            encoding="utf-8",
        )

        result = self.run_bootstrap(fixture, data_root)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.gate_hooks(config_path)), 1)

    def test_template_and_existing_config_receive_gate_hook_once(self) -> None:
        fixture = self.fixture()
        stanza_marker = "codex-first-gate.sh"
        template_text = CONFIG_TEMPLATE.read_text(encoding="utf-8")
        self.assertEqual(template_text.count(stanza_marker), 1)

        data_root = fixture.root / "bootstrap-existing"
        data_root.mkdir(mode=0o755)
        config_path = data_root / "config.toml"
        original = b"# local configuration\n[local]\nenabled = true\n"
        config_path.write_bytes(original)
        config_path.chmod(0o644)

        first = self.run_bootstrap(fixture, data_root)
        second = self.run_bootstrap(fixture, data_root)

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        materialized = config_path.read_bytes()
        self.assertTrue(materialized.startswith(original))
        self.assertEqual(materialized.count(stanza_marker.encode()), 1)
        self.assertEqual(stat.S_IMODE(config_path.stat().st_mode), 0o600)

    def test_help_describes_materialization_without_writing_config(self) -> None:
        fixture = self.fixture()
        data_root = fixture.root / "bootstrap-help"
        data_root.mkdir(mode=0o755)

        result = self.run_bootstrap(fixture, data_root, "--help")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Usage:", result.stdout)
        self.assertFalse((data_root / "config.toml").exists())


class RepositoryContractTests(WrapperTestCase):
    def test_runner_invokes_codex_rotation_suite(self) -> None:
        runner_text = RUNNER.read_text(encoding="utf-8")
        self.assertIn(
            'python3 "$ROOT/bin/tests/test_codex_with_rotation.py"', runner_text
        )

    def test_capability_token_limitation_is_documented(self) -> None:
        help_result = subprocess.run(
            [str(WRAPPER), "--help"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )

        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn(CAPABILITY_TOKEN_LIMITATION, AGENTS.read_text(encoding="utf-8"))
        self.assertIn(CAPABILITY_TOKEN_LIMITATION, DOC.read_text(encoding="utf-8"))
        self.assertIn(CAPABILITY_TOKEN_LIMITATION, help_result.stdout)

    def test_agents_distinguishes_worker_execution_from_orchestration(self) -> None:
        agents_text = AGENTS.read_text(encoding="utf-8")
        self.assertIn("Delegated worker execution", agents_text)
        self.assertIn("Kimi orchestration primitives", agents_text)
        self.assertIn("lib/codex-roles.txt", agents_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
