from __future__ import annotations

import json

import pytest

from agent_harness import cli
from agent_harness.errors import RefusalError
from agent_harness.loop import Agent
from conftest import ScriptedBackend, text_message, tool_message


@pytest.fixture
def stub_agent(monkeypatch):
    """Replace the real Agent with one driven by a scripted backend."""
    captured = {}

    def install(responses):
        def build(config):
            captured["config"] = config
            return Agent(config, backend=ScriptedBackend(list(responses)))

        monkeypatch.setattr(cli, "Agent", build)
        return captured

    return install


class TestArgumentParsing:
    def test_flags_reach_the_config(self, stub_agent, tmp_path):
        captured = stub_agent([text_message("done")])
        code = cli.main(
            [
                "--model", "claude-sonnet-5",
                "--effort", "low",
                "--max-turns", "3",
                "--max-cost", "1.50",
                "--workspace", str(tmp_path),
                "--permission-mode", "auto",
                "--context-strategy", "compact",
                "do the thing",
            ]
        )
        config = captured["config"]

        assert code == 0
        assert config.model == "claude-sonnet-5"
        assert config.effort == "low"
        assert config.max_turns == 3
        assert config.max_cost_usd == 1.50
        assert config.permission_mode == "auto"
        assert config.context_strategy == "compact"
        assert config.workspace == tmp_path.resolve()

    def test_flags_beat_the_environment(self, stub_agent, monkeypatch):
        monkeypatch.setenv("AGENT_MODEL", "claude-haiku-4-5")
        captured = stub_agent([text_message("done")])

        cli.main(["--model", "claude-opus-5", "hello"])
        assert captured["config"].model == "claude-opus-5"

    def test_environment_is_used_when_no_flag_is_given(self, stub_agent, monkeypatch):
        monkeypatch.setenv("AGENT_MAX_TURNS", "7")
        captured = stub_agent([text_message("done")])

        cli.main(["hello"])
        assert captured["config"].max_turns == 7

    def test_prompt_can_come_from_stdin(self, stub_agent, monkeypatch, capsys):
        import io

        monkeypatch.setattr("sys.stdin", io.StringIO("piped question\n"))
        stub_agent([text_message("piped answer")])

        assert cli.main(["-"]) == 0
        assert "piped answer" in capsys.readouterr().out


class TestExitCodes:
    def test_success_is_zero(self, stub_agent, capsys):
        stub_agent([text_message("the answer")])
        assert cli.main(["--quiet", "question"]) == 0
        assert capsys.readouterr().out.strip() == "the answer"

    def test_an_incomplete_run_is_non_zero(self, stub_agent):
        # Never stops calling tools, so it hits the turn ceiling.
        stub_agent([tool_message("list_dir", {"path": "."}) for _ in range(5)])
        assert cli.main(["--max-turns", "2", "--permission-mode", "auto", "go"]) == 1

    def test_a_harness_error_is_reported_and_non_zero(self, stub_agent, monkeypatch, capsys):
        def build(config):
            raise RefusalError("declined", category="cyber")

        monkeypatch.setattr(cli, "Agent", build)

        assert cli.main(["question"]) == 1
        assert "RefusalError" in capsys.readouterr().err

    def test_a_bad_config_value_is_exit_two(self, monkeypatch, capsys):
        monkeypatch.setenv("AGENT_MAX_TURNS", "not-a-number")
        assert cli.main(["question"]) == 2
        assert "configuration error" in capsys.readouterr().err

    def test_an_empty_prompt_is_exit_two(self, capsys):
        assert cli.main(["   "]) == 2
        assert "empty prompt" in capsys.readouterr().err


class TestOutput:
    def test_summary_goes_to_stderr_so_stdout_stays_pipeable(self, stub_agent, capsys):
        stub_agent([text_message("just the answer")])
        cli.main(["question"])
        out, err = capsys.readouterr()

        assert out.strip() == "just the answer"
        assert "end_turn" in err
        assert "tokens" in err

    def test_quiet_suppresses_the_summary(self, stub_agent, capsys):
        stub_agent([text_message("answer")])
        cli.main(["--quiet", "question"])
        assert capsys.readouterr().err == ""

    def test_transcript_is_written_when_asked(self, stub_agent, tmp_path, capsys):
        stub_agent([text_message("answer")])
        target = tmp_path / "runs"

        cli.main(["--quiet", "--transcript-dir", str(target), "question"])

        files = list(target.glob("run-*.json"))
        assert len(files) == 1
        payload = json.loads(files[0].read_text())
        assert payload["prompt"] == "question"
        assert payload["final_text"] == "answer"


class TestTranscriptOnFailure:
    """Regression: a failed run must still leave a transcript behind."""

    def test_partial_transcript_is_written_when_the_run_raises(
        self, stub_agent, tmp_path, capsys
    ):
        from conftest import FakeMessage, FakeToolUse

        stub_agent(
            [
                tool_message("list_dir", {"path": "."}, "toolu_1"),
                FakeMessage(
                    content=[FakeToolUse("write_file", {"path": "x", "content": "y"})],
                    stop_reason="max_tokens",
                ),
            ]
        )
        target = tmp_path / "runs"

        code = cli.main(
            ["--permission-mode", "auto", "--transcript-dir", str(target), "go"]
        )

        assert code == 1
        files = list(target.glob("run-*.json"))
        assert len(files) == 1, "the failing run left no transcript"
        payload = json.loads(files[0].read_text())
        assert payload["summary"]["stop_reason"] == "error"
        assert payload["tool_calls"][0]["name"] == "list_dir"
        assert "partial transcript" in capsys.readouterr().err

    def test_no_transcript_dir_means_no_write_and_no_crash(self, stub_agent, capsys):
        from conftest import FakeMessage, FakeToolUse

        stub_agent(
            [
                FakeMessage(
                    content=[FakeToolUse("write_file", {"path": "x", "content": "y"})],
                    stop_reason="max_tokens",
                )
            ]
        )
        assert cli.main(["--permission-mode", "auto", "go"]) == 1
        assert "LoopError" in capsys.readouterr().err
