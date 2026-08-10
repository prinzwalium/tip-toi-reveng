"""A very small translation layer.

Source strings are English and double as the lookup key, so a missing
translation degrades to readable English instead of to a key like
``book.editor.title``. The interface language defaults to German.

The language is per request: ``TTTOOL_WEB_LANG`` sets the default for everyone,
and a visitor can pick another one, which is remembered in a cookie. Outside a
request — during start up, or in a test — the configured default is used.
"""

import json
from pathlib import Path

from .config import config

LOCALES_DIR = Path(__file__).parent / "locales"

#: The source language: no catalogue, the strings in the code are already it.
SOURCE_LANG = "en"

#: Cookie holding the visitor's choice.
LANG_COOKIE = "tttool_lang"

#: What the language switch offers, in the order it shows them.
LANGUAGES: tuple[tuple[str, str], ...] = (("de", "Deutsch"), ("en", "English"))


#: Strings app.js needs in the browser; the English source is the key.
#: They live here rather than in app.py so that a test can read them
#: without importing — and thereby starting — the application.
UI_STRINGS = [
    "created",
    "changed",
    "deleted",
    "Files this run wrote that were not there before. Click one to download it.",
    "Files that already existed and this run overwrote. Click one to download it.",
    "Files that were removed while this command ran.",
    "… and {count} more",
    "in",
    "ok",
    "error",
    "timeout",
    "exit",
    "running …",
    "(no output — that means success)",
    "(no output)",
    "Request failed:",
]


def load_catalog(lang: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{lang}.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    # Entries may be left empty while a translation is still being written.
    return {k: v for k, v in data.items() if isinstance(v, str) and v}


#: Catalogues are small and never change while the process runs.
CATALOGS: dict[str, dict[str, str]] = {
    code: load_catalog(code) for code, _ in LANGUAGES if code != SOURCE_LANG
}


def known(lang: str) -> bool:
    return lang in {code for code, _ in LANGUAGES}


def default_lang() -> str:
    return config.LANG if known(config.LANG) else SOURCE_LANG


def current_lang() -> str:
    """The language of the request being served, or the configured default."""
    try:
        from flask import has_request_context, request
    except ImportError:  # pragma: no cover - flask is a hard dependency
        return default_lang()
    if not has_request_context():
        return default_lang()
    chosen = request.cookies.get(LANG_COOKIE, "")
    return chosen if known(chosen) else default_lang()


def t(text: str, **kwargs) -> str:
    """Translate ``text``; ``{placeholders}`` are filled from ``kwargs``."""
    translated = CATALOGS.get(current_lang(), {}).get(text, text)
    return translated.format(**kwargs) if kwargs else translated


def catalog_for_js(keys: list[str]) -> dict[str, str]:
    """The subset the browser needs, as {source: translation}."""
    return {key: t(key) for key in keys}
