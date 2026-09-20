"""Token accounting and cost estimation.

Every API response carries a ``usage`` object. The harness accumulates it across
turns so a run can be priced, budgeted, and logged.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# USD per 1M tokens, from the Anthropic pricing table.
# Cache writes bill at ~1.25x the input rate; cache reads at ~0.1x.
_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-fable-5-1": (10.00, 50.00),
}

_CACHE_WRITE_MULTIPLIER = 1.25
_CACHE_READ_MULTIPLIER = 0.10


@dataclass
class Usage:
    """Accumulated token counts for a run."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    turns: int = 0
    per_turn: list[dict[str, int]] = field(default_factory=list)

    def add(self, raw: object) -> None:
        """Fold one response's ``usage`` into the running total.

        Accepts anything with the usual attributes, so a scripted fake in the
        tests works the same as a real SDK ``Usage``.
        """
        turn = {
            "input_tokens": _get(raw, "input_tokens"),
            "output_tokens": _get(raw, "output_tokens"),
            "cache_creation_input_tokens": _get(raw, "cache_creation_input_tokens"),
            "cache_read_input_tokens": _get(raw, "cache_read_input_tokens"),
        }
        self.input_tokens += turn["input_tokens"]
        self.output_tokens += turn["output_tokens"]
        self.cache_creation_input_tokens += turn["cache_creation_input_tokens"]
        self.cache_read_input_tokens += turn["cache_read_input_tokens"]
        self.turns += 1
        self.per_turn.append(turn)

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )

    def cost_usd(self, model: str) -> float | None:
        """Estimated cost in USD, or ``None`` for a model with no price on file."""
        price = _PRICES.get(model)
        if price is None:
            return None
        in_rate, out_rate = price
        return (
            self.input_tokens * in_rate
            + self.cache_creation_input_tokens * in_rate * _CACHE_WRITE_MULTIPLIER
            + self.cache_read_input_tokens * in_rate * _CACHE_READ_MULTIPLIER
            + self.output_tokens * out_rate
        ) / 1_000_000

    def cache_hit_rate(self) -> float:
        """Share of input tokens served from cache.

        A rate pinned at 0.0 across a multi-turn run means something in the
        prefix is changing every request -- see README "Prompt caching".
        """
        billed_input = (
            self.input_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens
        )
        if billed_input == 0:
            return 0.0
        return self.cache_read_input_tokens / billed_input

    def summary(self, model: str) -> dict[str, object]:
        cost = self.cost_usd(model)
        return {
            "turns": self.turns,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "total_tokens": self.total_tokens,
            "cache_hit_rate": round(self.cache_hit_rate(), 4),
            "cost_usd": None if cost is None else round(cost, 6),
        }


def _get(raw: object, name: str) -> int:
    value = getattr(raw, name, 0)
    return int(value) if isinstance(value, (int, float)) else 0
