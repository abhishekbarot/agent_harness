"""Section 5 -- Building real tools safely. Run with: pytest course/section05_safe_tools"""

from __future__ import annotations

import pytest

from common.harness import ToolError
from loader import load


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "hello.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "nested.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("classified", encoding="utf-8")
    return root.resolve()


# -- 5.1 ---------------------------------------------------------------------


class TestEx1ResolveWithin:
    ex = load(__file__, "ex1_resolve_within")

    @pytest.mark.parametrize("path", ["hello.txt", "sub/nested.py", "sub/../hello.txt", "."])
    def test_paths_inside_are_allowed(self, workspace, path):
        resolved = self.ex.resolve_within(workspace, path)
        assert resolved == (workspace / path).resolve()

    @pytest.mark.parametrize(
        "path", ["../secret.txt", "../../etc/passwd", "sub/../../secret.txt", "/etc/passwd"]
    )
    def test_escapes_are_rejected(self, workspace, path):
        with pytest.raises(ToolError, match="escapes"):
            self.ex.resolve_within(workspace, path)

    def test_symlink_pointing_outside_is_rejected(self, workspace):
        (workspace / "innocent.txt").symlink_to(workspace.parent / "secret.txt")
        with pytest.raises(ToolError, match="escapes"):
            self.ex.resolve_within(workspace, "innocent.txt")

    def test_sibling_with_a_shared_prefix_is_rejected(self, workspace):
        """'/tmp/workspace-evil' starts with '/tmp/workspace' as a string -- but it's outside."""
        evil = workspace.parent / f"{workspace.name}-evil"
        evil.mkdir()
        with pytest.raises(ToolError, match="escapes"):
            self.ex.resolve_within(workspace, f"../{evil.name}/x.txt")

    @pytest.mark.parametrize("path", ["", "   ", None, 42])
    def test_non_strings_and_blanks_are_rejected(self, workspace, path):
        with pytest.raises(ToolError, match="non-empty"):
            self.ex.resolve_within(workspace, path)


# -- 5.2 ---------------------------------------------------------------------


class TestEx2ClampTimeout:
    ex = load(__file__, "ex2_clamp_timeout")

    def test_none_uses_the_default(self):
        assert self.ex.clamp_timeout(None) == 120
        assert self.ex.clamp_timeout(None, default=30) == 30

    def test_valid_values_pass_through(self):
        assert self.ex.clamp_timeout(45) == 45

    def test_huge_values_are_capped(self):
        assert self.ex.clamp_timeout(86_400) == 600
        assert self.ex.clamp_timeout(1_000, maximum=300) == 300

    @pytest.mark.parametrize("raw", [0, -5])
    def test_non_positive_is_rejected(self, raw):
        with pytest.raises(ToolError):
            self.ex.clamp_timeout(raw)

    @pytest.mark.parametrize("raw", ["60", 1.5, True, [60]])
    def test_wrong_types_are_rejected(self, raw):
        with pytest.raises(ToolError):
            self.ex.clamp_timeout(raw)


# -- 5.3 ---------------------------------------------------------------------


class TestEx3Truncate:
    ex = load(__file__, "ex3_truncate")

    def test_short_text_is_unchanged(self):
        assert self.ex.truncate("hello", 10) == "hello"
        assert self.ex.truncate("hello", 5) == "hello"

    def test_long_text_is_cut_with_a_marker(self):
        out = self.ex.truncate("abcdefghij", 4)
        assert out == "abcd\n...[truncated 6 characters]"


# -- 5.4 ---------------------------------------------------------------------


class TestEx4ReadFile:
    ex = load(__file__, "ex4_read_file")

    def test_reads_with_line_numbers(self, workspace):
        result = self.ex.read_file(workspace, "hello.txt")
        assert not result.is_error
        assert result.content.splitlines() == ["     1\talpha", "     2\tbeta", "     3\tgamma"]

    def test_escape_is_rejected(self, workspace):
        with pytest.raises(ToolError, match="escapes"):
            self.ex.read_file(workspace, "../secret.txt")

    def test_missing_file(self, workspace):
        with pytest.raises(ToolError, match="not found"):
            self.ex.read_file(workspace, "nope.txt")

    def test_directory(self, workspace):
        with pytest.raises(ToolError, match="directory"):
            self.ex.read_file(workspace, "sub")

    def test_too_big(self, workspace):
        (workspace / "big.log").write_text("x" * 2_000, encoding="utf-8")
        with pytest.raises(ToolError, match="limit"):
            self.ex.read_file(workspace, "big.log", max_bytes=1_000)

    def test_binary_file(self, workspace):
        (workspace / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe")
        with pytest.raises(ToolError, match="UTF-8"):
            self.ex.read_file(workspace, "image.png")

    def test_empty_file(self, workspace):
        (workspace / "empty.txt").write_text("", encoding="utf-8")
        assert self.ex.read_file(workspace, "empty.txt").content == "(empty file)"

    def test_long_output_is_truncated(self, workspace):
        (workspace / "long.txt").write_text("line\n" * 1_000, encoding="utf-8")
        content = self.ex.read_file(workspace, "long.txt", max_chars=100).content
        assert "[truncated" in content
        assert len(content) < 200
