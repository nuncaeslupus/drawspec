"""The `rag` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _optional_number
from drawspec.schema._model import Document, RagRow, Violation

#: Why a RAG row has no place for a field an author may reach for.
RAG_REFUSED: Final = {
    "edges": "a RAG report rates each row on its own; there is nothing to connect",
    "columns": (
        "one rating per row. Cost, time and scope rated separately are a table, or one "
        "report per dimension"
    ),
    "status": (
        "a rating is `rag` (`red`, `amber`, `green`); `status` marks a change on `flow` and `tree`"
    ),
    "colour": (
        "the rating is `rag`, and the theme draws it as a word, a shape and a colour. Write "
        '`"rag": "green"`'
    ),
    "score": (
        "a risk score is a number on a likelihood-by-impact grid: a `matrix` with a `scale`. "
        "Here the row carries its `rag`"
    ),
    "likelihood": "a likelihood-by-impact grid is a `matrix` with a `scale`",
    "impact": "a likelihood-by-impact grid is a `matrix` with a `scale`",
    "owner": "an owner is a caption: a second line in `text`, after a newline",
    "comment": "the commentary is `note`",
    "commentary": "the commentary is `note`",
}


#: What an author may mean by a rating or a trend outside the vocabulary.
RAG_VALUE_ADVICE: Final = (
    "Three ratings, as boards settle on: choose the nearer of the two in a split rating "
    "(`amber/green`) and say why in the `note`; a finished workstream is `green` with "
    "*Complete* in its note."
)


RAG_TREND_ADVICE: Final = (
    "Say what the change means — `better`, `same` or `worse` — not which way an arrow "
    "points: an arrow up means *improving* in one report and *risk rising* in another."
)


def _rag_refusal(violation: Violation) -> Violation:
    """A structural refusal in a RAG report, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    unknown = "is not" in violation.message and "field" in violation.message
    if name in RAG_REFUSED and unknown:
        return Violation(violation.pointer, f"{name!r}: {RAG_REFUSED[name]}.")
    if "is not one of" in violation.message and name in ("rag", "trend"):
        advice = RAG_VALUE_ADVICE if name == "rag" else RAG_TREND_ADVICE
        return Violation(violation.pointer, violation.message.split(".")[0] + ". " + advice)
    return violation


def _rag_document(document: Mapping[str, Any]) -> Document:
    """A RAG report: its rows, in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        rag_rows=tuple(
            RagRow(
                text=str(row["text"]),
                rag=str(row["rag"]),
                trend=str(row.get("trend", "")),
                note=str(row.get("note", "")),
            )
            for row in document["rows"]
        ),
    )
