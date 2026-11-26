# ============================================================
# Model Configuration
# ============================================================

DEFAULT_MODEL = "gpt-5.6-luna"


def resolve_default_model():
    """Return the model a run should use when the caller names none.

    config.yaml wins over the code default so the account settings page
    and the pipeline cannot drift apart. An unknown value falls back to
    DEFAULT_MODEL rather than being sent to the provider, because a typo
    here would otherwise fail on the first chunk of a paid run.

    A missing or unreadable config also falls back rather than raising: this
    is called at the top of a run, and a broken config should not stop a
    translation that could still proceed on the compiled-in default.
    """
    try:
        from app.core.config import read_config_safe

        configured = (read_config_safe().get("translation") or {}).get("default_model")
    except (OSError, AttributeError, TypeError, ValueError):
        return DEFAULT_MODEL
    if isinstance(configured, str) and configured.strip() in SUPPORTED_MODELS:
        return configured.strip()
    return DEFAULT_MODEL


SUPPORTED_MODELS = {
    "gpt-5.6-terra": {
        "provider": "openai-compatible",
        "description": "High-quality translation model",
    },
    "gpt-5.6-luna": {
        "provider": "openai-compatible",
        "description": "Primary translation model",
    },
    "gemini-3.1-flash-lite": {
        "provider": "openai-compatible",
        "description": "Fast, lower-cost translation model",
    },
    "deepseek-v4.1-flash": {
        "provider": "openai-compatible",
        "description": "Fast, low-cost DeepSeek translation model",
    },
    # The provider has no separate "low" model id: every
    # ``deepseek-v4.1-flash-*`` suffix we tried (``-low``, ``-lite``,
    # ``-mini``, ``-low-1017``) answers 404 model_not_found. "low" here means
    # the low-reasoning variant of the same upstream model, selected through
    # the request parameter instead of a second model name.
    #
    # Measured on the calibration preview request (one 550-token chunk):
    #   reasoning on (plain deepseek-v4.1-flash)  40-90s, 1000-2600 out tokens
    #   reasoning_effort="low"                    19-26s,  645-865 out tokens
    #   reasoning_effort="none"                    9s,     224 out tokens
    # All three returned valid, complete slot JSON. The preview is the first
    # thing a user waits on, so this entry ships the fastest setting; switch
    # the value below to "low" for the middle tier.
    "deepseek-v4.1-flash-low": {
        "provider": "openai-compatible",
        "description": "DeepSeek V4.1 Flash, low reasoning (fast)",
        "upstream": "deepseek-v4.1-flash",
        "request": {"reasoning_effort": "none"},
    },
}


def upstream_model(model):
    """The provider's model id for a supported entry.

    A supported id may be a local variant (``deepseek-v4.1-flash-low``) that
    the provider does not know; the request must carry the real upstream id.
    """
    entry = SUPPORTED_MODELS.get(model) or {}
    return entry.get("upstream", model)


def model_request(model):
    """Keyword arguments for ``chat.completions.create`` for this model id.

    Returns ``{"model": <upstream id>}`` plus any per-model request extras, so
    call sites pass ``**model_request(name)`` instead of ``model=name`` and a
    variant cannot silently send an id the provider rejects.
    """
    entry = SUPPORTED_MODELS.get(model) or {}
    return {"model": entry.get("upstream", model), **entry.get("request", {})}


def is_supported_model(model):
    """
    Check whether the requested model is supported.

    Parameters:
        model: Model name.

    Returns:
        bool: True if the model is supported,
              otherwise False.
    """

    return model in SUPPORTED_MODELS


def get_model_config(model):
    """
    Return configuration for the requested model.

    Parameters:
        model: Model name.

    Returns:
        dict: Configuration of the requested model.

    Raises:
        ValueError: If the model is not supported.
    """

    if not is_supported_model(model):

        raise ValueError(
            f"Unsupported model: {model}"
        )

    return SUPPORTED_MODELS[model]


def get_default_model():
    """
    Return the default translation model.

    Returns:
        str: Default model name.
    """

    return DEFAULT_MODEL
