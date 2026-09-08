"""JSON string catalogs — see docs/01-architecture.md#internationalization-i18n."""

import json
from collections.abc import Callable
from pathlib import Path

SUPPORTED_LOCALES = ("en", "fr")
DEFAULT_LOCALE = "en"

_LOCALES_DIR = Path(__file__).resolve().parent / "locales"


def _load_catalogs() -> dict[str, dict[str, str]]:
    catalogs: dict[str, dict[str, str]] = {}
    for locale in SUPPORTED_LOCALES:
        with (_LOCALES_DIR / f"{locale}.json").open(encoding="utf-8") as f:
            catalogs[locale] = json.load(f)
    return catalogs


_CATALOGS = _load_catalogs()


def get_translator(locale: str) -> Callable[..., str]:
    """Return a t(key, **kwargs) callable bound to `locale`, falling back to English."""

    def t(key: str, **kwargs: object) -> str:
        catalog = _CATALOGS.get(locale, _CATALOGS[DEFAULT_LOCALE])
        template = catalog.get(key) or _CATALOGS[DEFAULT_LOCALE].get(key, key)
        return template.format(**kwargs) if kwargs else template

    return t
