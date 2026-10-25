"""`network` — hosts on networks, drawn as buses with boxes hanging between them.

The kind's promises: networks are drawn top to bottom in the order written; a host
is a box under its topmost network with a line to every network it is on, and no
line crosses a bus it is not on; hosts whose spans are apart share a column; an
address sits beside its line; a group's backdrop holds only its members; and what
cannot be drawn that way is refused at its pointer before any layout runs.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from drawspec import render, render_text
from drawspec.buses import arrange
from drawspec.errors import FitError, ThemeError
from drawspec.kinds.network import NetworkDrawing, network_drawing
from drawspec.scene import TextLine
from drawspec.schema import NETWORK_HOST_MAX, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("network-*.json"))


def attach(*names: str) -> list[dict[str, str]]:
    return [{"network": name} for name in names]


def diagram(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "network",
        "networks": [
            {"id": "dmz", "address": "210.x.x.x/24"},
            {"id": "internal", "address": "172.x.x.x/24"},
        ],
        "hosts": [
            {
                "id": "web01",
                "networks": [
                    {"network": "dmz", "address": ".1"},
                    {"network": "internal", "address": ".1"},
                ],
            },
            {"id": "web02", "networks": attach("dmz", "internal")},
            {"id": "db01", "role": "store", "networks": attach("internal")},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any]) -> NetworkDrawing:
    return network_drawing(parse_document(document), THEME, MEASURER)


def violations(document: dict[str, Any]) -> dict[str, str]:
    return {violation.pointer: violation.message for violation in validate_document(document)}


def no_line_crosses_a_foreign_bus(document: dict[str, Any], drawing: NetworkDrawing) -> None:
    on = {host["id"]: {item["network"] for item in host["networks"]} for host in document["hosts"]}
    for host, x, top, bottom in drawing.lines:
        for network, (x0, y0, x1, y1) in drawing.buses.items():
            if network in on[host] or not x0 <= x <= x1:
                continue
            assert bottom <= y0 or top >= y1, (host, network)


# -- the references -----------------------------------------------------------


def test_there_are_reference_networks() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_validates_renders_and_keeps_its_lines_clear(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert validate_document(document) == ()
    assert render(document).startswith("<svg")
    no_line_crosses_a_foreign_bus(document, drawn(document))


# -- the layout ---------------------------------------------------------------


def test_networks_run_top_to_bottom_in_the_order_written() -> None:
    drawing = drawn(diagram())
    assert drawing.buses["dmz"][3] < drawing.buses["internal"][1]


def test_a_host_on_two_networks_stands_between_them() -> None:
    drawing = drawn(diagram())
    dmz, internal = drawing.buses["dmz"], drawing.buses["internal"]
    for host in ("web01", "web02"):
        _, top, _, bottom = drawing.boxes[host]
        assert dmz[3] < top and bottom < internal[1]
    assert drawing.boxes["db01"][1] > internal[3]


def test_every_attachment_has_a_line_reaching_its_bus() -> None:
    drawing = drawn(diagram())
    ends = {(host, round(y, 3)) for host, _, top, bottom in drawing.lines for y in (top, bottom)}
    assert ("web01", round(drawing.buses["dmz"][3], 3)) in ends
    assert ("web01", round(drawing.buses["internal"][1], 3)) in ends
    assert ("db01", round(drawing.buses["internal"][3], 3)) in ends


def test_a_bus_spans_exactly_its_hosts_columns() -> None:
    drawing = drawn(diagram())
    x0, _, x1, _ = drawing.buses["dmz"]
    for host in ("web01", "web02"):
        assert x0 < drawing.boxes[host][0] and drawing.boxes[host][2] < x1
    # db01 is not on the dmz, and the dmz bus does not reach over its column.
    assert not x0 <= (drawing.boxes["db01"][0] + drawing.boxes["db01"][2]) / 2 <= x1


def test_a_host_that_skips_a_network_stands_outside_its_bus() -> None:
    document = diagram(
        networks=[{"id": "a"}, {"id": "b"}, {"id": "c"}],
        hosts=[
            {"id": "p", "networks": attach("b")},
            {"id": "skip", "networks": attach("a", "c")},
            {"id": "q", "networks": attach("b")},
            {"id": "r", "networks": attach("a")},
        ],
    )
    assert validate_document(document) == ()
    no_line_crosses_a_foreign_bus(document, drawn(document))


def test_hosts_whose_spans_are_apart_share_a_column() -> None:
    arrangement = arrange(2, [[0], [0], [1], [1]])
    assert len(arrangement.columns) == 2
    assert all(len(column) == 2 for column in arrangement.columns)


def test_the_order_is_deterministic_and_prefers_the_order_written() -> None:
    first = arrange(1, [[0], [0], [0]])
    assert first.columns == ((0,), (1,), (2,))
    assert arrange(1, [[0], [0], [0]]) == first


def test_the_search_past_the_exhaustive_size_still_keeps_lines_clear() -> None:
    hosts = [[0, 1]] * 4 + [[1]] * 6 + [[1, 2]] * 3 + [[2]] * 3 + [[0, 2]]
    arrangement = arrange(3, hosts, [[0, 1, 2, 3]])
    assert arrangement.crossings == () and arrangement.clashes == ()


def test_addresses_are_written_beside_their_lines() -> None:
    drawing = drawn(diagram())
    words = [
        primitive.text for primitive in drawing.scene.primitives if isinstance(primitive, TextLine)
    ]
    assert words.count(".1") == 2
    assert any("210.x.x.x/24" in word for word in words)


def test_a_group_backdrop_holds_its_members_and_no_one_else() -> None:
    document = diagram(groups=[{"text": "web", "members": ["web01", "web02"]}])
    drawing = drawn(document)
    (x0, y0, x1, y1) = drawing.groups[0]
    for host, (left, top, right, bottom) in drawing.boxes.items():
        inside = x0 <= left and right <= x1 and y0 <= top and bottom <= y1
        assert inside == (host in ("web01", "web02")), host


def test_texts_do_not_overlap() -> None:
    document = json.loads((REFERENCE / "network-three-tier.json").read_text(encoding="utf-8"))
    boxes = drawn(document).texts
    for index, a in enumerate(boxes):
        for b in boxes[index + 1 :]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a, b)


def test_too_many_hosts_for_the_canvas_is_a_fit_error() -> None:
    hosts = [{"id": f"server-{index:02d}", "networks": attach("dmz")} for index in range(20)]
    with pytest.raises(FitError):
        render(diagram(networks=[{"id": "dmz"}], hosts=hosts))


# -- refusals -----------------------------------------------------------------


def test_a_line_no_order_keeps_clear_is_refused_at_the_host() -> None:
    names = ["n0", "n1", "n2", "n3", "n4"]
    document = diagram(
        networks=[{"id": name} for name in names],
        hosts=[
            {"id": "a", "networks": attach("n1", "n3")},
            {"id": "b", "networks": attach("n1", "n2", "n4")},
            {"id": "c", "networks": attach("n0", "n2", "n3")},
        ],
    )
    found = violations(document)
    pointer = next(pointer for pointer in found if pointer.startswith("/hosts/"))
    assert pointer.endswith("/networks")
    assert "which it is not on" in found[pointer]


def test_unknown_networks_and_members_are_refused_with_a_suggestion() -> None:
    document = diagram(groups=[{"members": ["web1"]}])
    document["hosts"][2]["networks"] = attach("internl")
    found = violations(document)
    assert "did you mean 'internal'" in found["/hosts/2/networks/0/network"]
    assert "did you mean 'web01'" in found["/groups/0/members/0"]


def test_a_network_no_host_is_on_is_refused() -> None:
    document = diagram()
    document["networks"].append({"id": "storage"})
    assert "empty bus" in violations(document)["/networks/2"]


def test_a_host_on_one_network_twice_is_refused() -> None:
    document = diagram()
    document["hosts"][2]["networks"] = attach("internal", "internal")
    assert "/hosts/2/networks/1/network" in violations(document)


def test_duplicate_ids_are_refused() -> None:
    document = diagram()
    document["hosts"][1]["id"] = "web01"
    assert "/hosts/1/id" in violations(document)


def test_a_host_in_two_groups_is_refused() -> None:
    document = diagram(groups=[{"members": ["web01"]}, {"members": ["web01", "web02"]}])
    assert "one backdrop" in violations(document)["/groups/1/members/0"]


def test_device_roles_are_refused_with_what_they_are_here() -> None:
    document = diagram()
    document["hosts"][0]["role"] = "router"
    message = violations(document)["/hosts/0/role"]
    assert "two networks" in message and "icons" in message


def test_placement_and_link_fields_are_refused() -> None:
    document = diagram(edges=[{"from": "web01", "to": "db01"}])
    document["hosts"][0]["column"] = 2
    found = violations(document)
    assert "/edges" in found and "/hosts/0/column" in found


def test_the_host_budget_is_enforced() -> None:
    hosts = [
        {"id": f"h{index}", "networks": attach("dmz")} for index in range(NETWORK_HOST_MAX + 1)
    ]
    document = diagram(networks=[{"id": "dmz"}], hosts=hosts)
    assert any(pointer.startswith("/hosts") for pointer in violations(document))


# -- theme and text -----------------------------------------------------------


def test_the_theme_sets_the_washes_and_refuses_a_dark_one() -> None:
    light = load_theme({"version": 1, "network": {"bus": 0.05, "group": 0.0}})
    assert light.network.bus == 0.05 and light.network.group == 0.0
    with pytest.raises(ThemeError):
        load_theme({"version": 1, "network": {"bus": 0.9}})
    with pytest.raises(ThemeError):
        load_theme({"version": 1, "network": {"shade": 0.1}})


def test_the_text_form_draws_buses_hosts_and_addresses() -> None:
    text = render_text(parse_document(diagram()))
    assert "dmz 210.x.x.x/24" in text and "internal 172.x.x.x/24" in text
    assert "web01" in text and "db01" in text and ".1" in text
    assert "┷" in text and "┯" in text
    ascii_text = render_text(parse_document(diagram()), charset="ascii")
    assert all(ord(character) < 128 for character in ascii_text)


def test_a_network_without_an_id_is_a_violation_not_a_crash() -> None:
    document = {
        "version": 1,
        "kind": "network",
        "networks": [{"text": "DMZ"}, {"id": "lan"}],
        "hosts": [{"id": "h", "networks": [{"network": "lan"}]}],
    }
    assert "/networks/0/id" in violations(document)


def test_a_host_stacks_only_with_its_own_group() -> None:
    arrangement = arrange(3, [[2], [1], [0]], [[2, 0]])
    assert arrangement.clashes == ()
    assert arrangement.column_of[1] != arrangement.column_of[0]


def test_a_group_clash_names_the_stranger_by_id(monkeypatch: pytest.MonkeyPatch) -> None:
    import drawspec.buses

    real = drawspec.buses.arrange

    def clashing(*arguments: Any) -> Any:
        return replace(real(*arguments), clashes=((0, 2),))

    monkeypatch.setattr(drawspec.buses, "arrange", clashing)
    found = violations(diagram(groups=[{"members": ["web01", "web02"]}]))
    assert "'db01'" in found["/groups/0/members"]
