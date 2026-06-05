"""Shared OpenRouter (OpenAI-compatible) chat client.

One factory used by curation (deep-merge), the router (intent fallback) and the
benchmark judge, so the provider/model/headers live in exactly one place.
"""

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
    """Return ``(client, model)`` for the latency-critical intent call.

    Prefers Groq (sub-second LPU inference) when ``GROQ_API_KEY`` is set;
    otherwise transparently reuses the OpenRouter client/model so nothing
    breaks when no Groq key is configured.
    """
    if config.GROQ_API_KEY:
        from openai import OpenAI

        client = OpenAI(
            base_url=config.GROQ_BASE_URL,
            api_key=config.GROQ_API_KEY,
        )
        return client, config.GROQ_MODEL
    return make_client(), config.OPENROUTER_MODEL
