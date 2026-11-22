"""Validation and parsing entry points that dispatch to each kind's module."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import replace
from pathlib import Path
from typing import Any, Final

from drawspec.errors import DocumentError
from drawspec.filetree import problems
from drawspec.schema._build import _beside
from drawspec.schema._checks import (
    _axes,
    _causal_violations,
    _check_object,
    _class_violations,
    _classes,
    _did_you_mean,
    _entries,
    _escape,
    _hub,
    _hub_violations,
    _items,
    _listed,
    _loop_violations,
    _optional_number,
    _pointer,
    _scale_violations,
    _self_containment,
    _shaped_in_cycle,
    _status_violations,
)
from drawspec.schema._constants import (
    AGGREGATION_REFUSED,
    ARGUMENT_KINDS,
    AUTOMATON_KINDS,
    BARMODEL_KINDS,
    BOARD_KINDS,
    BRACKET_EDGE_ROLES,
    BRACKET_LEAVES_MAX,
    CLASSES_MAX,
    CLOCK_KINDS,
    CONTAINER_KINDS,
    DEPENDENCY_ROLES,
    DOCUMENT_VERSION,
    EMPHASIS_CAP,
    EMPHASIS_ROLE,
    ENTITIES_KINDS,
    FAMILYTREE_KINDS,
    FILES_KINDS,
    FISHBONE_KINDS,
    GANTT_KINDS,
    GITGRAPH_KINDS,
    GRAPH_EDGE_ROLES,
    GRAPH_KINDS,
    HIERARCHY_ROLES,
    JOURNEY_KINDS,
    KINDS,
    LANES_KINDS,
    LANES_PHASES_MAX,
    METER_KINDS,
    MINDMAP_KINDS,
    NETWORK_KINDS,
    NEURALNET_KINDS,
    NUMBERLINE_KINDS,
    PACKET_KINDS,
    PERT_KINDS,
    PIE_KINDS,
    RAG_KINDS,
    RAILROAD_KINDS,
    READABILITY_BUDGET,
    SANKEY_KINDS,
    SEQUENCE_KINDS,
    STATES_KINDS,
    SUNBURST_KINDS,
    TIMING_KINDS,
    TREEMAP_KINDS,
    USECASE_KINDS,
    VENN_KINDS,
    WARDLEY_KINDS,
    WATERFALL_KINDS,
)
from drawspec.schema._fields import _VERSION_REQUIRED, fields_for
from drawspec.schema._model import (
    Band,
    CausalLoop,
    Cell,
    Curve,
    Document,
    Edge,
    Group,
    Key,
    Node,
    Position,
    Series,
    Span,
    Violation,
    Waypoint,
)
from drawspec.schema.kind_argument import (
    _argument_document,
    _argument_refusal,
    _argument_violations,
)
from drawspec.schema.kind_automaton import (
    _automaton_document,
    _automaton_refusal,
    _automaton_violations,
)
from drawspec.schema.kind_barmodel import (
    _barmodel_document,
    _barmodel_refusal,
    _barmodel_violations,
)
from drawspec.schema.kind_board import _board_document, _board_refusal, _board_violations
from drawspec.schema.kind_chart import _chart_violations
from drawspec.schema.kind_clock import _clock_document, _clock_refusal, _clock_violations
from drawspec.schema.kind_entities import _entities_document, _entities_violations
from drawspec.schema.kind_familytree import (
    _familytree_document,
    _familytree_refusal,
    _familytree_violations,
)
from drawspec.schema.kind_fishbone import _fishbone_document, _fishbone_refusal
from drawspec.schema.kind_funnel import _funnel_amount_violations
from drawspec.schema.kind_gantt import _gantt_document, _gantt_refusal, _gantt_violations
from drawspec.schema.kind_gitgraph import (
    _gitgraph_document,
    _gitgraph_refusal,
    _gitgraph_violations,
)
from drawspec.schema.kind_journey import _journey_document, _journey_refusal, _journey_violations
from drawspec.schema.kind_lanes import _lanes_document, _lanes_refusal, _lanes_violations
from drawspec.schema.kind_meter import _meter_document, _meter_refusal, _meter_violations
from drawspec.schema.kind_mindmap import _mindmap_document, _mindmap_refusal, _mindmap_violations
from drawspec.schema.kind_network import _network_document, _network_refusal, _network_violations
from drawspec.schema.kind_neuralnet import (
    _neuralnet_document,
    _neuralnet_refusal,
    _neuralnet_violations,
)
from drawspec.schema.kind_numberline import (
    _numberline_document,
    _numberline_refusal,
    _numberline_violations,
)
from drawspec.schema.kind_packet import _packet_document, _packet_refusal, _packet_violations
from drawspec.schema.kind_pert import _pert_document, _pert_refusal, _pert_violations
from drawspec.schema.kind_pie import _pie_document, _pie_refusal, _pie_violations
from drawspec.schema.kind_quadrant import _quadrant_violations
from drawspec.schema.kind_rag import _rag_document, _rag_refusal
from drawspec.schema.kind_railroad import (
    _railroad_document,
    _railroad_refusal,
    _railroad_too_deep,
    _railroad_violations,
)
from drawspec.schema.kind_sankey import _sankey_document, _sankey_refusal, _sankey_violations
from drawspec.schema.kind_sequence import (
    _sequence_document,
    _sequence_refusal,
    _sequence_violations,
)
from drawspec.schema.kind_states import _states_document, _states_violations
from drawspec.schema.kind_sunburst import (
    _sunburst_document,
    _sunburst_refusal,
    _sunburst_too_deep,
    _sunburst_violations,
)
from drawspec.schema.kind_timing import _timing_document, _timing_refusal, _timing_violations
from drawspec.schema.kind_treemap import _treemap_document, _treemap_refusal, _treemap_violations
from drawspec.schema.kind_usecase import _usecase_document, _usecase_refusal, _usecase_violations
from drawspec.schema.kind_venn import _venn_document, _venn_refusal, _venn_violations
from drawspec.schema.kind_wardley import _wardley_document, _wardley_refusal, _wardley_violations
from drawspec.schema.kind_waterfall import (
    _waterfall_document,
    _waterfall_refusal,
    _waterfall_violations,
)


def validate_document(document: Mapping[str, Any]) -> tuple[Violation, ...]:
    """Every structural and referential violation in `document`, each located.

    Returns all of them rather than stopping at the first, so `drawspec validate`
    can print a document's whole story in one pass.
    """
    found: list[Violation] = []
    kind = document.get("kind")

    if not isinstance(kind, str) or kind not in KINDS:
        # Without a kind there is no way to know which payload fields are legal,
        # so reporting them would be a page of violations about the wrong thing.
        found.append(
            Violation(
                "/kind",
                "'kind' is required"
                if kind is None
                else f"{kind!r} is not one of {', '.join(KINDS)}. The vocabulary is "
                f"closed: a new kind needs evidence, in docs/kinds-wanted.md."
                f"{_did_you_mean(kind, KINDS) if isinstance(kind, str) else ''}",
            )
        )
        if "version" not in document:
            found.append(Violation("/version", _VERSION_REQUIRED))
        return tuple(found)

    if kind in SUNBURST_KINDS:
        # `sunburst-node` is self-referential, so cap the depth before the
        # recursive structural pass can overflow on pathologically deep input.
        too_deep = _sunburst_too_deep(document)
        if too_deep is not None:
            found.append(too_deep)
            return tuple(found)

    if kind in RAILROAD_KINDS:
        # `railroad-item` is self-referential too: cap the nesting before recursing.
        nested = _railroad_too_deep(document)
        if nested is not None:
            found.append(nested)
            return tuple(found)

    _check_object(document, fields_for(kind), "", found)

    version = document.get("version")
    if isinstance(version, int) and not isinstance(version, bool) and version != DOCUMENT_VERSION:
        found.append(
            Violation(
                "/version",
                f"version {version!r} is not supported; this drawspec reads version "
                f"{DOCUMENT_VERSION}. A change of meaning ships as v2, with both "
                f"readable in parallel for at least one release.",
            )
        )

    if kind in SEQUENCE_KINDS:
        found = [_sequence_refusal(violation, document) for violation in found]
    if kind in LANES_KINDS:
        found = [_lanes_refusal(violation) for violation in found]
    if kind in GANTT_KINDS:
        found = [_gantt_refusal(violation, document) for violation in found]
    if kind in BOARD_KINDS:
        found = [_board_refusal(violation) for violation in found]
    if kind in FISHBONE_KINDS:
        found = [_fishbone_refusal(violation) for violation in found]
    if kind in VENN_KINDS:
        found = [_venn_refusal(violation) for violation in found]
    if kind in JOURNEY_KINDS:
        found = [_journey_refusal(violation) for violation in found]
    if kind in TREEMAP_KINDS:
        found = [_treemap_refusal(violation) for violation in found]
    if kind in SANKEY_KINDS:
        found = [_sankey_refusal(violation) for violation in found]
    if kind in NUMBERLINE_KINDS:
        found = [_numberline_refusal(violation, document) for violation in found]
    if kind in BARMODEL_KINDS:
        found = [_barmodel_refusal(violation) for violation in found]
    if kind in WATERFALL_KINDS:
        found = [_waterfall_refusal(violation) for violation in found]
    if kind in PIE_KINDS:
        found = [_pie_refusal(violation) for violation in found]
    if kind in MINDMAP_KINDS:
        found = [_mindmap_refusal(violation) for violation in found]
    if kind in ARGUMENT_KINDS:
        found = [_argument_refusal(violation, document) for violation in found]
    if kind in FAMILYTREE_KINDS:
        found = [_familytree_refusal(violation) for violation in found]
    if kind in METER_KINDS:
        found = [_meter_refusal(violation) for violation in found]
    if kind in RAG_KINDS:
        found = [_rag_refusal(violation) for violation in found]
    if kind in CLOCK_KINDS:
        found = [_clock_refusal(violation) for violation in found]
    if kind in SUNBURST_KINDS:
        found = [_sunburst_refusal(violation) for violation in found]
    if kind in PERT_KINDS:
        found = [_pert_refusal(violation) for violation in found]
    if kind in AUTOMATON_KINDS:
        found = [_automaton_refusal(violation) for violation in found]
    if kind in NEURALNET_KINDS:
        found = [_neuralnet_refusal(violation) for violation in found]
    if kind in PACKET_KINDS:
        found = [_packet_refusal(violation) for violation in found]
    if kind in WARDLEY_KINDS:
        found = [_wardley_refusal(violation) for violation in found]
    if kind == "tree":
        found = [_tree_refusal(violation, document) for violation in found]
    if kind in USECASE_KINDS:
        found = [_usecase_refusal(violation) for violation in found]
    if kind in RAILROAD_KINDS:
        found = [_railroad_refusal(violation) for violation in found]
    if kind in NETWORK_KINDS:
        found = [_network_refusal(violation) for violation in found]
    if kind in TIMING_KINDS:
        found = [_timing_refusal(violation) for violation in found]
    if kind in GITGRAPH_KINDS:
        found = [_gitgraph_refusal(violation) for violation in found]
    found = [_edge_role_refusal(violation, document, kind) for violation in found]
    # The passes below read the raw document and assume its shape. When the
    # structural pass has already refused part of it, a wrong shape is the likely
    # cause of a crash in them, and the author should hear the violation already
    # found, not a traceback: so they are best effort then. On a document with no
    # structural violation they run unguarded, and a crash there is a real bug.
    passes: list[Callable[[], list[Violation]]] = [
        lambda: _referential_violations(document, kind),
        lambda: _bracket_violations(document) if kind == "tree" else [],
        lambda: list(_readability_violations(document, kind)),
        lambda: list(_emphasis_violations(document)),
    ]
    malformed = bool(found)
    for run in passes:
        if not malformed:
            found.extend(run())
            continue
        with suppress(KeyError, TypeError, AttributeError, IndexError, ValueError, OverflowError):
            found.extend(run())
    return tuple(found)


def _tree_refusal(violation: Violation, document: Mapping[str, Any]) -> Violation:
    """A bracket's `root` at the top or bottom, told why a bracket only reads across."""
    root = document.get("root")
    if violation.pointer == "/root" and root in ("top", "bottom", "up", "down"):
        return Violation(
            "/root",
            f"{root!r}: a bracket reads across, each leaf's name on a row of its own, so its "
            "root stands at the `left`, the `right` or in the `middle`. A tree read down the "
            'page is the boxed one: drop `"style": "bracket"`.',
        )
    return violation


#: Why a bracket refuses what a boxed tree takes, by the field's name.
BRACKET_REFUSED: Final[Mapping[str, str]] = {
    "groups": (
        "a bracket has no boxes to frame: its nodes are lines. Name a part of the draw in an "
        "inner node's words (a region, a clade), or draw it as boxes without the bracket style."
    ),
    "bands": (
        "a bracket has no boxes for a band to run beside. Say what runs alongside in the "
        "`caption`, or draw it as boxes without the bracket style."
    ),
    "classes": (
        "a bracket has no boxes to fill, so a class would have nothing to mark. Name the "
        "grouping in an inner node's words, or draw it as boxes without the bracket style."
    ),
    "class": "a bracket's node is a line, with no box for a class's fill. Drop it.",
    "status": (
        "a bracket's node is a line, with no box for a change's mark. Draw the change as two "
        "brackets, or as boxes without the bracket style."
    ),
    "actor": (
        "a bracket's node is one line of words, with no box for an actor's lead. Write who "
        "into the node's `text`."
    ),
    "role": (
        "a bracket's node is a line of words, with no box for a role to shape. To mark the "
        'path the reader should follow, give its edges `"role": "strong"`.'
    ),
}


def _bracket_violations(document: Mapping[str, Any]) -> list[Violation]:
    """A tree drawn as a bracket: one root, one parent each, no node of one child.

    The boxed tree draws any graph its edges make, cross-links included. A bracket
    places every node from its leaves, so the edges must be a tree, rooted once,
    and each inner node a match or a split of at least two.
    """
    if document.get("style", "boxes") != "bracket":
        if "root" in document:
            return [
                Violation(
                    "/root",
                    "`root` says which edge a bracket's root stands at, and this tree is drawn "
                    'as boxes ranked down from its root. Say `"style": "bracket"`, or drop it.',
                )
            ]
        return []
    found: list[Violation] = []
    for name in ("groups", "bands", "classes"):
        if name in document:
            found.append(Violation(f"/{name}", BRACKET_REFUSED[name]))
    ids: dict[str, int] = {}
    texts: dict[str, str] = {}
    for index, node in enumerate(_listed(document, "nodes")):
        if not isinstance(node, dict):
            continue
        for name in ("class", "status", "actor"):
            if name in node:
                found.append(Violation(_pointer("nodes", index, name), BRACKET_REFUSED[name]))
        if node.get("role", "step") != "step":
            found.append(Violation(_pointer("nodes", index, "role"), BRACKET_REFUSED["role"]))
        text = node.get("text")
        if isinstance(text, str) and "\n" in text.strip():
            found.append(
                Violation(
                    _pointer("nodes", index, "text"),
                    "a bracket's node is one line of words on its line: a team, a taxon, a "
                    "winner. Join the text into one line, or put the detail in the caption.",
                )
            )
        identifier = node.get("id")
        if isinstance(identifier, str) and identifier not in ids:
            ids[identifier] = index
            texts[identifier] = text if isinstance(text, str) else ""
    parent: dict[str, str] = {}
    children: dict[str, list[str]] = {identifier: [] for identifier in ids}
    for index, edge in enumerate(_listed(document, "edges")):
        if not isinstance(edge, dict):
            continue
        if "status" in edge:
            found.append(Violation(_pointer("edges", index, "status"), BRACKET_REFUSED["status"]))
        role = edge.get("role", "flow")
        if isinstance(role, str) and role not in BRACKET_EDGE_ROLES:
            found.append(
                Violation(
                    _pointer("edges", index, "role"),
                    f"{role!r}: a bracket's lines are all one line, square elbows to the next "
                    'round, so an edge is `"flow"` (the default) or `"strong"`, the heavy '
                    "path the reader follows.",
                )
            )
        label = edge.get("label")
        if isinstance(label, str) and "\n" in label.strip():
            found.append(
                Violation(
                    _pointer("edges", index, "label"),
                    "an edge's label is written on one line beside the elbow: a score, a "
                    "trait. Join it into one line.",
                )
            )
        source, target = edge.get("from"), edge.get("to")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if source not in ids or target not in ids:
            continue  # reported by the graph checks
        if source == target:
            found.append(
                Violation(
                    _pointer("edges", index, "to"),
                    f"{target!r} joins itself, and a bracket only joins a node to the match "
                    "or the split it feeds. Drop the edge.",
                )
            )
        elif target in parent:
            found.append(
                Violation(
                    _pointer("edges", index, "to"),
                    f"{target!r} already hangs from {parent[target]!r}, and in a bracket each "
                    "node feeds one match or one split. A team in two matches is two "
                    "entries, and a hybrid of two lineages is a network, not a tree: draw "
                    "that as boxes without the bracket style.",
                )
            )
        else:
            parent[target] = source
            children[source].append(target)
    if not ids:
        return found
    roots = [identifier for identifier in ids if identifier not in parent]
    if not roots:
        found.append(
            Violation(
                "/edges",
                "every node hangs from another, so the edges make a cycle and the bracket has "
                "no root: no final, no common ancestor. Drop the edge into the root.",
            )
        )
        return found
    if len(roots) > 1:
        found.append(
            Violation(
                _pointer("nodes", ids[roots[1]]),
                f"{roots[1]!r} hangs from nothing, and neither does {roots[0]!r}: a bracket "
                "has one root, the final or the common ancestor, and every other node feeds "
                "into it. Add the edge that joins them, or draw two brackets.",
            )
        )
        return found
    reached: set[str] = set()
    stack = [roots[0]]
    while stack:
        identifier = stack.pop()
        if identifier not in reached:
            reached.add(identifier)
            stack.extend(children[identifier])
    for identifier, index in ids.items():
        if identifier not in reached:
            found.append(
                Violation(
                    _pointer("nodes", index),
                    f"{identifier!r} is on a cycle of edges that never reaches the root "
                    f"{roots[0]!r}. Drop the edge that closes the cycle.",
                )
            )
            return found
    for identifier, kids in children.items():
        if len(kids) == 1:
            found.append(
                Violation(
                    _pointer("nodes", ids[identifier]),
                    f"{identifier!r} has one child, {kids[0]!r}: a match has two sides and a "
                    "split at least two branches, so a node of one is the same line twice. "
                    "Drop it and join its child to its parent, or give it its other side.",
                )
            )
    leaves = [identifier for identifier, kids in children.items() if not kids]
    for identifier in leaves:
        if not texts[identifier].strip():
            found.append(
                Violation(
                    _pointer("nodes", ids[identifier], "text"),
                    f"{identifier!r} is a leaf, and the leaves are what a bracket is of: the "
                    "teams, the taxa. Only an inner node may go unnamed.",
                )
            )
    if len(leaves) > BRACKET_LEAVES_MAX:
        found.append(
            Violation(
                _pointer("nodes", ids[leaves[BRACKET_LEAVES_MAX]]),
                f"{len(leaves)} leaves are past what one bracket can be read at — "
                f"{BRACKET_LEAVES_MAX} at most. Split it as a 64-team draw is printed: one "
                "bracket per region of sixteen, and one more for the regions' winners. The "
                "budget is not a canvas size, so a larger top-level 'width' does not lift it.",
            )
        )
    if document.get("root") == "middle" and len(children[roots[0]]) != 2:
        found.append(
            Violation(
                "/root",
                f"a two-sided bracket puts the root's first child's half on the left and its "
                f"second's on the right, and {roots[0]!r} has {len(children[roots[0]])} "
                'children. Give it two, or say `"root": "left"` or `"right"`.',
            )
        )
    return found


def _edge_role_refusal(violation: Violation, document: Mapping[str, Any], kind: str) -> Violation:
    """An edge role outside the kind's vocabulary, told which kind it belongs to.

    The generic refusal lists the legal roles, which says nothing to an author who
    wrote `inherits` in a `flow`, or `aggregates` in an entity diagram, on purpose.
    """
    parts = violation.pointer.split("/")
    if len(parts) != 4 or parts[1] != "edges" or parts[3] != "role":
        return violation
    edges = document.get("edges")
    try:
        role = edges[int(parts[2])]["role"]  # type: ignore[index]
    except (TypeError, ValueError, IndexError, KeyError):
        return violation
    if not isinstance(role, str):
        return violation
    if role in HIERARCHY_ROLES and kind not in ENTITIES_KINDS:
        legal = DEPENDENCY_ROLES if kind in GANTT_KINDS else GRAPH_EDGE_ROLES
        return Violation(
            violation.pointer,
            f"{role!r} is an edge role of the `entities` kind only: it says one class is a "
            f"kind of another, which a {kind} has no classes to mean. Here, one of "
            f"{', '.join(legal)}.",
        )
    if kind in ENTITIES_KINDS and role.startswith("aggregat"):
        return Violation(violation.pointer, f"{role!r}: {AGGREGATION_REFUSED}")
    return violation


_CLASSES_ADVICE: Final = (
    f"Past {CLASSES_MAX} classes the fills stop being told apart and the key is a table. "
    "Merge the classes a reader need not tell apart, or draw one diagram per class that "
    "matters."
)


#: What to do instead, for a budget whose generic advice ("split it into an
#: overview and details") is not the remedy. Keyed by (kind, array) for a
#: top-level budget and by (outer, inner) for a nested one.
BUDGET_ADVICE: Final[Mapping[tuple[str, str], str]] = {
    ("flow", "classes"): _CLASSES_ADVICE,
    ("tree", "classes"): _CLASSES_ADVICE,
    ("lanes", "classes"): _CLASSES_ADVICE,
    ("lanes", "phases"): (
        f"Past {LANES_PHASES_MAX} phases the header band is a table of contents. Merge "
        "neighbouring phases, or split the process at a phase boundary into two diagrams."
    ),
    ("fishbone", "categories"): (
        "Past six bones a fishbone stops being scannable: merge the categories that overlap, "
        "or draw the biggest category as a fishbone of its own."
    ),
    ("barmodel", "bars"): (
        "Past three bars a bar model is a table of quantities. Draw the step the problem "
        "turns on, or one model per step of a multi-step problem."
    ),
    ("argument", "points"): (
        "Past fifteen points an argument map is searched, not read. Split it: an overview "
        "with the claim and the top-level reasons and objections, and a map per contested "
        "reason, with that reason as its claim."
    ),
    ("familytree", "people"): (
        "Past thirty people a family tree is searched, not read. Split it by branch: one "
        "tree per side of the family, each naming where it joins the other in a `caption`."
    ),
    ("mindmap", "branches"): (
        "Past eight main branches they stop reading as peers round one centre. Group the "
        "ones that belong together under a new main branch, or split the topic into two maps."
    ),
    ("mindmap", "branches*"): (
        "Split it: an overview map naming the main branches, and a map per main branch "
        "carrying its detail, with that branch as its centre."
    ),
    ("meter", "meters"): (
        "Past six meters a panel is a dashboard, read as a table. Keep the ones the page is "
        "about, and put the rest in a table beside it."
    ),
    ("clock", "clocks"): (
        "Past twelve faces a sheet is two sheets: split it by the skill each practises — "
        "o'clock and half past on one, quarters on the next."
    ),
    ("timing", "signals"): (
        "Past twelve lanes a timing figure is searched, not read: split it by bus or by "
        "phase, one figure each, on the same steps."
    ),
    ("signals", "states"): (
        "Past six states the levels of one lane crowd: merge the states the reader need not "
        "tell apart, or draw the machine as a `states` diagram."
    ),
    ("rag", "rows"): (
        "Past fifteen rows a status report is searched, not read: split it by programme or "
        "directorate, one report each, or put the green rows in a table beside it."
    ),
    ("pert", "activities"): (
        "Past twenty activities a network is searched, not followed. Draw an overview network "
        "with one activity per phase, and a network per phase carrying its detail."
    ),
    ("automaton", "states"): (
        "Past twelve states a reader traces a word through a maze, not a machine. Minimise "
        "it, or draw the parts as separate automata and say in the caption how they join."
    ),
    ("automaton", "transitions"): (
        "Past thirty-six moves the arcs are a weave. Merge symbols that do the same thing "
        "into a class (`digit` for 0-9), or leave the dead state and its moves out."
    ),
    ("neuralnet", "layers"): (
        "Past sixteen layers a network is searched, not read. Draw its stages as one box "
        "each — `Stage 2: 4 residual blocks` — and a figure per stage carrying its layers."
    ),
    ("neuralnet", "skips"): (
        "Past six skip connections the bows are a weave. Draw one block with its skip and "
        "repeat it with `repeats`, as ResNet's figures do."
    ),
    ("neuralnet", "repeats"): (
        "Past three repeated blocks the frames crowd the layers. Draw each stage as one box, "
        "and a figure of the block it repeats."
    ),
    ("meters", "bands"): (
        "Past five bands neighbouring tones blur: merge the bands the reader need not tell "
        "apart. Few's bullet graph uses two to five."
    ),
    ("pie", "parts"): (
        "Past eight sectors the smallest are slivers no one compares: keep the largest seven "
        'and merge the rest into one `"role": "note"` part — `Everything else` — or draw a '
        "bar `chart`."
    ),
    ("waterfall", "bars"): (
        "Past twelve bars the names under them are too narrow to read. Split the bridge at "
        "a subtotal into two waterfalls, or merge the smallest steps into one `Other` step."
    ),
    ("bars", "parts"): (
        "Past eight parts the boxes are too thin to write in: merge the parts the question "
        "does not ask about into one, or draw the bar in `units`."
    ),
    ("flow", "loops"): (
        "Past six loops the markers crowd the map and none reads as a story. Split it: one "
        "diagram per subsystem, as research maps do, each naming its own loops."
    ),
    ("venn", "sets"): (
        "No drawing of five sets shows every region legibly, so a fifth set cannot be drawn "
        "honestly. Use a `matrix`: the sets as columns, the items as rows, a mark where an "
        "item belongs."
    ),
    ("journey", "stages"): (
        "Past seven stages the columns are too narrow to read. Split it into two journeys, "
        "before and after a hand-off, each with its own feeling line."
    ),
    ("journey", "feelings"): (
        "Past five levels two neighbours cannot be told apart on the page. Merge the levels "
        "nobody could tell apart in a sentence either."
    ),
    ("journey", "rows"): (
        "Past four rows the map is a table with a line on it. Keep the rows the line is "
        "explained by, or split it into two journeys, before and after a hand-off."
    ),
    ("treemap", "parts"): (
        "Past ten parts the smallest are slivers no label fits, and the drawing is a "
        "disk-usage tool's output. Merge the smallest into one `note` part — `Everything "
        "else` — and say what it holds in the caption."
    ),
    ("usecase", "actors"): (
        "Past eight actors the lines from the two sides are a net. Draw one use case "
        "diagram per kind of user — the customer's, the staff's — each with the use "
        "cases that user takes part in."
    ),
    ("usecase", "usecases"): (
        "Past fifteen use cases the boundary is a list. Draw an overview with one use case "
        "per goal, then a diagram per goal with the steps it includes and extends."
    ),
    ("usecase", "edges"): (
        "Past thirty relations the lines are a net. Split the diagram by actor or by "
        "subsystem, so each holds the relations one reader follows."
    ),
    ("sankey", "nodes"): (
        "Past fourteen nodes the bands are a tangle. Merge the small ends into one `note` "
        "node, or draw one sankey per stage — the middle column's nodes become the next "
        "one's sources."
    ),
    ("sankey", "flows"): (
        "Past twenty-four flows the bands are a tangle. Merge the small flows into one named "
        "`other` flow, or draw one sankey per stage."
    ),
    ("treemap", "groups"): (
        "Past four groups the frames crowd out the parts they hold. Draw one treemap of the "
        "groups' totals, then one per group that matters."
    ),
    ("groups", "regions"): (
        "Past four regions each is too small to hold a machine. Draw the composite as one "
        "state here and give each region a state machine of its own."
    ),
    ("categories", "causes"): (
        "Past five causes a bone is a list: keep the ones the investigation turned on, or "
        "make this category its own fishbone with these causes as its categories."
    ),
}


def _readability_violations(document: Mapping[str, Any], kind: str) -> list[Violation]:
    """Every counted array that holds more than its kind's readability budget.

    A refusal of a document that would draw: it says the picture would not be
    read, which is a different claim from `FitError`'s and comes before it.
    """
    found: list[Violation] = []
    for name, limit in READABILITY_BUDGET.get(kind, ()):
        if kind == "tree" and name == "nodes" and document.get("style") == "bracket":
            continue  # a bracket counts its leaves instead: see `BRACKET_LEAVES_MAX`
        if "/" in name:
            found.extend(_nested_budget(document, name, limit))
            continue
        if "@" in name:
            found.extend(_cell_budget(document, name, limit))
            continue
        if name.endswith("*"):
            found.extend(_deep_budget(document, kind, name[:-1], limit))
            continue
        if "=" in name:
            found.extend(_role_budget(document, kind, name, limit))
            continue
        entries = document.get(name)
        if not isinstance(entries, list) or len(entries) <= limit:
            continue
        found.append(
            Violation(
                _pointer(name, limit),
                f"{len(entries)} {name} is past what one {kind} can be read at — "
                f"{limit} at most. "
                + BUDGET_ADVICE.get(
                    (kind, name),
                    "Past that a reader searches the diagram instead of "
                    "taking it in. Split it: an overview that names each part once, plus a "
                    "detail diagram per part, each within the budget.",
                )
                + " The budget is not a canvas size, so a larger top-level 'width' does not "
                "lift it.",
            )
        )
    return found


def _role_budget(document: Mapping[str, Any], kind: str, name: str, limit: int) -> list[Violation]:
    """The budget of the entries of an array that take some roles: a machine's bars."""
    outer, roles = name.split("=")
    taking = roles.split("|")
    counted = [
        index
        for index, entry in enumerate(_listed(document, outer))
        if isinstance(entry, dict) and entry.get("role") in taking
    ]
    if len(counted) <= limit:
        return []
    named = " and ".join(taking)
    return [
        Violation(
            _pointer(outer, counted[limit], "role"),
            f"{len(counted)} {named} bars are past what one {kind} can be read at — "
            f"{limit} at most. Past that the machine is a workflow: draw it as a `flow` "
            f"or `lanes`, or split it into a machine per stage.",
        )
    ]


def _nested_budget(document: Mapping[str, Any], name: str, limit: int) -> list[Violation]:
    """The budget of an array inside each entry of another — the rows of one box."""
    outer, inner = name.split("/")
    found: list[Violation] = []
    for index, entry in enumerate(_listed(document, outer)):
        rows = entry.get(inner) if isinstance(entry, dict) else None
        if not isinstance(rows, list) or len(rows) <= limit:
            continue
        advice = BUDGET_ADVICE.get((outer, inner))
        found.append(
            Violation(
                _pointer(outer, index, inner, limit),
                f"{len(rows)} {inner} is past what one box can be read at — {limit} at "
                f"most. Show the ones this diagram is about and end the list with a "
                f"`...` field, which says there are more."
                if advice is None
                else f"{len(rows)} {inner} is past what one {_singular(outer)} can be read at — "
                f"{limit} at most. {advice}",
            )
        )
    return found


def _deep_budget(document: Mapping[str, Any], kind: str, name: str, limit: int) -> list[Violation]:
    """The budget of an array counted at every depth together: a mind map's branches.

    Counted in reading order, depth first, so the pointer lands on the entry that
    made one too many, wherever it is nested.
    """
    seen: list[str] = []

    def walk(entries: object, pointer: str) -> None:
        if not isinstance(entries, list):
            return
        for index, entry in enumerate(entries):
            seen.append(f"{pointer}/{index}")
            if isinstance(entry, dict):
                walk(entry.get(name), f"{pointer}/{index}/{name}")

    walk(document.get(name), f"/{name}")
    if len(seen) <= limit:
        return []
    return [
        Violation(
            seen[limit],
            f"{len(seen)} {name} in all is past what one {kind} can be read at — {limit} at "
            f"most, counted at every level. "
            + BUDGET_ADVICE.get((kind, f"{name}*"), "Split it into an overview and details.")
            + " The budget is not a canvas size, so a larger top-level 'width' does not lift it.",
        )
    ]


def _singular(name: str) -> str:
    """`categories` → `category`, `bars` → `bar`: one entry of a counted array."""
    return name[:-3] + "y" if name.endswith("ies") else name[:-1]


def _cell_budget(document: Mapping[str, Any], name: str, limit: int) -> list[Violation]:
    """The budget of a board's cell: how many cards share one column and one row."""
    outer, _ = name.split("@")
    found: list[Violation] = []
    counts: dict[tuple[object, object], int] = {}
    for index, card in enumerate(_listed(document, outer)):
        if not isinstance(card, dict):
            continue
        cell = (card.get("column"), card.get("row"))
        if not all(isinstance(part, str | None) for part in cell):
            continue
        counts[cell] = counts.get(cell, 0) + 1
        if counts[cell] == limit + 1:
            found.append(
                Violation(
                    _pointer(outer, index),
                    f"this is card {limit + 1} in one cell, and a board's cell can be read at "
                    f"{limit} at most — past that a reader counts instead of reading. Keep the "
                    f'ones that matter and end with a summary card, `{{"text": "+ 6 more", '
                    f'"role": "note"}}`, which says there are more.',
                )
            )
    return found


def _emphasis_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Every focal element past the cap, wherever in the document it was written.

    Counted across the whole document — nodes, items, positions, series, curves
    — because the reader's eye does not care which array a heavy mark came from.
    """
    found: list[Violation] = []
    focal: list[str] = []

    def collect(value: object, pointer: str) -> None:
        if isinstance(value, dict):
            if value.get("role") == EMPHASIS_ROLE:
                focal.append(pointer)
            for key, child in value.items():
                collect(child, f"{pointer}/{_escape(key)}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                collect(child, f"{pointer}/{index}")

    collect(document, "")
    for pointer in focal[EMPHASIS_CAP:]:
        found.append(
            Violation(
                f"{pointer}/role",
                f"{len(focal)} elements say {EMPHASIS_ROLE!r}, and a diagram may have "
                f"{EMPHASIS_CAP}. Emphasis means *look here first*; when three things "
                f"say it, none of them is first. Keep the one or two the diagram is "
                f"about and give the rest their ordinary role — or, if they really are "
                f"equal, emphasise none.",
            )
        )
    return found


def _referential_violations(document: Mapping[str, Any], kind: str) -> list[Violation]:
    """The checks JSON Schema cannot express: unique ids, and edges that land."""
    found: list[Violation] = []
    if kind in STATES_KINDS:
        return _states_violations(document)
    if kind in SEQUENCE_KINDS:
        return _sequence_violations(document)
    if kind in ENTITIES_KINDS:
        return _entities_violations(document)
    if kind in GANTT_KINDS:
        return _gantt_violations(document)
    if kind in BOARD_KINDS:
        return _board_violations(document)
    if kind in FISHBONE_KINDS:
        return []
    if kind in VENN_KINDS:
        return _venn_violations(document)
    if kind in JOURNEY_KINDS:
        return _journey_violations(document)
    if kind in TREEMAP_KINDS:
        return _treemap_violations(document)
    if kind in SANKEY_KINDS:
        return _sankey_violations(document)
    if kind in NUMBERLINE_KINDS:
        return _numberline_violations(document)
    if kind in BARMODEL_KINDS:
        return _barmodel_violations(document)
    if kind in WATERFALL_KINDS:
        return _waterfall_violations(document)
    if kind in PIE_KINDS:
        return _pie_violations(document)
    if kind in MINDMAP_KINDS:
        return _mindmap_violations(document)
    if kind in ARGUMENT_KINDS:
        return _argument_violations(document)
    if kind in FAMILYTREE_KINDS:
        return _familytree_violations(document)
    if kind in METER_KINDS:
        return _meter_violations(document)
    if kind in CLOCK_KINDS:
        return _clock_violations(document)
    if kind in SUNBURST_KINDS:
        return _sunburst_violations(document)
    if kind in PERT_KINDS:
        return _pert_violations(document)
    if kind in AUTOMATON_KINDS:
        return _automaton_violations(document)
    if kind in NEURALNET_KINDS:
        return _neuralnet_violations(document)
    if kind in PACKET_KINDS:
        return _packet_violations(document)
    if kind in WARDLEY_KINDS:
        return _wardley_violations(document)
    if kind in USECASE_KINDS:
        return _usecase_violations(document)
    if kind in RAILROAD_KINDS:
        return _railroad_violations(document)
    if kind in NETWORK_KINDS:
        return _network_violations(document)
    if kind in TIMING_KINDS:
        return _timing_violations(document)
    if kind in GITGRAPH_KINDS:
        return _gitgraph_violations(document)
    if kind == "chart":
        return _chart_violations(document)
    if kind == "quadrant":
        return _quadrant_violations(document)
    if kind in LANES_KINDS:
        found.extend(_lanes_violations(document))
    if kind in FILES_KINDS:
        entries = document.get("entries", ())
        # Only a well-formed list is worth reading for paths: the structural pass
        # has already reported anything else, and would be reported twice here.
        well_formed = isinstance(entries, list) and all(
            isinstance(entry, dict)
            and isinstance(entry.get("path"), str)
            and all(isinstance(entry.get(name, ""), str) for name in ("note", "link", "status"))
            for entry in entries
        )
        found.extend(
            Violation(_pointer("entries", index, name), message)
            for index, name, message in (problems(_entries(entries)) if well_formed else [])
        )
        root = document.get("root", "")
        if isinstance(root, str) and ("/" in root.strip("/") or root.strip() != root):
            found.append(
                Violation(
                    "/root",
                    f"{root!r} is one folder's name, drawn as the top row — not a path. "
                    "Put the folders below it in the entries' paths.",
                )
            )
    if kind in GRAPH_KINDS:
        middles = [
            index
            for index, node in enumerate(document.get("nodes", ()) or ())
            if isinstance(node, dict) and node.get("centre")
        ]
        for index in middles[1:]:
            found.append(
                Violation(
                    _pointer("nodes", index, "centre"),
                    "a second node says it is the centre. A diagram arranged around a "
                    "subject has one subject.",
                )
            )
        # An actor is drawn as the box's lead, and a box has one lead. A node
        # that wrote its own is not refused a *field* — it is told that the two
        # are the same slot, which is a different mistake and a different fix.
        for index, node in enumerate(document.get("nodes", ()) or ()):
            if not isinstance(node, dict) or not node.get("actor"):
                continue
            text = node.get("text")
            if isinstance(text, str) and "\n" in text.strip():
                found.append(
                    Violation(
                        _pointer("nodes", index, "actor"),
                        "this node names an actor and also writes its own lead — the "
                        "newline in its 'text' says the first paragraph is one. A box "
                        "has a single lead and the actor is it: either drop the actor, "
                        "or join the text into one paragraph.",
                    )
                )
        if middles and kind != "flow":
            found.append(
                Violation(
                    _pointer("nodes", middles[0], "centre"),
                    f"a {kind} is ranked from its root, so it has no middle to arrange "
                    f"around. Use a flow"
                    + (
                        " — or, for something the loop turns around rather than a step "
                        "on it, the cycle's own 'hub'."
                        if kind == "cycle"
                        else "."
                    ),
                )
            )
    if kind == "curve":
        marked: set[str] = set()
        located: dict[str, tuple[Any, Any]] = {}
        for curve_index, entry in enumerate(document.get("curves", ()) or ()):
            if not isinstance(entry, dict):
                continue
            for point_index, point in enumerate(entry.get("waypoints", ()) or ()):
                if not isinstance(point, dict) or not isinstance(point.get("id"), str):
                    continue
                if not point["id"]:
                    continue
                if point["id"] in marked:
                    found.append(
                        Violation(
                            f"/curves/{curve_index}/waypoints/{point_index}/id",
                            f"duplicate waypoint id {point['id']!r}",
                        )
                    )
                marked.add(point["id"])
                located[point["id"]] = (point.get("across"), point.get("up"))
        for index, span in enumerate(document.get("spans", ()) or ()):
            if not isinstance(span, dict):
                continue
            start, end = span.get("from"), span.get("to")
            for role, value in (("from", start), ("to", end)):
                if isinstance(value, str) and value not in marked:
                    found.append(
                        Violation(
                            f"/spans/{index}/{role}",
                            f"{value!r} is not the id of any waypoint in this document. A "
                            f"span measures between two points, so both need naming — give "
                            f"the waypoints ids.",
                        )
                    )
            if isinstance(start, str) and start == end:
                found.append(
                    Violation(
                        f"/spans/{index}/to",
                        "a span between a point and itself has no distance to name.",
                    )
                )
            elif (
                isinstance(start, str)
                and isinstance(end, str)
                and start in located
                and end in located
                and located[start] == located[end]
            ):
                found.append(
                    Violation(
                        f"/spans/{index}/to",
                        f"{start!r} and {end!r} are two names for the same place, so there "
                        f"is no distance between them to draw. A span makes a gap visible; "
                        f"this one has no gap.",
                    )
                )
        return found
    if kind == "timeline":
        entries = document.get("items")
        spans = document.get("spans")
        if not isinstance(entries, list) or not isinstance(spans, list):
            return found
        order = {
            str(entry["id"]): index
            for index, entry in enumerate(entries)
            if isinstance(entry, dict) and isinstance(entry.get("id"), str) and entry["id"]
        }
        for index, span in enumerate(spans):
            if not isinstance(span, dict):
                continue
            start, end = span.get("from"), span.get("to")
            for role, value in (("from", start), ("to", end)):
                if isinstance(value, str) and value not in order:
                    found.append(
                        Violation(
                            f"/spans/{index}/{role}",
                            f"{value!r} is not the id of any entry on this timeline. A span "
                            f"runs between two of its moments, so both need naming — give "
                            f"the entries ids.",
                        )
                    )
            if (
                isinstance(start, str)
                and isinstance(end, str)
                and start in order
                and end in order
                and order[start] >= order[end]
            ):
                found.append(
                    Violation(
                        f"/spans/{index}/to",
                        f"{end!r} is not after {start!r} on this timeline, so there is no "
                        f"interval between them to name. A span runs forwards.",
                    )
                )
        return found
    if kind == "matrix":
        cells = document.get("cells")
        if not isinstance(cells, list):
            return found
        identified: set[str] = set()
        for index, cell in enumerate(cells):
            if not isinstance(cell, dict) or not isinstance(cell.get("id"), str) or not cell["id"]:
                continue
            if cell["id"] in identified:
                found.append(
                    Violation(_pointer("cells", index, "id"), f"duplicate cell id {cell['id']!r}")
                )
            identified.add(cell["id"])
        for index, edge in enumerate(document.get("edges", ()) or ()):
            if not isinstance(edge, dict):
                continue
            for end in ("from", "to"):
                target = edge.get(end)
                if isinstance(target, str) and target not in identified:
                    found.append(
                        Violation(
                            _pointer("edges", index, end),
                            f"{target!r} is not the id of any cell in this document. An edge "
                            f"on a matrix joins two cells, and a cell needs an `id` before "
                            f"anything can name it.",
                        )
                    )
            if "status" in edge:
                found.append(
                    Violation(
                        _pointer("edges", index, "status"),
                        "a matrix is not a drawing of a change; 'status' marks one on a "
                        "flow or a tree.",
                    )
                )
            for name in ("polarity", "delay"):
                if name in edge:
                    found.append(
                        Violation(
                            _pointer("edges", index, name),
                            f"{name!r} marks a causal link, and a causal loop diagram is a "
                            f"`flow`: draw it as one.",
                        )
                    )
            if isinstance(edge.get("from"), str) and edge["from"] == edge.get("to"):
                found.append(
                    Violation(
                        _pointer("edges", index, "to"),
                        f"the cell {edge['from']!r} is joined to itself, and a grid has "
                        f"nowhere to draw that: the two ends are the same square.",
                    )
                )
        scale = document.get("scale")
        steps: set[str] | None = None
        if isinstance(scale, list) and all(isinstance(step, str) for step in scale):
            steps = set(scale)
            found.extend(_scale_violations(scale, cells))
        entries = document.get("key")
        if not isinstance(entries, list):
            return found
        cell_groups = {
            str(cell["group"])
            for cell in cells
            if isinstance(cell, dict) and isinstance(cell.get("group"), str) and cell["group"]
        }
        seen_groups: set[str] = set()
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            group = entry.get("group")
            if not isinstance(group, str):
                continue
            if steps is not None and group not in steps:
                found.append(
                    Violation(
                        f"/key/{index}/group",
                        f"{group!r} is not a step of this matrix's scale, so a key line for "
                        f"it would describe nothing in the drawing. Steps: "
                        f"{', '.join(str(step) for step in scale or ())}.",
                    )
                )
            elif steps is None and group not in cell_groups:
                found.append(
                    Violation(
                        f"/key/{index}/group",
                        f"no cell belongs to the group {group!r}, so naming it puts a line "
                        f"in the key for a fill that is not in the drawing. Groups here: "
                        f"{', '.join(sorted(cell_groups)) or 'none'}.",
                    )
                )
            elif group in seen_groups:
                found.append(
                    Violation(
                        f"/key/{index}/group",
                        f"the group {group!r} is named twice. One group, one line in the key.",
                    )
                )
            seen_groups.add(group)
        return found
    if kind == "funnel":
        stages = document.get("stages")
        found.extend(_funnel_amount_violations(document))
        if isinstance(stages, list) and stages:
            last = stages[-1]
            if isinstance(last, dict) and last.get("gate"):
                found.append(
                    Violation(
                        f"/stages/{len(stages) - 1}/gate",
                        "the last stage has no next stage, so nothing stands between it "
                        "and one. A gate names the threshold *after* a stage; drop it, or "
                        "add the stage it leads to.",
                    )
                )
        return found
    if kind not in GRAPH_KINDS + LANES_KINDS:
        return found

    nodes = document.get("nodes")
    if not isinstance(nodes, list):
        return found

    seen: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        identifier = node.get("id")
        if not isinstance(identifier, str):
            continue
        if identifier in seen:
            found.append(
                Violation(_pointer("nodes", index, "id"), f"duplicate node id {identifier!r}")
            )
        seen.add(identifier)

    found.extend(_status_violations(document, kind))
    found.extend(_class_violations(document, kind))
    found.extend(_causal_violations(document, kind, seen))

    if kind == "cycle":
        found.extend(_shaped_in_cycle(nodes))
        found.extend(_hub_violations(document, seen))
        hub = document.get("hub")
        if isinstance(hub, dict) and isinstance(hub.get("id"), str):
            seen.add(hub["id"])

    groups = document.get("groups")
    # A member may name a node or another group: a container that contains a
    # container is how the corpus draws three frames deep, and refusing it
    # would make the nesting the renderer supports unsayable.
    containers = {
        group["id"]
        for group in (groups if isinstance(groups, list) else ())
        if isinstance(group, dict) and isinstance(group.get("id"), str)
    }

    # A group is a name an edge may resolve to, because a relation can belong to
    # the whole container rather than to any one box in it — R5-2. The frame is
    # already a box with an extent and a border, so the only thing that was
    # missing was saying so. Only where the frame is *drawn*, though: see
    # `CONTAINER_KINDS`. A `cycle` accepts `groups` in its payload and draws
    # none, so a group id at an edge's end is an id its renderer cannot place.
    endpoints = containers if kind in CONTAINER_KINDS else frozenset()

    edges = document.get("edges")
    if isinstance(edges, list):
        for index, edge in enumerate(edges):
            if not isinstance(edge, dict):
                continue
            for end in ("from", "to"):
                target = edge.get(end)
                if not isinstance(target, str) or target in seen or target in endpoints:
                    continue
                found.append(
                    Violation(
                        _pointer("edges", index, end),
                        f"{target!r} is a group, and a {kind} is drawn as a ring of steps "
                        f"with no containers in it, so an edge here may only name a node"
                        if target in containers
                        else f"{target!r} is not the id of any node"
                        + (" or group" if kind in CONTAINER_KINDS else "")
                        + " in this document",
                    )
                )
        found.extend(_self_containment(edges, groups, endpoints))
        if kind in CONTAINER_KINDS + LANES_KINDS:
            found.extend(_loop_violations(edges, frozenset(containers), "edges"))

    if isinstance(groups, list):
        # A group id is a name a member may resolve to, and the renderer keys its
        # containment tree and its captions by it. So a repeated one does not
        # draw twice — the second silently replaces the first, and the drawing
        # stops matching the document with nothing said. An id shared with a node
        # is the same failure by another route: a member naming it could mean
        # either, and which one it gets is an implementation detail.
        named: set[str] = set()
        for index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            identifier = group.get("id")
            if isinstance(identifier, str):
                if identifier in seen:
                    found.append(
                        Violation(
                            _pointer("groups", index, "id"),
                            f"{identifier!r} is already the id of a node; a member naming it "
                            f"could mean either",
                        )
                    )
                elif identifier in named:
                    found.append(
                        Violation(
                            _pointer("groups", index, "id"),
                            f"duplicate group id {identifier!r}",
                        )
                    )
                named.add(identifier)

            members = group.get("members")
            if not isinstance(members, list):
                continue
            for position, member in enumerate(members):
                if isinstance(member, str) and member not in seen and member not in containers:
                    found.append(
                        Violation(
                            _pointer("groups", index, "members", position),
                            f"{member!r} is not the id of any node or group in this document",
                        )
                    )

    bands = document.get("bands")
    if isinstance(bands, list):
        # A band's members are nodes and nothing else. It runs *beside* boxes, so
        # naming a group would be asking it to run beside a frame, which is a
        # different drawing and not one this says how to make.
        for index, band in enumerate(bands):
            if not isinstance(band, dict):
                continue
            members = band.get("members")
            if not isinstance(members, list):
                continue
            for position, member in enumerate(members):
                if isinstance(member, str) and member not in seen:
                    found.append(
                        Violation(
                            _pointer("bands", index, "members", position),
                            f"{member!r} is not the id of any node in this document",
                        )
                    )
    return found


def parse_document(document: Mapping[str, Any]) -> Document:
    """Validate `document` and build the model.

    Raises:
        DocumentError: carrying every violation, each with its JSON pointer.
    """
    if not isinstance(document, Mapping):
        hint = (
            "; it arrived as a string, so pass the JSON object itself, not its text"
            if isinstance(document, str)
            else ""
        )
        raise DocumentError(f"a document must be a mapping{hint}", ())
    violations = validate_document(document)
    if violations:
        raise DocumentError(_describe(violations), violations)

    kind = str(document["kind"])
    if kind in STATES_KINDS:
        return _states_document(document)
    if kind in SEQUENCE_KINDS:
        return _sequence_document(document)
    if kind in LANES_KINDS:
        return _lanes_document(document)
    if kind in ENTITIES_KINDS:
        return _entities_document(document)
    if kind in GANTT_KINDS:
        return _gantt_document(document)
    if kind in BOARD_KINDS:
        return _board_document(document)
    if kind in FISHBONE_KINDS:
        return _fishbone_document(document)
    if kind in VENN_KINDS:
        return _venn_document(document)
    if kind in JOURNEY_KINDS:
        return _journey_document(document)
    if kind in TREEMAP_KINDS:
        return _treemap_document(document)
    if kind in SANKEY_KINDS:
        return _sankey_document(document)
    if kind in NUMBERLINE_KINDS:
        return _numberline_document(document)
    if kind in BARMODEL_KINDS:
        return _barmodel_document(document)
    if kind in WATERFALL_KINDS:
        return _waterfall_document(document)
    if kind in PIE_KINDS:
        return _pie_document(document)
    if kind in MINDMAP_KINDS:
        return _mindmap_document(document)
    if kind in ARGUMENT_KINDS:
        return _argument_document(document)
    if kind in FAMILYTREE_KINDS:
        return _familytree_document(document)
    if kind in METER_KINDS:
        return _meter_document(document)
    if kind in RAG_KINDS:
        return _rag_document(document)
    if kind in CLOCK_KINDS:
        return _clock_document(document)
    if kind in SUNBURST_KINDS:
        return _sunburst_document(document)
    if kind in PACKET_KINDS:
        return _packet_document(document)
    if kind in WARDLEY_KINDS:
        return _wardley_document(document)
    if kind in USECASE_KINDS:
        return _usecase_document(document)
    if kind in RAILROAD_KINDS:
        return _railroad_document(document)
    if kind in NETWORK_KINDS:
        return _network_document(document)
    if kind in TIMING_KINDS:
        return _timing_document(document)
    if kind in GITGRAPH_KINDS:
        return _gitgraph_document(document)
    if kind in PERT_KINDS:
        return _pert_document(document)
    if kind in AUTOMATON_KINDS:
        return _automaton_document(document)
    if kind in NEURALNET_KINDS:
        return _neuralnet_document(document)
    return Document(
        kind=kind,
        version=DOCUMENT_VERSION,
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        values=bool(document.get("values", True)),
        rise=bool(document.get("rise", False)),
        tree_style=str(document.get("style", "boxes")) if kind == "tree" else "boxes",
        bracket_root=str(document.get("root", "right")) if kind == "tree" else "right",
        theme=str(document.get("theme", "")),
        nodes=tuple(
            Node(
                id=entry["id"],
                text=entry["text"],
                role=entry.get("role", "step"),
                centre=bool(entry.get("centre", False)),
                note=entry.get("note", ""),
                actor=entry.get("actor", ""),
                status=entry.get("status", ""),
                klass=entry.get("class", ""),
            )
            for entry in document.get("nodes", ())
        ),
        classes=_classes(document),
        hub=_hub(document.get("hub")),
        edges=tuple(
            Edge(
                source=entry["from"],
                target=entry["to"],
                label=entry.get("label", ""),
                role=entry.get("role", "flow"),
                status=entry.get("status", ""),
                polarity=entry.get("polarity", ""),
                delay=bool(entry.get("delay", False)),
            )
            for entry in document.get("edges", ())
        ),
        loops=tuple(
            CausalLoop(
                text=entry["text"],
                nodes=tuple(entry["nodes"]),
                type=entry.get("type", ""),
            )
            for entry in document.get("loops", ())
        ),
        groups=tuple(
            Group(id=entry["id"], members=tuple(entry["members"]), text=entry.get("text", ""))
            for entry in document.get("groups", ())
        ),
        bands=tuple(
            Band(text=entry["text"], members=tuple(entry["members"]))
            for entry in document.get("bands", ())
        ),
        items=_items(document.get("items", ())),
        levels=_items(document.get("levels", ())),
        stages=_items(document.get("stages", ())),
        unit=str(document.get("unit", "")),
        rings=_items(document.get("rings", ())),
        cells=tuple(
            Cell(
                text=entry["text"],
                id=entry.get("id", ""),
                column=int(entry["column"]),
                row=int(entry["row"]),
                across=int(entry.get("across", 1)),
                down=int(entry.get("down", 1)),
                group=entry.get("group", ""),
                role=entry.get("role", "step"),
            )
            for entry in document.get("cells", ())
        ),
        columns=tuple(document.get("columns", ())),
        rows=tuple(document.get("rows", ())),
        scale=tuple(document.get("scale", ())),
        key=tuple(
            Key(group=entry["group"], text=entry["text"]) for entry in document.get("key", ())
        ),
        spans=tuple(
            Span(text=entry["text"], start=entry["from"], end=entry["to"])
            for entry in document.get("spans", ())
        ),
        positions=tuple(
            Position(
                text=entry["text"],
                across=float(entry["across"]),
                up=float(entry["up"]),
                role=entry.get("role", "step"),
            )
            for entry in document.get("positions", ())
        ),
        quadrants=tuple(str(name) for name in document.get("quadrants", ())),
        curves=tuple(
            Curve(
                name=entry.get("name", ""),
                waypoints=tuple(
                    Waypoint(
                        across=float(point["across"]),
                        up=float(point["up"]),
                        text=point.get("text", ""),
                        id=point.get("id", ""),
                    )
                    for point in entry["waypoints"]
                ),
                role=entry.get("role", "step"),
            )
            for entry in document.get("curves", ())
        ),
        axes=_axes(document.get("axes")),
        series=tuple(
            Series(
                name=entry["name"],
                data=tuple((float(x), float(y)) for x, y in entry["data"]),
                role=entry.get("role", "step"),
                mark=entry.get("mark", "line"),
                stack=entry.get("stack", ""),
            )
            for entry in document.get("series", ())
        ),
        root=str(document.get("root", "")),
        entries=_entries(document.get("entries", ())),
        order=str(document.get("sort", "given")),
        style=str(document.get("style", "icons")),
    )


def _describe(violations: Sequence[Violation]) -> str:
    heading = f"{len(violations)} violation{'s' if len(violations) > 1 else ''} in this document"
    return heading + ":\n" + "\n".join(f"  {violation}" for violation in violations)


def load_document(path: str | Path) -> Document:
    """Read and validate a JSON document from `path`."""
    location = Path(path)
    try:
        text = location.read_text(encoding="utf-8")
    except OSError as error:
        raise DocumentError(f"document could not be read: {location} ({error})", ()) from None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise DocumentError(f"document is not valid JSON: {location} ({error})", ()) from None
    document = parse_document(parsed)
    return replace(document, theme=_beside(document.theme, location))
