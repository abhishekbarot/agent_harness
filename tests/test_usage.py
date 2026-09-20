from __future__ import annotations

from agent_harness.usage import Usage
from conftest import FakeUsage


def test_costs_use_the_published_rates():
    usage = Usage()
    usage.add(FakeUsage(input_tokens=1_000_000, output_tokens=0))
    assert usage.cost_usd("claude-opus-5") == 5.00

    usage = Usage()
    usage.add(FakeUsage(input_tokens=0, output_tokens=1_000_000))
    assert usage.cost_usd("claude-opus-5") == 25.00


def test_cache_reads_are_a_tenth_of_input():
    usage = Usage()
    usage.add(FakeUsage(input_tokens=0, output_tokens=0, cache_read_input_tokens=1_000_000))
    assert usage.cost_usd("claude-opus-5") == 0.50


def test_cache_writes_carry_the_premium():
    usage = Usage()
    usage.add(FakeUsage(input_tokens=0, output_tokens=0, cache_creation_input_tokens=1_000_000))
    assert usage.cost_usd("claude-opus-5") == 6.25


def test_unknown_model_has_no_price():
    usage = Usage()
    usage.add(FakeUsage())
    assert usage.cost_usd("some-future-model") is None
    assert usage.summary("some-future-model")["cost_usd"] is None


def test_cache_hit_rate():
    usage = Usage()
    usage.add(FakeUsage(input_tokens=250, cache_read_input_tokens=750))
    assert usage.cache_hit_rate() == 0.75


def test_cache_hit_rate_is_zero_when_nothing_was_sent():
    assert Usage().cache_hit_rate() == 0.0


def test_missing_usage_object_is_tolerated():
    """A backend that returns no usage must not crash the run."""
    usage = Usage()
    usage.add(None)
    assert usage.turns == 1
    assert usage.total_tokens == 0


def test_totals_accumulate():
    usage = Usage()
    for _ in range(3):
        usage.add(FakeUsage(input_tokens=10, output_tokens=5))
    assert usage.turns == 3
    assert usage.total_tokens == 45
