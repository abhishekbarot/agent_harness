"""Section 3 -- Tool use. Run with: pytest course/section03_tool_use"""

from __future__ import annotations

import pytest

from common.fakes import FakeToolUse
from common.harness import Tool, ToolResult
from loader import load


def echo_tool(name: str = "echo") -> Tool:
    return Tool(
        name=name,
        description="Echo the input back.",
        input_schema={"type": "object", "properties": {}, "required": []},
        fn=lambda **kw: ToolResult(str(kw)),
    )


# -- 3.1 ---------------------------------------------------------------------


class TestEx1ToolResult:
    ex = load(__file__, "ex1_tool_result")

    def test_success_block(self):
        block = self.ex.to_block(ToolResult("42 files"), "toolu_a")
        assert block == {"type": "tool_result", "tool_use_id": "toolu_a", "content": "42 files"}

    def test_error_block_sets_is_error(self):
        block = self.ex.to_block(ToolResult("not found", is_error=True), "toolu_b")
        assert block["is_error"] is True
        assert block["tool_use_id"] == "toolu_b"

    def test_success_omits_is_error_entirely(self):
        assert "is_error" not in self.ex.to_block(ToolResult("ok"), "toolu_c")


# -- 3.2 ---------------------------------------------------------------------

GOOD = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "limit": {"type": ["integer", "null"]},
    },
    "required": ["path", "limit"],
    "additionalProperties": False,
}


class TestEx2StrictSchema:
    ex = load(__file__, "ex2_strict_schema")

    def test_a_good_schema_passes(self):
        self.ex.validate_strict_schema("read_file", GOOD)

    @pytest.mark.parametrize(
        "change",
        [
            {"type": "array"},
            {"additionalProperties": True},
            {"required": ["path"]},
            {"required": ["path", "limit", "ghost"]},
        ],
        ids=["not-object", "extra-props-allowed", "optional-left-out", "unknown-required"],
    )
    def test_strict_mode_violations_are_rejected(self, change):
        with pytest.raises(ValueError, match="read_file"):
            self.ex.validate_strict_schema("read_file", {**GOOD, **change})

    def test_missing_additional_properties_is_rejected_by_the_validator(self):
        schema = {k: v for k, v in GOOD.items() if k != "additionalProperties"}
        with pytest.raises(ValueError):
            self.ex.validate_strict_schema("read_file", schema)

    def test_to_api_schema_shape(self):
        out = self.ex.to_api_schema("read_file", "Read a file.", GOOD)
        assert out["name"] == "read_file"
        assert out["description"] == "Read a file."
        assert out["strict"] is True
        assert out["input_schema"]["properties"] == GOOD["properties"]

    def test_to_api_schema_defaults_additional_properties_without_mutating(self):
        schema = {k: v for k, v in GOOD.items() if k != "additionalProperties"}
        out = self.ex.to_api_schema("read_file", "Read a file.", schema)
        assert out["input_schema"]["additionalProperties"] is False
        assert "additionalProperties" not in schema, "the caller's dict was modified"

    def test_to_api_schema_validates(self):
        with pytest.raises(ValueError):
            self.ex.to_api_schema("read_file", "Read a file.", {**GOOD, "required": ["path"]})


# -- 3.3 ---------------------------------------------------------------------


class TestEx3Registry:
    ex = load(__file__, "ex3_registry")

    def test_register_and_get(self):
        registry = self.ex.ToolRegistry([echo_tool("a")])
        assert registry.get("a").name == "a"
        assert "a" in registry and "b" not in registry
        assert len(registry) == 1

    def test_unknown_tool_is_none_not_an_exception(self):
        assert self.ex.ToolRegistry().get("nope") is None

    def test_duplicate_names_are_rejected(self):
        registry = self.ex.ToolRegistry([echo_tool("a")])
        with pytest.raises(ValueError, match="duplicate"):
            registry.register(echo_tool("a"))

    def test_order_is_registration_order(self):
        names = ["zeta", "alpha", "mid"]
        registry = self.ex.ToolRegistry([echo_tool(n) for n in names])
        assert registry.names() == names
        assert [s["name"] for s in registry.to_api_schemas()] == names

    def test_schemas_are_identical_every_call(self):
        """The tool list is part of the cached prefix; it must not drift."""
        registry = self.ex.ToolRegistry([echo_tool("a"), echo_tool("b")])
        assert registry.to_api_schemas() == registry.to_api_schemas()


# -- 3.4 ---------------------------------------------------------------------


class TestEx4BatchResults:
    ex = load(__file__, "ex4_batch_results")

    calls = [
        FakeToolUse("read_file", {}, "toolu_a"),
        FakeToolUse("list_dir", {}, "toolu_b"),
        FakeToolUse("search", {}, "toolu_c"),
    ]

    def test_one_user_message_in_call_order(self):
        # Results arrive out of order -- e.g. from a thread pool.
        results = {
            "toolu_c": ToolResult("c"),
            "toolu_a": ToolResult("a"),
            "toolu_b": ToolResult("b"),
        }
        message = self.ex.batch_results(self.calls, results)
        assert message["role"] == "user"
        assert [b["tool_use_id"] for b in message["content"]] == ["toolu_a", "toolu_b", "toolu_c"]
        assert [b["content"] for b in message["content"]] == ["a", "b", "c"]

    def test_every_call_gets_a_result_even_when_missing(self):
        message = self.ex.batch_results(self.calls, {"toolu_a": ToolResult("a")})
        blocks = message["content"]
        assert len(blocks) == 3
        assert blocks[1]["is_error"] is True and blocks[2]["is_error"] is True
        assert "no result" in blocks[1]["content"].lower()

    def test_errors_keep_their_flag(self):
        results = {c.id: ToolResult("boom", is_error=True) for c in self.calls}
        message = self.ex.batch_results(self.calls, results)
        assert all(b["is_error"] for b in message["content"])
