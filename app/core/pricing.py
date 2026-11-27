"""Model price table and cost arithmetic, shared by estimate and usage.

The table used to live in ``app/jobs/estimate.py``. The per-call usage recorder
sits in ``app/core`` and needs the same numbers, and ``app.core`` importing
``app.jobs`` would invert the dependency direction (jobs already imports core).
So the table moved here and ``estimate`` re-exports it unchanged.

Prices are USD per million tokens as ``(input, output)``. A model absent from
the table has no known price; callers must say so rather than invent a zero
that reads like "free".
"""
from __future__ import annotations

PRICING: dict[str, tuple[float, float]] = {
    # OpenAI GPT-4 family (prices per million tokens - actual as of Sep 2026)
    "gpt-4": (30.00, 60.00),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),

    # OpenAI GPT-3.5
    "gpt-3.5-turbo": (0.50, 1.50),
    "gpt-3.5-turbo-16k": (1.00, 2.00),

    # Anthropic Claude
    "claude-3-opus-20240229": (15.00, 75.00),
    "claude-3-sonnet-20240229": (3.00, 15.00),
    "claude-3-haiku-20240307": (0.25, 1.25),
    "claude-3-5-sonnet-20240620": (3.00, 15.00),

    # Google Gemini
    "gemini-1.5-pro": (1.25, 5.00),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-pro": (0.50, 1.50),

    # Project custom models (adjust based on your actual provider pricing)
    "gpt-5.6-luna": (0.15, 0.60),           # Equivalent to gpt-4o-mini
    "gpt-5.6-terra": (2.50, 10.00),         # Equivalent to gpt-4o
    "gemini-3.1-flash-lite": (0.075, 0.30), # Equivalent to gemini-1.5-flash
    # DeepSeek V4.1 Flash (deepseek-flash / DeepSeek-V4.1-Flash-1017). Official
    # list price, USD per million tokens: cache-miss input $0.15 off-peak /
    # $0.30 peak, output $0.60 off-peak / $1.20 peak. Priced at the peak rate
    # so the estimate is biased high; off-peak is half of this.
    "deepseek-v4.1-flash": (0.30, 1.20),
    # Same upstream model with reasoning disabled: identical price per token,
    # but far fewer output tokens, so the real bill is lower.
    "deepseek-v4.1-flash-low": (0.30, 1.20),
}


def rates_for(model: str | None) -> tuple[float, float] | None:
    """Return ``(input, output)`` USD-per-million-token rates, or ``None``."""
    return PRICING.get(str(model or ""))


def cost_usd(model: str | None, input_tokens: int, output_tokens: int) -> tuple[float, bool]:
    """Return ``(usd, price_known)`` for one call.

    ``price_known`` is ``False`` when the model is not in :data:`PRICING`; the
    returned amount is then ``0.0`` and the caller must not present it as a
    real cost.
    """
    rates = rates_for(model)
    if rates is None:
        return 0.0, False
    price_in, price_out = rates
    amount = (
        max(0, int(input_tokens or 0)) * price_in
        + max(0, int(output_tokens or 0)) * price_out
    ) / 1_000_000
    return round(amount, 6), True
