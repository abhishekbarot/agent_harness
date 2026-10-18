"""Profile, planning, and memory: the parts of an agent around actions.

Actions (tools) and the loop have their own test modules. These cover the rest
of the component model -- who the agent is, how it plans, and what it keeps
between runs -- and how each one plugs into the loop without disturbing the
cached request prefix.
"""

from __future__ import annotations

import pytest

from agent_harness import cli
from agent_harness.config import Config
from agent_harness.errors import ConfigError, ToolError
from agent_harness.loop import Agent
from agent_harness.permissions import build_policy
from agent_harness.profiles import BUILTIN_PROFILES, MAX_PROFILE_CHARS, load_profile
from agent_harness.tools.base import Risk
from agent_harness.tools.memory import MAX_MEMORY_FILE_BYTES, MemoryTool
from agent_harness.tools.planning import UpdatePlanTool
from conftest import ScriptedBackend, text_message, tool_message


def make_agent(config, responses, **kwargs):
    return Agent(config, backend=ScriptedBackend(responses), **kwargs)


def system_text(agent: Agent) -> str:
    return agent.system[0]["text"]


# -- profiles ---------------------------------------------------------------


class TestProfiles:
    def test_builtin_profile_by_name(self):
        assert load_profile("reviewer") == BUILTIN_PROFILES["reviewer"]

    def test_profile_from_file(self, tmp_path):
        path = tmp_path / "persona.md"
        path.write_text("You are a release manager.\n", encoding="utf-8")
        assert load_profile(str(path)) == "You are a release manager."

    @pytest.mark.parametrize("content", ["", "   \n", "x" * (MAX_PROFILE_CHARS + 1)])
    def test_empty_or_oversized_profiles_are_rejected(self, tmp_path, content):
        path = tmp_path / "persona.md"
        path.write_text(content, encoding="utf-8")
        with pytest.raises(ConfigError):
            load_profile(str(path))

    def test_unknown_profile_is_a_config_error(self):
        with pytest.raises(ConfigError, match="unknown profile"):
            load_profile("no-such-profile")

    def test_config_profile_reaches_the_system_prompt(self, config):
        reviewer = Config(**{**config.__dict__, "profile": "reviewer"})
        agent = make_agent(reviewer, [])
        assert system_text(agent).startswith(BUILTIN_PROFILES["reviewer"])

    def test_explicit_instructions_still_win(self, config):
        agent = make_agent(config, [], instructions="Custom persona.")
        assert system_text(agent).startswith("Custom persona.")


# -- planning ---------------------------------------------------------------


class TestPlanTool:
    def test_plan_is_replaced_not_appended(self):
        tool = UpdatePlanTool()
        tool.run(steps=[{"step": "a", "status": "in_progress"}])
        result = tool.run(
            steps=[{"step": "a", "status": "completed"}, {"step": "b", "status": "pending"}]
        )
        assert [s.step for s in tool.steps] == ["a", "b"]
        assert "(1/2 completed)" in result.content
        assert "[x] a" in result.content and "[ ] b" in result.content
        assert tool.revisions == 2

    @pytest.mark.parametrize(
        "steps, message",
        [
            ([], "non-empty list"),
            ([{"step": "", "status": "pending"}], "non-empty 'step'"),
            ([{"step": "a", "status": "done"}], "status must be one of"),
            (
                [{"step": "a", "status": "in_progress"}, {"step": "b", "status": "in_progress"}],
                "only one step",
            ),
            ([{"step": str(i), "status": "pending"} for i in range(31)], "at most"),
        ],
    )
    def test_invalid_plans_are_tool_errors(self, steps, message):
        with pytest.raises(ToolError, match=message):
            UpdatePlanTool().run(steps=steps)

    def test_plan_is_read_only_and_needs_no_approval(self):
        policy = build_policy("readonly")
        tool = UpdatePlanTool()
        assert tool.risk is Risk.READ_ONLY
        assert policy.check(tool, {"steps": []}).allowed

    def test_schema_is_strict_compatible(self):
        schema = UpdatePlanTool().to_api_schema()
        assert schema["strict"] is True
        assert schema["input_schema"]["additionalProperties"] is False


class TestPlanInTheLoop:
    def test_run_result_carries_the_latest_plan(self, config):
        plan = [
            {"step": "read the file", "status": "completed"},
            {"step": "summarize", "status": "in_progress"},
        ]
        agent = make_agent(
            config, [tool_message("update_plan", {"steps": plan}), text_message("done")]
        )
        result = agent.run("go")

        assert [s.step for s in result.plan] == ["read the file", "summarize"]
        summary = result.summary(config.model)
        assert summary["plan_steps"] == 2
        assert summary["plan_completed"] == 1

    def test_planning_can_be_turned_off(self, config):
        agent = make_agent(Config(**{**config.__dict__, "planning": False}), [])
        assert "update_plan" not in agent.registry
        assert "update_plan" not in system_text(agent)

    def test_plan_hint_is_in_the_system_prompt(self, config):
        agent = make_agent(config, [])
        assert UpdatePlanTool.prompt_hint in system_text(agent)


# -- memory -----------------------------------------------------------------


@pytest.fixture
def memory(tmp_path):
    return MemoryTool(tmp_path / "mem")


class TestMemoryCommands:
    def test_api_schema_is_the_anthropic_defined_tool(self, memory):
        assert memory.to_api_schema() == {"type": "memory_20250818", "name": "memory"}

    def test_create_then_view(self, memory):
        memory.run(command="create", path="/memories/notes.md", file_text="one\ntwo\n")
        result = memory.run(command="view", path="/memories/notes.md")
        assert "1\tone" in result.content and "2\ttwo" in result.content

    def test_view_range(self, memory):
        memory.run(command="create", path="/memories/n.md", file_text="a\nb\nc\nd\n")
        result = memory.run(command="view", path="/memories/n.md", view_range=[2, 3])
        assert "2\tb" in result.content and "3\tc" in result.content
        assert "1\ta" not in result.content and "d" not in result.content

    def test_view_directory_lists_files(self, memory):
        memory.run(command="create", path="/memories/a/b.md", file_text="x")
        listing = memory.run(command="view", path="/memories").content
        assert "/memories/a/" in listing and "/memories/a/b.md" in listing

    def test_view_of_an_empty_store(self, memory):
        assert "(empty)" in memory.run(command="view", path="/memories").content

    def test_str_replace_needs_exactly_one_match(self, memory):
        memory.run(command="create", path="/memories/n.md", file_text="x x\n")
        with pytest.raises(ToolError, match="exactly once"):
            memory.run(command="str_replace", path="/memories/n.md", old_str="x", new_str="y")
        memory.run(command="str_replace", path="/memories/n.md", old_str="x x", new_str="y")
        assert (memory.root / "n.md").read_text() == "y\n"

    def test_insert(self, memory):
        memory.run(command="create", path="/memories/n.md", file_text="a\nc")
        memory.run(command="insert", path="/memories/n.md", insert_line=1, insert_text="b")
        assert (memory.root / "n.md").read_text() == "a\nb\nc\n"
        with pytest.raises(ToolError, match="between 0 and"):
            memory.run(command="insert", path="/memories/n.md", insert_line=9, insert_text="z")

    def test_rename_and_delete(self, memory):
        memory.run(command="create", path="/memories/old.md", file_text="x")
        memory.run(command="rename", old_path="/memories/old.md", new_path="/memories/new.md")
        assert (memory.root / "new.md").exists() and not (memory.root / "old.md").exists()
        memory.run(command="delete", path="/memories/new.md")
        assert not (memory.root / "new.md").exists()

    def test_cannot_delete_the_root(self, memory):
        with pytest.raises(ToolError, match="refusing"):
            memory.run(command="delete", path="/memories")

    def test_oversized_file_is_rejected(self, memory):
        with pytest.raises(ToolError, match="limit"):
            memory.run(
                command="create",
                path="/memories/big.md",
                file_text="x" * (MAX_MEMORY_FILE_BYTES + 1),
            )

    def test_unknown_command(self, memory):
        with pytest.raises(ToolError, match="unknown memory command"):
            memory.run(command="format", path="/memories")


class TestMemoryConfinement:
    """Memory paths are model output too."""

    @pytest.mark.parametrize(
        "path",
        ["/memories/../escape.md", "/memories/a/../../escape.md", "/etc/passwd", "notes.md",
         "/memoriesX/notes.md"],
    )
    def test_paths_cannot_leave_the_memory_root(self, memory, path):
        with pytest.raises(ToolError):
            memory.run(command="create", path=path, file_text="x")
        assert not (memory.root.parent / "escape.md").exists()

    def test_symlink_out_of_the_store_is_rejected(self, memory, tmp_path):
        memory.root.mkdir(parents=True)
        secret = tmp_path / "secret.txt"
        secret.write_text("classified", encoding="utf-8")
        (memory.root / "link.md").symlink_to(secret)
        with pytest.raises(ToolError, match="escapes"):
            memory.run(command="view", path="/memories/link.md")


class TestMemoryPermissions:
    def test_view_is_read_only_and_writes_are_not(self, memory):
        assert memory.risk_for({"command": "view"}) is Risk.READ_ONLY
        for command in ("create", "str_replace", "insert", "delete", "rename"):
            assert memory.risk_for({"command": command}) is Risk.WRITE

    def test_readonly_mode_allows_view_and_blocks_writes(self, memory):
        policy = build_policy("readonly")
        assert policy.check(memory, {"command": "view", "path": "/memories"}).allowed
        assert not policy.check(memory, {"command": "delete", "path": "/memories/x"}).allowed


class TestMemoryInTheLoop:
    def test_memory_is_off_unless_configured(self, config):
        agent = make_agent(config, [])
        assert "memory" not in agent.registry

    def test_memory_persists_across_runs(self, config, tmp_path):
        with_memory = Config(**{**config.__dict__, "memory_dir": tmp_path / "mem"})
        write = {"command": "create", "path": "/memories/prefs.md", "file_text": "tabs\n"}
        first = make_agent(with_memory, [tool_message("memory", write), text_message("saved")])
        first.run("remember I like tabs")

        read = {"command": "view", "path": "/memories/prefs.md"}
        second = make_agent(with_memory, [tool_message("memory", read), text_message("tabs")])
        result = second.run("what do I like?")

        tool_result = result.messages[2]["content"][0]
        assert "tabs" in tool_result["content"]
        assert not tool_result.get("is_error")

    def test_tool_order_and_prompt_are_stable(self, config, tmp_path):
        """Tools render first in the cached prefix; their order must not drift."""
        with_memory = Config(**{**config.__dict__, "memory_dir": tmp_path / "mem"})
        a, b = make_agent(with_memory, []), make_agent(with_memory, [])
        names = [t.name for t in a.registry]
        assert names[-2:] == ["update_plan", "memory"]
        assert a.registry.fingerprint() == b.registry.fingerprint()
        assert a.system == b.system
        assert MemoryTool.prompt_hint in system_text(a)


# -- configuration ----------------------------------------------------------


class TestConfiguration:
    def test_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AGENT_PROFILE", "explainer")
        monkeypatch.setenv("AGENT_MEMORY_DIR", str(tmp_path / "m"))
        monkeypatch.setenv("AGENT_PLANNING", "off")
        config = Config.from_env()
        assert config.profile == "explainer"
        assert config.memory_dir == (tmp_path / "m").resolve()
        assert config.planning is False

    def test_bad_planning_value(self, monkeypatch):
        monkeypatch.setenv("AGENT_PLANNING", "maybe")
        with pytest.raises(ConfigError, match="true or false"):
            Config.from_env()

    def test_cli_flags(self, monkeypatch, tmp_path):
        captured = {}

        def build(config):
            captured["config"] = config
            return Agent(config, backend=ScriptedBackend([text_message("done")]))

        monkeypatch.setattr(cli, "Agent", build)
        code = cli.main(
            [
                "--profile", "reviewer",
                "--memory-dir", str(tmp_path / "m"),
                "--no-plan",
                "--workspace", str(tmp_path),
                "review it",
            ]
        )
        config = captured["config"]
        assert code == 0
        assert config.profile == "reviewer"
        assert config.memory_dir == (tmp_path / "m").resolve()
        assert config.planning is False

    def test_cli_reports_a_bad_profile_as_an_error(self, capsys, tmp_path):
        code = cli.main(
            ["--profile", "nope", "--workspace", str(tmp_path), "--permission-mode", "deny", "x"]
        )
        assert code == 1
        assert "unknown profile" in capsys.readouterr().err
