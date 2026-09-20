from __future__ import annotations

import dataclasses

import pytest

from agent_harness.config import Config
from agent_harness.errors import ConfigError


def test_defaults_use_opus_5():
    assert Config().model == "claude-opus-5"


def test_workspace_is_resolved(tmp_path):
    nested = tmp_path / "a" / ".." / "a"
    nested.mkdir(parents=True, exist_ok=True)
    assert Config(workspace=nested).workspace == (tmp_path / "a").resolve()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"effort": "turbo"},
        {"permission_mode": "maybe"},
        {"context_strategy": "shrink"},
        {"max_turns": 0},
        {"max_tokens": 0},
        {"log_format": "xml"},
        {"max_cost_usd": -1.0},
    ],
)
def test_invalid_values_are_rejected(kwargs):
    with pytest.raises(ConfigError):
        Config(**kwargs)


def test_env_is_read_and_overrides_win(monkeypatch):
    monkeypatch.setenv("AGENT_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("AGENT_MAX_TURNS", "9")
    monkeypatch.setenv("AGENT_EFFORT", "low")

    config = Config.from_env(effort="max")
    assert config.model == "claude-sonnet-5"
    assert config.max_turns == 9
    assert config.effort == "max"  # explicit override beats the environment


def test_env_type_errors_are_config_errors(monkeypatch):
    monkeypatch.setenv("AGENT_MAX_TURNS", "lots")
    with pytest.raises(ConfigError):
        Config.from_env()


def test_config_is_frozen():
    config = Config()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.model = "something-else"  # type: ignore[misc]
