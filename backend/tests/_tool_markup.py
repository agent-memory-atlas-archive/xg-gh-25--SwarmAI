"""Test helper: build tool-call markup without writing it literally.

Test fixtures for the tool-call leak code are written with ``‹`` in place of
``<`` (``‹invoke name="Bash">``) and passed through ``tc()``. The model reads
these files while working on the leak code, and literal tool-call markup in
its context is a priming source for the very glitch under test (it writes its
own tool call as text). ``tc`` restores the real markup at runtime, so test
behaviour is unchanged.

Public symbols:
- ``tc(s)`` — return ``s`` with every ``‹`` replaced by ``<``.
"""


def tc(s: str) -> str:
    return s.replace("\u2039", "<")
