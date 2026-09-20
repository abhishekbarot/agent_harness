from __future__ import annotations

import pytest

from agent_harness.errors import ToolError
from agent_harness.tools.base import Risk, ToolRegistry, ToolResult
from agent_harness.tools.builtin import (
    ListDirTool,
    ReadFileTool,
    RunCommandTool,
    SearchFilesTool,
    WriteFileTool,
    default_tools,
)


class TestPathConfinement:
    """Tool input is model output. Every path is checked before it is used."""

    @pytest.mark.parametrize(
        "escape",
        ["../outside.txt", "../../etc/passwd", "sub/../../outside.txt", "/etc/passwd"],
    )
    def test_reads_cannot_escape_the_workspace(self, workspace, escape):
        with pytest.raises(ToolError, match="escapes the workspace"):
            ReadFileTool(workspace).run(path=escape)

    def test_writes_cannot_escape_the_workspace(self, workspace):
        with pytest.raises(ToolError, match="escapes the workspace"):
            WriteFileTool(workspace).run(path="../evil.txt", content="x")
        assert not (workspace.parent / "evil.txt").exists()

    def test_symlink_out_of_the_workspace_is_rejected(self, workspace, tmp_path):
        secret = tmp_path.parent / "secret.txt"
        secret.write_text("classified", encoding="utf-8")
        (workspace / "link.txt").symlink_to(secret)

        # The path resolves outside the root, so the check catches it even
        # though the symlink itself lives inside.
        with pytest.raises(ToolError, match="escapes the workspace"):
            ReadFileTool(workspace).run(path="link.txt")

    def test_empty_path_is_rejected(self, workspace):
        with pytest.raises(ToolError, match="non-empty string"):
            ReadFileTool(workspace).run(path="   ")


class TestReadFile:
    def test_reads_with_line_numbers(self, workspace):
        result = ReadFileTool(workspace).run(path="hello.txt")
        assert not result.is_error
        assert "1\talpha" in result.content
        assert "3\tgamma" in result.content

    def test_missing_file_is_a_tool_error(self, workspace):
        with pytest.raises(ToolError, match="file not found"):
            ReadFileTool(workspace).run(path="nope.txt")

    def test_directory_is_rejected(self, workspace):
        with pytest.raises(ToolError, match="is a directory"):
            ReadFileTool(workspace).run(path="sub")

    def test_binary_file_is_rejected(self, workspace):
        (workspace / "blob.bin").write_bytes(b"\xff\xfe\x00\x01")
        with pytest.raises(ToolError, match="not valid UTF-8"):
            ReadFileTool(workspace).run(path="blob.bin")


class TestWriteFile:
    def test_creates_file_and_parents(self, workspace):
        result = WriteFileTool(workspace).run(path="deep/dir/new.txt", content="hi")
        assert not result.is_error
        assert (workspace / "deep" / "dir" / "new.txt").read_text() == "hi"
        assert result.metadata["created"] is True

    def test_overwrites_existing(self, workspace):
        result = WriteFileTool(workspace).run(path="hello.txt", content="replaced")
        assert "Overwrote" in result.content
        assert (workspace / "hello.txt").read_text() == "replaced"

    def test_non_string_content_is_rejected(self, workspace):
        with pytest.raises(ToolError, match="content must be a string"):
            WriteFileTool(workspace).run(path="x.txt", content=123)


class TestListAndSearch:
    def test_list_dir_marks_directories(self, workspace):
        content = ListDirTool(workspace).run(path=".").content
        assert "sub/" in content
        assert "hello.txt" in content

    def test_search_finds_matches(self, workspace):
        result = SearchFilesTool(workspace).run(pattern=r"def \w+", glob="**/*.py")
        assert "nested.py" in result.content
        assert result.metadata["count"] == 1

    def test_search_reports_no_matches(self, workspace):
        result = SearchFilesTool(workspace).run(pattern="zzzz")
        assert "No matches" in result.content

    def test_invalid_regex_is_a_tool_error(self, workspace):
        with pytest.raises(ToolError, match="invalid regular expression"):
            SearchFilesTool(workspace).run(pattern="(unclosed")


class TestRunCommand:
    def test_captures_stdout_and_exit_code(self, workspace):
        result = RunCommandTool(workspace).run(command="echo hello")
        assert not result.is_error
        assert "hello" in result.content
        assert result.metadata["exit_code"] == 0

    def test_non_zero_exit_is_an_error_result_not_an_exception(self, workspace):
        result = RunCommandTool(workspace).run(command="exit 3")
        assert result.is_error
        assert result.metadata["exit_code"] == 3

    def test_denylist_blocks_catastrophic_commands(self, workspace):
        tool = RunCommandTool(workspace, denied=("rm -rf /",))
        with pytest.raises(ToolError, match="blocked by policy"):
            tool.run(command="sudo RM -RF / --no-preserve-root")

    def test_timeout_is_reported(self, workspace):
        with pytest.raises(ToolError, match="timed out"):
            RunCommandTool(workspace).run(command="sleep 5", timeout=1)

    def test_runs_in_the_workspace(self, workspace):
        result = RunCommandTool(workspace).run(command="ls")
        assert "hello.txt" in result.content


class TestRegistryAndSchemas:
    def test_duplicate_names_are_rejected(self, workspace):
        registry = ToolRegistry([ReadFileTool(workspace)])
        with pytest.raises(ValueError, match="duplicate tool name"):
            registry.register(ReadFileTool(workspace))

    def test_schemas_are_strict(self, workspace):
        for schema in ToolRegistry(default_tools(workspace)).to_api_schemas():
            assert schema["strict"] is True
            assert schema["input_schema"]["additionalProperties"] is False
            assert schema["description"]

    def test_fingerprint_is_stable_and_order_sensitive(self, workspace):
        a = ToolRegistry(default_tools(workspace))
        b = ToolRegistry(default_tools(workspace))
        assert a.fingerprint() == b.fingerprint()

        reordered = ToolRegistry(list(reversed(default_tools(workspace))))
        assert reordered.fingerprint() != a.fingerprint()

    def test_risk_tiers_match_capability(self, workspace):
        risks = {t.name: t.risk for t in default_tools(workspace)}
        assert risks["read_file"] is Risk.READ_ONLY
        assert risks["search_files"] is Risk.READ_ONLY
        assert risks["write_file"] is Risk.WRITE
        assert risks["run_command"] is Risk.DANGEROUS

    def test_only_read_only_tools_are_parallel_safe(self, workspace):
        for tool in default_tools(workspace):
            assert tool.parallel_safe == (tool.risk is Risk.READ_ONLY)


def test_tool_result_block_shape():
    ok = ToolResult("fine").to_block("toolu_9")
    assert ok == {"type": "tool_result", "tool_use_id": "toolu_9", "content": "fine"}

    bad = ToolResult("broke", is_error=True).to_block("toolu_9")
    assert bad["is_error"] is True
