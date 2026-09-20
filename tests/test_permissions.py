from __future__ import annotations

import io

from agent_harness.permissions import (
    ConsoleApprover,
    Decision,
    PermissionPolicy,
    always_deny,
    auto_approve,
    build_policy,
)
from agent_harness.tools.builtin import ReadFileTool, RunCommandTool, WriteFileTool


def tools(workspace):
    return ReadFileTool(workspace), WriteFileTool(workspace), RunCommandTool(workspace)


class TestModes:
    def test_auto_allows_everything(self, workspace):
        policy = build_policy("auto")
        for tool in tools(workspace):
            assert policy.check(tool, {}).allowed

    def test_deny_blocks_everything_including_reads(self, workspace):
        policy = build_policy("deny")
        for tool in tools(workspace):
            assert not policy.check(tool, {}).allowed

    def test_readonly_allows_reads_and_blocks_mutations(self, workspace):
        read, write, command = tools(workspace)
        policy = build_policy("readonly")
        assert policy.check(read, {}).allowed
        assert not policy.check(write, {}).allowed
        assert not policy.check(command, {}).allowed

    def test_ask_escalates_only_non_read_only_tools(self, workspace):
        read, write, _ = tools(workspace)
        asked = []

        def approver(tool, tool_input):
            asked.append(tool.name)
            return Decision.allow()

        policy = PermissionPolicy("ask", approver)
        policy.check(read, {})
        policy.check(write, {"path": "x"})
        assert asked == ["write_file"]  # the read never reached the approver


class TestRemembering:
    def test_always_is_remembered_for_the_rest_of_the_run(self, workspace):
        _, write, _ = tools(workspace)
        calls = []

        def approver(tool, tool_input):
            calls.append(tool.name)
            return Decision.allow("always", remember=True)

        policy = PermissionPolicy("ask", approver)
        assert policy.check(write, {}).allowed
        assert policy.check(write, {}).allowed
        assert len(calls) == 1  # asked once, applied twice

    def test_never_is_remembered_too(self, workspace):
        _, write, _ = tools(workspace)
        policy = PermissionPolicy(
            "ask", lambda tool, ti: Decision.deny("never", remember=True)
        )
        assert not policy.check(write, {}).allowed
        assert not policy.check(write, {}).allowed


class TestConsoleApprover:
    def _approve(self, workspace, answer):
        stream = io.StringIO(answer)
        stream.isatty = lambda: True  # type: ignore[method-assign]
        _, write, _ = tools(workspace)
        return ConsoleApprover(stream)(write, {"path": "x.txt", "content": "y"})

    def test_yes(self, workspace):
        assert self._approve(workspace, "y\n").allowed

    def test_no(self, workspace):
        assert not self._approve(workspace, "n\n").allowed

    def test_always_sets_remember(self, workspace):
        decision = self._approve(workspace, "always\n")
        assert decision.allowed and decision.remember

    def test_never_sets_remember(self, workspace):
        decision = self._approve(workspace, "never\n")
        assert not decision.allowed and decision.remember

    def test_unrecognized_answer_denies(self, workspace):
        assert not self._approve(workspace, "hunter2\n").allowed

    def test_without_a_tty_it_denies_instead_of_blocking(self, workspace):
        _, write, _ = tools(workspace)
        # A pipe has no isatty; an unattended run must not hang on a prompt.
        decision = ConsoleApprover(io.StringIO("y\n"))(write, {})
        assert not decision.allowed
        assert "no interactive terminal" in decision.reason


def test_build_policy_picks_sane_default_approvers():
    assert build_policy("auto").approver is auto_approve
    assert build_policy("readonly").approver is always_deny
    assert isinstance(build_policy("ask").approver, ConsoleApprover)
