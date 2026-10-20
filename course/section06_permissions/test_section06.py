"""Section 6 -- Permissions. Run with: pytest course/section06_permissions"""

from __future__ import annotations

import io

import pytest

from common.fakes import FakeToolUse
from common.harness import Decision, Risk, SimpleRegistry, Tool, ToolError, ToolResult
from loader import load


def make_tool(name: str, risk: Risk = Risk.READ_ONLY, fn=None, risk_fn=None) -> Tool:
    return Tool(
        name=name,
        description=name,
        input_schema={"type": "object"},
        fn=fn or (lambda **kw: ToolResult(f"{name} ran")),
        risk=risk,
        risk_fn=risk_fn,
    )


def memory_risk(tool_input):
    return Risk.READ_ONLY if tool_input.get("command") == "view" else Risk.WRITE


READ = make_tool("read_file", Risk.READ_ONLY)
WRITE = make_tool("write_file", Risk.WRITE)
SHELL = make_tool("run_command", Risk.DANGEROUS)
MEMORY = make_tool("memory", Risk.WRITE, risk_fn=memory_risk)


class Terminal(io.StringIO):
    """A fake stdin that says it is an interactive terminal."""

    def isatty(self) -> bool:
        return True


class Pipe(io.StringIO):
    """A fake stdin that is not a terminal -- like a cron job or CI."""

    def isatty(self) -> bool:
        return False


class RecordingApprover:
    """Answers with a fixed decision and records every question."""

    def __init__(self, decision: Decision) -> None:
        self.decision = decision
        self.asked: list[str] = []

    def __call__(self, tool, tool_input):
        self.asked.append(tool.name)
        return self.decision


# -- 6.1 ---------------------------------------------------------------------


class TestEx1Decide:
    ex = load(__file__, "ex1_decide")

    TABLE = {
        "auto": ("allow", "allow", "allow"),
        "ask": ("allow", "ask", "ask"),
        "readonly": ("allow", "deny", "deny"),
        "deny": ("deny", "deny", "deny"),
    }

    @pytest.mark.parametrize("mode", list(TABLE))
    def test_the_whole_table(self, mode):
        risks = (Risk.READ_ONLY, Risk.WRITE, Risk.DANGEROUS)
        assert tuple(self.ex.decide(mode, r) for r in risks) == self.TABLE[mode]

    @pytest.mark.parametrize("mode", ["Auto", "allow", "", "yolo"])
    def test_unknown_modes_are_errors_not_defaults(self, mode):
        with pytest.raises(ValueError):
            self.ex.decide(mode, Risk.READ_ONLY)


# -- 6.2 ---------------------------------------------------------------------


class TestEx2ConsoleApprover:
    ex = load(__file__, "ex2_console_approver")

    def ask(self, answer: str, tool: Tool = WRITE, tool_input=None):
        out = io.StringIO()
        approver = self.ex.ConsoleApprover(stream=Terminal(answer + "\n"), out=out)
        decision = approver(tool, tool_input or {"path": "notes.txt"})
        return decision, out.getvalue()

    @pytest.mark.parametrize("answer", ["y", "yes", "YES", "  y  "])
    def test_yes_allows_once(self, answer):
        decision, _ = self.ask(answer)
        assert decision.allowed and not decision.remember

    @pytest.mark.parametrize("answer", ["a", "always"])
    def test_always_allows_and_remembers(self, answer):
        decision, _ = self.ask(answer)
        assert decision.allowed and decision.remember

    def test_never_denies_and_remembers(self):
        decision, _ = self.ask("never")
        assert not decision.allowed and decision.remember

    @pytest.mark.parametrize("answer", ["n", "no", "", "sure", "yess"])
    def test_anything_else_denies(self, answer):
        decision, _ = self.ask(answer)
        assert not decision.allowed and not decision.remember

    def test_prompt_shows_the_call(self):
        _, shown = self.ask("y", tool_input={"path": "notes.txt", "content": "hi"})
        assert "write_file" in shown and "write" in shown
        assert "path: notes.txt" in shown and "content: hi" in shown
        assert "Allow?" in shown

    def test_prompt_shows_per_call_risk(self):
        _, shown = self.ask("y", tool=MEMORY, tool_input={"command": "view"})
        assert "read_only" in shown

    def test_long_values_are_cut(self):
        _, shown = self.ask("y", tool_input={"content": "x" * 5_000})
        assert "x" * 501 not in shown
        assert "[5000 chars total]" in shown

    def test_no_terminal_means_deny_without_asking(self):
        out = io.StringIO()
        stream = Pipe("y\n")
        decision = self.ex.ConsoleApprover(stream=stream, out=out)(WRITE, {"path": "a"})
        assert not decision.allowed
        assert "no interactive terminal" in decision.reason
        assert out.getvalue() == "", "nothing should be printed"
        assert stream.read() == "y\n", "nothing should be read"

    def test_a_stream_without_isatty_is_denied(self):
        decision = self.ex.ConsoleApprover(stream=object(), out=io.StringIO())(WRITE, {})
        assert not decision.allowed


# -- 6.3 ---------------------------------------------------------------------


class TestEx3Policy:
    ex = load(__file__, "ex3_policy")

    def policy(self, mode: str, decision: Decision | None = None):
        approver = RecordingApprover(decision or Decision.allow("ok"))
        return self.ex.PermissionPolicy(mode, approver), approver

    def test_auto_allows_everything_without_asking(self):
        policy, approver = self.policy("auto")
        assert all(policy.check(t, {}).allowed for t in (READ, WRITE, SHELL))
        assert approver.asked == []

    def test_ask_only_asks_about_risky_calls(self):
        policy, approver = self.policy("ask")
        assert policy.check(READ, {}).allowed
        policy.check(WRITE, {})
        policy.check(SHELL, {})
        assert approver.asked == ["write_file", "run_command"]

    def test_the_approver_decides(self):
        policy, _ = self.policy("ask", Decision.deny("no thanks"))
        decision = policy.check(WRITE, {})
        assert not decision.allowed and decision.reason == "no thanks"

    def test_readonly_denies_with_a_useful_reason(self):
        policy, approver = self.policy("readonly")
        assert policy.check(READ, {}).allowed
        decision = policy.check(WRITE, {})
        assert not decision.allowed
        assert "write_file" in decision.reason and "write" in decision.reason
        assert approver.asked == []

    def test_deny_blocks_even_reads(self):
        policy, _ = self.policy("deny")
        assert not policy.check(READ, {}).allowed

    def test_always_is_remembered_per_tool(self):
        policy, approver = self.policy("ask", Decision.allow("ok", remember=True))
        policy.check(WRITE, {})
        policy.check(WRITE, {})
        policy.check(SHELL, {})
        assert approver.asked == ["write_file", "run_command"], "ask once per tool"

    def test_never_is_remembered_too(self):
        policy, approver = self.policy("ask", Decision.deny("never", remember=True))
        policy.check(SHELL, {})
        assert not policy.check(SHELL, {}).allowed
        assert approver.asked == ["run_command"]

    def test_a_plain_yes_is_not_remembered(self):
        policy, approver = self.policy("ask", Decision.allow("once"))
        policy.check(WRITE, {})
        policy.check(WRITE, {})
        assert approver.asked == ["write_file", "write_file"]

    def test_deny_mode_beats_a_remembered_always(self):
        policy, _ = self.policy("ask", Decision.allow("ok", remember=True))
        policy.check(WRITE, {})
        policy.mode = "deny"
        assert not policy.check(WRITE, {}).allowed

    def test_risk_is_rated_per_call(self):
        policy, approver = self.policy("readonly")
        assert policy.check(MEMORY, {"command": "view"}).allowed
        assert not policy.check(MEMORY, {"command": "delete"}).allowed
        assert approver.asked == []


# -- 6.4 ---------------------------------------------------------------------


class TestEx4GatedDispatch:
    ex = load(__file__, "ex4_gated_dispatch")
    policy_module = load(__file__, "ex3_policy")

    def build(self, mode: str, decision: Decision):
        events: list[str] = []

        def tracked(name, risk, fn=None):
            def run(**kw):
                events.append(f"run {name}")
                return fn(**kw) if fn else ToolResult(f"{name} ran")

            return make_tool(name, risk, fn=run)

        def fail(**_):
            raise ToolError("disk full")

        registry = SimpleRegistry(
            [
                tracked("read_file", Risk.READ_ONLY),
                tracked("write_file", Risk.WRITE),
                tracked("run_command", Risk.DANGEROUS),
                tracked("broken", Risk.READ_ONLY, fn=fail),
            ]
        )

        def approver(tool, tool_input):
            events.append(f"ask {tool.name}")
            return decision

        policy = self.policy_module.PermissionPolicy(mode, approver)
        return registry, policy, events

    def test_approved_calls_run(self):
        registry, policy, _ = self.build("ask", Decision.allow("ok"))
        blocks = self.ex.gated_dispatch(
            registry, policy, [FakeToolUse("write_file", {"path": "a"}, "t1")]
        )
        assert blocks == [{"type": "tool_result", "tool_use_id": "t1", "content": "write_file ran"}]

    def test_a_denial_is_a_result_not_an_exception(self):
        registry, policy, events = self.build("ask", Decision.deny("too risky"))
        [block] = self.ex.gated_dispatch(
            registry, policy, [FakeToolUse("run_command", {"command": "rm -rf ."}, "t1")]
        )
        assert block["is_error"] is True
        assert block["content"] == "The user declined this tool call. Reason: too risky"
        assert "run run_command" not in events, "a denied tool must not run"

    def test_every_check_happens_before_any_tool_runs(self):
        registry, policy, events = self.build("ask", Decision.allow("ok"))
        calls = [
            FakeToolUse("write_file", {}, "t1"),
            FakeToolUse("run_command", {}, "t2"),
        ]
        self.ex.gated_dispatch(registry, policy, calls)
        assert events == ["ask write_file", "ask run_command", "run write_file", "run run_command"]

    def test_mixed_turn_keeps_order(self):
        registry, policy, _ = self.build("readonly", Decision.allow("unused"))
        calls = [
            FakeToolUse("read_file", {}, "t1"),
            FakeToolUse("write_file", {}, "t2"),
            FakeToolUse("ghost", {}, "t3"),
            FakeToolUse("broken", {}, "t4"),
        ]
        blocks = self.ex.gated_dispatch(registry, policy, calls)
        assert [b["tool_use_id"] for b in blocks] == ["t1", "t2", "t3", "t4"]
        assert "is_error" not in blocks[0]
        assert "declined" in blocks[1]["content"]
        assert "ghost" in blocks[2]["content"] and blocks[2]["is_error"]
        assert blocks[3]["content"] == "Error: disk full"

    def test_unknown_tools_are_never_sent_to_the_approver(self):
        registry, policy, events = self.build("ask", Decision.allow("ok"))
        self.ex.gated_dispatch(registry, policy, [FakeToolUse("ghost", {}, "t1")])
        assert events == []
