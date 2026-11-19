"""Shared OpenRouter chat client."""

from __future__ import annotations

from . import config


def make_client():
    """Return an OpenAI client pointed at OpenRouter."""
    from openai import OpenAI

    return OpenAI(
        base_url=config.OPENROUTER_BASE_URL,
        api_key=config.OPENROUTER_API_KEY,
        default_headers={
            "HTTP-Referer": config.OPENROUTER_SITE_URL,
            "X-Title": config.OPENROUTER_APP_TITLE,
        },
    )


def make_intent_client() -> tuple[object, str]:
    """Return (client, model) for intent; prefers Groq, falls back to OpenRouter."""
    if config.GROQ_API_KEY:
        from openai import OpenAI

        client = OpenAI(
            base_url=config.GROQ_BASE_URL,
            api_key=config.GROQ_API_KEY,
        )
        return client, config.GROQ_MODEL
    return make_client(), config.OPENROUTER_MODEL
