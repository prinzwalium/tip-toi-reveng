"""A very small translation layer.

Source strings are English and double as the lookup key, so a missing
translation degrades to readable English instead of to a key like
``book.editor.title``. The interface language defaults to German.
"""

import json
from pathlib import Path

from .config import config

LOCALES_DIR = Path(__file__).parent / "locales"


def load_catalog(lang: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{lang}.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    # Entries may be left empty while a translation is still being written.
    return {k: v for k, v in data.items() if isinstance(v, str) and v}


CATALOG = load_catalog(config.LANG)


def t(text: str, **kwargs) -> str:
    """Translate ``text``; ``{placeholders}`` are filled from ``kwargs``."""
    translated = CATALOG.get(text, text)
    return translated.format(**kwargs) if kwargs else translated


def catalog_for_js(keys: list[str]) -> dict[str, str]:
    """The subset the browser needs, as {source: translation}."""
    return {key: t(key) for key in keys}
