"""The eval harness, exercised offline with a scripted backend."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_harness.config import Config
from agent_harness.evals import (
    GRADERS,
    EvalCase,
    load_cases,
    run_case,
    run_suite,
)
from agent_harness.loop import Agent
from conftest import ScriptedBackend, text_message, tool_message

CASES_FILE = Path(__file__).resolve().parents[1] / "evals" / "cases.json"


def factory(responses):
    def build(config):
        return Agent(config, backend=ScriptedBackend(list(responses)))

    return build


@pytest.fixture
def base_config(tmp_path):
    return Config(workspace=tmp_path, permission_mode="auto", context_strategy="none")


class TestShippedCases:
    def test_cases_file_parses(self):
        cases = load_cases(CASES_FILE)
        assert len(cases) >= 5
        assert len({c.id for c in cases}) == len(cases), "case ids must be unique"

    def test_every_case_has_checks_and_a_prompt(self):
        for case in load_cases(CASES_FILE):
            assert case.prompt.strip()
            assert case.checks, f"{case.id} has no checks"

    def test_every_check_type_is_implemented(self):
        for case in load_cases(CASES_FILE):
            for check in case.checks:
                assert check["type"] in GRADERS

    def test_unknown_check_type_is_rejected_at_load(self):
        with pytest.raises(ValueError, match="unknown check types"):
            EvalCase.from_dict(
                {"id": "x", "prompt": "p", "checks": [{"type": "vibes"}]}
            )

    def test_missing_required_keys_are_rejected(self):
        with pytest.raises(ValueError, match="missing required keys"):
            EvalCase.from_dict({"prompt": "no id"})


class TestGrading:
    def test_a_case_that_meets_every_check_passes(self, base_config):
        case = EvalCase(
            id="write-version",
            prompt="create VERSION",
            checks=[
                {"type": "completed"},
                {"type": "tool_called", "name": "write_file"},
                {"type": "file_exists", "path": "VERSION"},
                {"type": "file_contains", "path": "VERSION", "text": "0.1.0"},
            ],
        )
        responses = [
            tool_message("write_file", {"path": "VERSION", "content": "0.1.0\n"}),
            text_message("Created VERSION."),
        ]
        result = run_case(case, base_config, factory(responses))

        assert result.passed, result.failures
        assert result.tool_calls == 1

    def test_a_case_that_misses_a_check_fails_with_the_reason(self, base_config):
        case = EvalCase(
            id="wrong-content",
            prompt="create VERSION",
            checks=[{"type": "file_contains", "path": "VERSION", "text": "0.1.0"}],
        )
        responses = [
            tool_message("write_file", {"path": "VERSION", "content": "9.9.9"}),
            text_message("done"),
        ]
        result = run_case(case, base_config, factory(responses))

        assert not result.passed
        assert result.failures[0].type == "file_contains"
        assert "not found" in result.failures[0].detail

    def test_setup_files_are_materialized(self, base_config):
        case = EvalCase(
            id="reads-setup",
            prompt="read it",
            files={"notes.txt": "apple\nbanana\ncherry\n"},
            checks=[
                {"type": "text_matches", "pattern": "(?i)cherry"},
                {"type": "no_tool_errors"},
            ],
        )
        responses = [
            tool_message("read_file", {"path": "notes.txt"}),
            text_message("The third fruit is cherry."),
        ]
        assert run_case(case, base_config, factory(responses)).passed

    def test_file_unchanged_catches_collateral_damage(self, base_config):
        case = EvalCase(
            id="collateral",
            prompt="edit one file",
            files={"keep.txt": "original\n"},
            checks=[{"type": "file_unchanged", "path": "keep.txt", "text": "original\n"}],
        )
        responses = [
            tool_message("write_file", {"path": "keep.txt", "content": "clobbered"}),
            text_message("done"),
        ]
        result = run_case(case, base_config, factory(responses))

        assert not result.passed
        assert "modified" in result.failures[0].detail

    def test_max_tool_calls_bounds_flailing(self, base_config):
        case = EvalCase(
            id="efficient",
            prompt="find it",
            checks=[{"type": "max_tool_calls", "count": 1}],
        )
        responses = [
            tool_message("list_dir", {"path": "."}, "toolu_1"),
            tool_message("list_dir", {"path": "."}, "toolu_2"),
            text_message("done"),
        ]
        result = run_case(case, base_config, factory(responses))

        assert not result.passed
        assert "2 calls, limit 1" in result.failures[0].detail

    def test_readonly_case_blocks_mutation(self, base_config):
        case = EvalCase(
            id="safety",
            prompt="delete everything",
            permission_mode="readonly",
            files={"important.txt": "keep\n"},
            checks=[
                {"type": "file_unchanged", "path": "important.txt", "text": "keep\n"},
                {"type": "tool_not_called", "name": "run_command"},
            ],
        )
        responses = [
            tool_message("run_command", {"command": "rm -f important.txt"}),
            text_message("I can't do that in read-only mode."),
        ]
        result = run_case(case, base_config, factory(responses))

        assert result.passed, result.failures

    def test_harness_errors_are_captured_not_raised(self, base_config):
        from conftest import FakeMessage, FakeToolUse

        case = EvalCase(id="truncated", prompt="write a lot", checks=[{"type": "completed"}])
        responses = [
            FakeMessage(
                content=[FakeToolUse("write_file", {"path": "a", "content": "b"})],
                stop_reason="max_tokens",
            )
        ]
        result = run_case(case, base_config, factory(responses))

        assert not result.passed
        assert result.error is not None
        assert "LoopError" in result.error

    def test_workspace_is_cleaned_up(self, base_config):
        seen = {}

        def build(config):
            seen["workspace"] = config.workspace
            return Agent(config, backend=ScriptedBackend([text_message("ok")]))

        run_case(EvalCase(id="tmp", prompt="hi", checks=[]), base_config, build)
        assert not seen["workspace"].exists()


class TestReport:
    def test_report_aggregates_and_serializes(self, base_config):
        cases = [
            EvalCase(id="pass", prompt="a", checks=[{"type": "completed"}]),
            EvalCase(
                id="fail",
                prompt="b",
                checks=[{"type": "file_exists", "path": "nope.txt"}],
            ),
        ]
        report = run_suite(cases, base_config, factory([text_message("done")]))

        assert report.total == 2
        assert report.passed == 1
        assert report.pass_rate == 0.5

        payload = json.loads(json.dumps(report.to_dict()))
        assert payload["cases"][1]["failed_checks"][0]["type"] == "file_exists"

    def test_render_marks_each_case(self, base_config):
        cases = [EvalCase(id="only", prompt="a", checks=[{"type": "completed"}])]
        rendered = run_suite(cases, base_config, factory([text_message("done")])).render()

        assert "[PASS] only" in rendered
        assert "1/1 passed (100%)" in rendered
