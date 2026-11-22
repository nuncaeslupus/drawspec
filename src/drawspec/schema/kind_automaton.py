"""The `automaton` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from difflib import get_close_matches
from typing import Any, Final

from drawspec.schema._checks import _listed, _optional_number, _pointer
from drawspec.schema._constants import _AUTOMATON_EMPTY, AUTOMATON_NAME_MAX
from drawspec.schema._model import AutomatonState, AutomatonTransition, Document, Violation

#: Why an automaton has no place for a field an author may reach for.
AUTOMATON_REFUSED: Final = {
    "initial": "the start state is the top-level `start`, the id of one state",
    "final": "the accepting states are the top-level `accepting`, a list of state ids",
    "accept": "the accepting states are the top-level `accepting`, a list of state ids",
    "accepting": "the accepting states are the top-level `accepting`, a list of state ids",
    "start": "the start state is the top-level `start`, the id of one state",
    "symbol": "the symbol a move reads is `on`",
    "input": "the symbol a move reads is `on`",
    "event": (
        "a move reads a symbol, `on`; an event with a guard and an action is a UML state "
        "machine — the `states` kind"
    ),
    "label": (
        "the arrow's label is built from `on` (or `epsilon`) and `output`; two moves between "
        "the same states are merged into `a, b`"
    ),
    "symbols": (
        "one symbol per transition, as `on`: write a transition for each, and drawspec merges "
        "them into one arrow labelled `a, b`"
    ),
    "guard": "a finite automaton's move has no guard: it reads a symbol, `on`",
    "action": "a move's output is `output`, drawn after its symbol as `a / 1` (a Mealy machine)",
    "alphabet": (
        "the alphabet is read from the transitions, in the order the symbols first appear: "
        "every symbol is some move's `on`"
    ),
    "role": (
        "an automaton draws every state as a circle and every accepting one doubled: being "
        "the start or accepting is said by `start` and `accepting`"
    ),
    "nodes": "an automaton's circles are its `states`",
    "edges": "an automaton's arrows are its `transitions`",
    "groups": "an automaton has no composite states: a frame round states is the `states` kind",
}


def _automaton_refusal(violation: Violation) -> Violation:
    """A structural refusal in an automaton, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    unknown = "is not a known field" in violation.message or (
        "is not" in violation.message and "field" in violation.message
    )
    if unknown and name in AUTOMATON_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {AUTOMATON_REFUSED[name]}.")
    return violation


def _automaton_violations(document: Mapping[str, Any]) -> list[Violation]:
    """What an automaton may not be: ids that do not land, moves that read nothing.

    Exactly one start; every accepting id and every `from` and `to` a state; every
    move reads one symbol or is an empty move, never both; a move written once; a
    Mealy or a Moore machine, whole, never both; and a declared DFA with no ε-move and
    no two moves from one state on one symbol.
    """
    found: list[Violation] = []
    ids: dict[str, int] = {}
    outputs: list[int] = []
    for index, entry in enumerate(_listed(document, "states")):
        if not isinstance(entry, dict):
            continue
        identifier = entry.get("id")
        if isinstance(identifier, str):
            if not identifier.strip():
                found.append(
                    Violation(
                        _pointer("states", index, "id"),
                        "a state needs an id — `q0` — for `start`, `accepting` and the "
                        "transitions to name.",
                    )
                )
            elif identifier in ids:
                found.append(
                    Violation(
                        _pointer("states", index, "id"),
                        f"{identifier!r} is already the id of state {ids[identifier]}: every "
                        f"state needs its own, so a transition names one circle.",
                    )
                )
            else:
                ids[identifier] = index
        text = entry.get("text", identifier)
        output = entry.get("output")
        if isinstance(output, str):
            outputs.append(index)
            if not output.strip():
                found.append(
                    Violation(
                        _pointer("states", index, "output"),
                        "a Moore output needs a value — `0`, `open` — or leave `output` out.",
                    )
                )
        if isinstance(text, str):
            where = _pointer("states", index, "text" if "text" in entry else "id")
            name = f"{text} / {output}" if isinstance(output, str) else text
            if "text" in entry and not text.strip():
                found.append(Violation(where, "a state's name needs words, or leave `text` out."))
            elif "\n" in text:
                found.append(
                    Violation(
                        where,
                        "a state's name is one line in its circle. Say what holds in it in "
                        "the `caption`, or draw the machine as a `states` diagram, whose boxes "
                        "take a lead and a detail.",
                    )
                )
            elif len(name) > AUTOMATON_NAME_MAX:
                found.append(
                    Violation(
                        where,
                        f"{name!r} is {len(name)} characters, past the {AUTOMATON_NAME_MAX} a "
                        f"circle holds: every state is drawn the size of the widest. Shorten "
                        f"it to a handle (`q3`, `odd`) and say what it means in the caption, "
                        f"or draw a `states` diagram.",
                    )
                )

    states = list(_listed(document, "states"))
    if outputs and len(outputs) < len([entry for entry in states if isinstance(entry, dict)]):
        missing = next(
            index
            for index, entry in enumerate(states)
            if isinstance(entry, dict) and index not in outputs
        )
        found.append(
            Violation(
                _pointer("states", missing),
                "a Moore machine writes an output in every state: this one has none. Give it "
                "an `output`, or take `output` off every state.",
            )
        )

    def resolve(value: object, here: str, what: str) -> None:
        if isinstance(value, str) and value not in ids:
            close = get_close_matches(value, list(ids), n=1)
            hint = f" Did you mean {close[0]!r}?" if close else ""
            found.append(Violation(here, f"{value!r} {what} names no state.{hint}"))

    resolve(document.get("start"), "/start", "as the start state")
    seen_accepting: set[str] = set()
    for position, value in enumerate(_listed(document, "accepting")):
        here = _pointer("accepting", position)
        if isinstance(value, str) and value in seen_accepting:
            found.append(Violation(here, f"{value!r} is already accepting: list it once."))
        else:
            resolve(value, here, "as an accepting state")
        if isinstance(value, str):
            seen_accepting.add(value)

    deterministic = document.get("deterministic") is True
    written: dict[tuple[Any, ...], int] = {}
    reads: dict[tuple[str, str], int] = {}
    mealy: list[int] = []
    moves = list(_listed(document, "transitions"))
    for index, entry in enumerate(moves):
        if not isinstance(entry, dict):
            continue
        here = _pointer("transitions", index)
        resolve(entry.get("from"), f"{here}/from", "as `from`")
        resolve(entry.get("to"), f"{here}/to", "as `to`")
        symbol = entry.get("on")
        empty = entry.get("epsilon") is True
        if "output" in entry:
            mealy.append(index)
            output = entry.get("output")
            if isinstance(output, str) and not output.strip():
                found.append(
                    Violation(
                        f"{here}/output",
                        "a Mealy output needs a value — `0`, `beep` — or leave `output` out.",
                    )
                )
        if empty and "on" in entry:
            found.append(
                Violation(
                    f"{here}/epsilon",
                    "a move reads a symbol (`on`) or is an empty move (`epsilon: true`), not "
                    "both. Keep one.",
                )
            )
            continue
        if not empty and "on" not in entry:
            found.append(
                Violation(
                    here,
                    "a move reads a symbol: give it `on` — `0`, `a` — or make it an empty move "
                    "with `epsilon: true`.",
                )
            )
            continue
        if isinstance(symbol, str):
            if not symbol.strip():
                found.append(
                    Violation(
                        f"{here}/on",
                        "a symbol needs a character. An empty move is `epsilon: true`.",
                    )
                )
                continue
            if symbol.strip().casefold() in _AUTOMATON_EMPTY:
                found.append(
                    Violation(
                        f"{here}/on",
                        f"{symbol!r} reads as the empty move, which is not a symbol on the "
                        f"input: write `epsilon: true` in place of `on`, and drawspec labels "
                        f"it ε.",
                    )
                )
                continue
            if "\n" in symbol:
                found.append(Violation(f"{here}/on", "a symbol is one line: drop the newline."))
                continue
        source, target = entry.get("from"), entry.get("to")
        if not (isinstance(source, str) and isinstance(target, str)):
            continue
        read = "" if empty else symbol
        if not isinstance(read, str):
            continue
        key = (source, target, read, empty)
        if key in written:
            found.append(
                Violation(
                    f"{here}/{'epsilon' if empty else 'on'}",
                    f"this move is transition {written[key]} again ({source} to {target} "
                    f"{'by ε' if empty else f'on {read!r}'}): write it once.",
                )
            )
            continue
        written[key] = index
        if not deterministic:
            continue
        if empty:
            found.append(
                Violation(
                    f"{here}/epsilon",
                    "a deterministic automaton has no empty moves: each step reads a symbol. "
                    "Remove the ε-move, or drop `deterministic` — this is an NFA.",
                )
            )
            continue
        if (source, read) in reads:
            first = reads[(source, read)]
            found.append(
                Violation(
                    f"{here}/on",
                    f"{source!r} already moves on {read!r} (transition {first}): a "
                    f"deterministic automaton has one move per state and symbol. Remove one, "
                    f"or drop `deterministic` — this is an NFA.",
                )
            )
            continue
        reads[(source, read)] = index

    dicts = [index for index, entry in enumerate(moves) if isinstance(entry, dict)]
    if mealy and len(mealy) < len(dicts):
        missing = next(index for index in dicts if index not in mealy)
        found.append(
            Violation(
                _pointer("transitions", missing),
                "a Mealy machine writes an output on every move: this one has none. Give it an "
                "`output`, or take `output` off every transition.",
            )
        )
    if mealy and outputs:
        found.append(
            Violation(
                _pointer("states", outputs[0], "output"),
                "a machine writes its outputs on its moves (Mealy) or in its states (Moore), not "
                "both. Keep one.",
            )
        )
    return found


def _automaton_document(document: Mapping[str, Any]) -> Document:
    """A finite automaton: its states and moves in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        automaton_states=tuple(
            AutomatonState(
                id=str(entry["id"]),
                text=str(entry.get("text", entry["id"])),
                output=str(entry.get("output", "")),
            )
            for entry in document["states"]
        ),
        automaton_transitions=tuple(
            AutomatonTransition(
                source=str(entry["from"]),
                target=str(entry["to"]),
                symbol=str(entry.get("on", "")),
                epsilon=entry.get("epsilon") is True,
                output=str(entry.get("output", "")),
            )
            for entry in document.get("transitions", ())
        ),
        automaton_start=str(document["start"]),
        automaton_accepting=tuple(str(name) for name in document.get("accepting", ())),
        automaton_deterministic=document.get("deterministic") is True,
    )
