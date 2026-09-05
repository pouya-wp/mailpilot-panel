"""Every refusal this API makes has a Persian translation.

`messages.FA` is keyed on the English sentence written at the raise site,
which is the cheap way to do this — nothing at the 147 raise sites has to
change — and it has one failure mode: someone edits or adds a message and
the translation quietly stops matching, leaving a Persian reader with an
English sentence and nobody any the wiser.

So the keys are checked against the source rather than trusted. This
parses every `detail=` string literal out of the app package and requires
that each one is in the table, and that the table has no keys that no
longer exist.

If this test fails, it is not the test that is wrong: add the message to
`messages.FA`, or remove the stale key.
"""

from __future__ import annotations

import ast
import io
from pathlib import Path

from app import messages

APP = Path(__file__).resolve().parents[1] / "app"


def _messages_in_source() -> set[str]:
    """Every sentence that can end up in a response's `detail`.

    Two sources, because there are two ways one gets there:

      * `detail="..."` written at the raise site.
      * `GoogleError("...")` — the routes that talk to Gmail re-raise these
        as `detail=str(exc)`, so the text Google's wrapper was constructed
        with is shown to the reader verbatim.
    """
    found: set[str] = set()
    for path in APP.rglob("*.py"):
        tree = ast.parse(io.open(path, encoding="utf-8").read(), str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if (
                    kw.arg == "detail"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    found.add(kw.value.value)
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name == "GoogleError" and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    found.add(first.value)
    return found


def test_every_server_message_is_translated():
    missing = sorted(_messages_in_source() - set(messages.FA))
    assert not missing, (
        "these server messages would reach a Persian reader in English — "
        "add them to messages.FA:\n  " + "\n  ".join(missing)
    )


def test_no_stale_translations():
    """A key for a message that no longer exists is dead weight, and a hint
    that a message was reworded without its translation following."""
    # the validation handler's own message is not a `detail=` literal
    from_handler = {"The request body did not validate"}
    stale = sorted(set(messages.FA) - _messages_in_source() - from_handler)
    assert not stale, "translations for messages that no longer exist:\n  " + "\n  ".join(stale)


def test_english_is_untouched_by_default():
    assert messages.translate("Campaign not found", None) == "Campaign not found"
    assert messages.translate("Campaign not found", "en-GB,en;q=0.9") == "Campaign not found"


def test_persian_is_returned_for_a_persian_reader():
    assert messages.translate("Campaign not found", "fa") == "کمپین پیدا نشد"
    assert messages.translate("Campaign not found", "fa-IR") == "کمپین پیدا نشد"


def test_an_unknown_message_falls_back_to_english():
    """A gap must degrade, not blank out. This is the behaviour the panel
    had before translation existed, so a missing key costs nothing."""
    assert messages.translate("Something new", "fa") == "Something new"


def test_a_non_string_detail_is_left_alone():
    """FastAPI allows a dict or list detail; translating one would corrupt it."""
    payload = {"field": "email"}
    assert messages.translate(payload, "fa") is payload
