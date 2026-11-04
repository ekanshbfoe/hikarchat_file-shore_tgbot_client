"""The client is not technical. These words and patterns must never reach a user."""

import re

from bot import texts

BANNED_WORDS = (
    "api",
    "database",
    "db",
    "exception",
    "error",
    "traceback",
    "server",
    "webhook",
    "token",
    "null",
    "none",
    "json",
    "sql",
    "postgres",
    "stack",
    "timeout",
    "http",
    "ocr",
    "tesseract",
    "bug",
    "crash",
    "failed",
    "status code",
)


def all_texts() -> dict[str, str]:
    return {
        name: value
        for name, value in vars(texts).items()
        if name.isupper() and isinstance(value, str)
    }


def test_there_are_texts_to_check():
    assert len(all_texts()) > 100


def test_no_technical_words():
    offenders = []
    for name, value in all_texts().items():
        plain = re.sub(r"<[^>]+>|\{[^}]*\}", " ", value).lower().replace("https://", "")
        offenders += [
            (name, word) for word in BANNED_WORDS if re.search(rf"\b{re.escape(word)}\b", plain)
        ]
    assert offenders == []


def test_no_error_codes():
    for name, value in all_texts().items():
        assert not re.search(r"\b[45]\d\d\b", value), name


def test_html_tags_are_balanced():
    for name, value in all_texts().items():
        for tag in ("b", "i", "code"):
            assert value.count(f"<{tag}>") == value.count(f"</{tag}>"), name


def test_format_placeholders_are_simple():
    # Fields are filled with str.format, so only plain names are allowed, except for
    # the caption help which shows placeholders to the owner and is never formatted.
    documented = {"CAPTION_PROMPT"}
    for name, value in all_texts().items():
        if name in documented:
            continue
        for field in re.findall(r"\{([^}]*)\}", value):
            assert field.isidentifier(), (name, field)
