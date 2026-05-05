"""Deterministic user-language detection used to lock the assistant's reply language.

`langdetect` is unreliable on short inputs (e.g. "hello" → Finnish, "Login details..."
→ French). To avoid spurious translations we:

1. Strip URLs/emails/digits/punctuation before detection.
2. Require at least `_MIN_LETTERS_FOR_DETECTION` letters or return `None`.
3. Expose `detect_with_history` so short messages inherit the language of the most
   recent reliable prior user turn instead of being guessed.
4. `language_matches` returns True for text that's too short to verify, so the
   translation-fallback path never fires on noise.
"""

from __future__ import annotations

import logging
import re
from typing import Iterable

from langdetect import DetectorFactory, LangDetectException, detect

logger = logging.getLogger(__name__)

DetectorFactory.seed = 0

_DEFAULT_LANGUAGE = "English"
_MIN_LETTERS_FOR_DETECTION = 20
_MIN_LETTERS_FOR_VERIFICATION = 30

LANGUAGE_NAMES: dict[str, str] = {
    "af": "Afrikaans", "ar": "Arabic", "bg": "Bulgarian", "bn": "Bengali",
    "ca": "Catalan", "cs": "Czech", "cy": "Welsh", "da": "Danish",
    "de": "German", "el": "Greek", "en": "English", "es": "Spanish",
    "et": "Estonian", "fa": "Persian", "fi": "Finnish", "fr": "French",
    "gu": "Gujarati", "he": "Hebrew", "hi": "Hindi", "hr": "Croatian",
    "hu": "Hungarian", "id": "Indonesian", "it": "Italian", "ja": "Japanese",
    "kn": "Kannada", "ko": "Korean", "lt": "Lithuanian", "lv": "Latvian",
    "mk": "Macedonian", "ml": "Malayalam", "mr": "Marathi", "ne": "Nepali",
    "nl": "Dutch", "no": "Norwegian", "pa": "Punjabi", "pl": "Polish",
    "pt": "Portuguese", "ro": "Romanian", "ru": "Russian", "sk": "Slovak",
    "sl": "Slovenian", "so": "Somali", "sq": "Albanian", "sv": "Swedish",
    "sw": "Swahili", "ta": "Tamil", "te": "Telugu", "th": "Thai",
    "tl": "Tagalog", "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu",
    "vi": "Vietnamese", "zh-cn": "Chinese", "zh-tw": "Chinese",
}

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
_LETTER_RE = re.compile(r"[A-Za-zÀ-ÿĀ-ſƀ-ɏ\u0370-\u03FF\u0400-\u04FF]")
_NON_LETTER_RE = re.compile(r"[^A-Za-zÀ-ÿĀ-ſƀ-ɏ\u0370-\u03FF\u0400-\u04FF\s]+")


def _normalize_for_detection(text: str) -> str:
    """Strip URLs, emails, digits and punctuation so the detector sees only natural words."""
    cleaned = _URL_RE.sub(" ", text)
    cleaned = _EMAIL_RE.sub(" ", cleaned)
    cleaned = _NON_LETTER_RE.sub(" ", cleaned)
    return " ".join(cleaned.split())


def _letter_count(text: str) -> int:
    return len(_LETTER_RE.findall(text))


def _detect_raw(text: str, *, min_letters: int) -> str | None:
    """Run `langdetect` only when there's enough letter content to be reliable."""
    cleaned = _normalize_for_detection(text)
    if _letter_count(cleaned) < min_letters:
        return None
    try:
        code = detect(cleaned).lower()
    except LangDetectException as exc:
        logger.debug("[LANG] detect failed for %r: %s", text[:60], exc)
        return None
    return LANGUAGE_NAMES.get(code)


def detect_user_language(text: str, *, fallback: str = _DEFAULT_LANGUAGE) -> str:
    """Detect language of `text`. Falls back to `fallback` when input is too short."""
    if not text or not text.strip():
        return fallback
    return _detect_raw(text, min_letters=_MIN_LETTERS_FOR_DETECTION) or fallback


def detect_with_history(
    current_message: str,
    history_user_messages: Iterable[str] | None = None,
    *,
    fallback: str = _DEFAULT_LANGUAGE,
) -> str:
    """Best-effort language for `current_message`, walking back through prior user turns
    when the latest message is too short to detect on its own (e.g. "ok", "thanks").

    `history_user_messages` should be the prior user turns in chronological order
    (oldest → newest). We scan newest-first and stop at the first reliable detection.
    """
    direct = _detect_raw(current_message, min_letters=_MIN_LETTERS_FOR_DETECTION)
    if direct is not None:
        return direct

    if history_user_messages:
        for prior in reversed(list(history_user_messages)):
            inherited = _detect_raw(prior, min_letters=_MIN_LETTERS_FOR_DETECTION)
            if inherited is not None:
                return inherited

    return fallback


def language_matches(text: str, expected_language: str) -> bool:
    """True if `text` is detected as `expected_language`.

    Returns True when `text` is too short to verify reliably — we never want the
    translation fallback to fire on a sub-sentence that langdetect can't handle.
    """
    if not text or not text.strip():
        return True
    detected = _detect_raw(text, min_letters=_MIN_LETTERS_FOR_VERIFICATION)
    if detected is None:
        return True
    return detected.lower() == expected_language.lower()
