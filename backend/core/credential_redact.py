"""Shared credential scrubbing for ticket fields (Zendesk / Jira)."""

import re


def redact_ticket_field(text: str) -> str:
    """Scrub sensitive credentials from ticket summary/description before external APIs.

    Strips the value entirely so the ticket reads naturally
    (e.g. "changed their password" instead of exposing the literal value).
    """
    text = re.sub(
        r"(?i)(\b(?:password|passwort|passwd|token|api[\s_-]?key|secret|credential)\b)"
        r"(?:\s+(?:is|to|was|ist|lautet)|:)?\s+[\'\"]?(\S+?)[\'\"]?(?=[\s.,;)\n]|$)",
        r"\1",
        text,
    )
    text = re.sub(
        r"(?i)\b(?:sk|pk|bearer|xox[bpaso])-[A-Za-z0-9_\-\.]{6,}",
        "",
        text,
    )
    return text
