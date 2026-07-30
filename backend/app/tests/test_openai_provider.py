"""Tests for OpenAI request parameter compatibility."""

from app.ai.providers.openai_provider import _temperature_kwargs, _token_limit_kwargs


def test_gpt5_uses_max_completion_tokens() -> None:
    assert _token_limit_kwargs("gpt-5.6-sol", 8192) == {
        "max_completion_tokens": 8192
    }


def test_legacy_models_keep_max_tokens() -> None:
    assert _token_limit_kwargs("gpt-4o", 4096) == {"max_tokens": 4096}


def test_gpt5_omits_custom_temperature() -> None:
    assert _temperature_kwargs("gpt-5.6-sol", 0.1) == {}


def test_legacy_models_keep_custom_temperature() -> None:
    assert _temperature_kwargs("gpt-4o", 0.2) == {"temperature": 0.2}
