from __future__ import annotations

import re
import unicodedata


def normalize_key(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "nat"}:
        return None
    return text


def safe_slug(value: object, *, fallback: str = "unknown") -> str:
    key = normalize_key(value).replace(" ", "_")
    key = re.sub(r"_+", "_", key).strip("_")
    return key or fallback
