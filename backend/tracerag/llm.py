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
