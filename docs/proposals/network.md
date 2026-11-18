# `network` — hosts on networks, in the nwdiag style

A network diagram as deployment documentation draws it: each network a horizontal bus,
its name and address on it; each host a box hanging under it, with a line to every
network it is on and the host's address on that network beside the line. A host on two
networks stands between them and joins them — a router, a firewall, a web server with a
public and a private side. Optional groups put a shaded backdrop behind a cluster.

This came as an owner request (new drawing types borrowed from similar tools), and it
answers a real gap: a `flow` joins boxes to boxes, so a network drawn as one either
invents a box per switch or draws every host pair, and neither is the picture a reader
of a runbook expects. Nothing drawspec draws joins boxes to a bus.

## The originals

Found by web search, as the owner approved for this request. Each was seen in search
results, and is described here from those results; the pages themselves were not
fetched (outbound fetches are blocked in the session that wrote this).

1. **PlantUML, *Network Diagram with nwdiag*** —
   [plantuml.com/nwdiag](https://plantuml.com/nwdiag) (also
   [cdn-0.plantuml.com/nwdiag](https://cdn-0.plantuml.com/nwdiag)). The canonical
   example: a `dmz` network `210.x.x.x/24` with `web01` and `web02`, an `internal`
   network `172.x.x.x/24` with the same two web servers and `db01`, `db02` on it only;
   per-node addresses on each network; groups declared inside or outside networks, with a
   description. Our `network-nwdiag.json` is that example.
2. **nwdiag (blockdiag), the original tool** — [pypi.org/project/nwdiag](https://pypi.org/project/nwdiag)
   and its Sphinx examples, e.g.
   [lpn-doc-sphinx-primer… nwdiag](https://lpn-doc-sphinx-primer-devel.readthedocs.io/extensions/blockdiag/nwdiag.html):
   the same `dmz`/`internal` sample in spec-text form, networks with an `address`, nodes
   with an address per network, `group` blocks.
3. **A three-tier deployment, as vendor guides describe it** — Tableau's enterprise
   deployment guide, part 3
   ([help.tableau.com … edg_part3](https://help.tableau.com/current/guides/enterprise-deployment/en-us/edg_part3.htm)):
   a public DMZ subnet for the web tier that proxies to an application tier, a separate
   data tier subnet, a firewall between tiers. Our `network-three-tier.json` draws that
   shape: internet, DMZ, internal, storage, with the web tier on the first two and the
   databases on the last two.
4. **A small office network** — Microsoft's *Small Office Network* reference
   ([learn.microsoft.com … cc776089](https://learn.microsoft.com/en-us/previous-versions/windows/it-pro/windows-server-2003/cc776089(v=ws.10))):
   one router between the internet line and the office LAN, clients and a server behind
   it. Our `network-office.json` adds a guest network on the same router.

Checked against the design: every one is buses plus hosts plus per-network addresses,
with groups in 1 and 2; none needs a host-to-host link, a coordinate or an icon to read.

## The design

```json
{
  "version": 1,
  "kind": "network",
  "networks": [
    {"id": "dmz", "address": "210.x.x.x/24"},
    {"id": "internal", "text": "Internal", "address": "172.x.x.x/24"}
  ],
  "hosts": [
    {"id": "web01", "networks": [{"network": "dmz", "address": ".1"},
                                 {"network": "internal", "address": ".1"}]},
    {"id": "db01", "role": "store", "networks": [{"network": "internal"}]}
  ],
  "groups": [{"text": "web", "members": ["web01"]}]
}
```

- **`networks`** are drawn top to bottom in the order written: that order is the one
  thing the author decides, because it says which way traffic goes. `text` defaults to the
  `id`; `address` is words, written after the name on the bus.
- **`hosts`** each name their `networks`, each with an optional `address`. A host's box
  sits under its topmost network; a line goes up to it and down to every other network it
  is on. `role` reuses the shapes drawspec already has: `step` (a box: any device),
  `emphasis`, `store` (a drum: a database), `person` (a client). No device icons.
- **`groups`** list `members`; each is a shaded backdrop behind them with its name at the
  top left, in a band of its own so no line runs through the words.

**The columns are derived.** A host's line through a bus it is not on would read as
attached. `drawspec.buses` searches the column order (every order up to seven hosts, a
local search from four starting orders past that) for the fewest such crossings — usually
none — then for the fewest columns, the shortest buses and the order nearest the one
written.
Hosts whose vertical spans are apart stack in one column, as nwdiag stacks them. A bus
runs from its first host's column to its last, and is long enough for its name.

**A hop where a line must cross a bus.** When no order keeps a line clear, the line
crosses the bus with a hop: it stops short of the bar, jumps it in a half circle to the
right, and goes on — the wiring diagram's mark for two lines that cross without joining,
which reads as *not on this network* without a legend. The order with the fewest hops
wins, and a bus's name is set clear of any hop over it. (This was first built refusing
such a document at the host; the owner's call was that a diagram that can be useful is
drawn. The refusal's advice still loses a hop: put the host on the network in between
too, or reorder `networks` so the ones it joins are neighbours.)

## What it refuses

- Coordinates and placement: `column`, `order`, `x`, `y` — the columns are derived.
- `icon`, `shape`, and device roles (`router`, `firewall`, `server`, `database`,
  `switch`, `cloud`, `client`): each refusal says what that device is in this vocabulary
  (a router is a host on two networks; a database is `store`; the internet is a network).
- `edges`: hosts are joined through networks; links between boxes are a `flow`.
- A network no host is on, a host on the same network twice, an unknown network or member
  id (with a *did you mean*), a host in two groups, an empty name.
- A group no column order keeps free of a stranger's box, at its pointer. A host whose
  line no order keeps clear of a bus is not refused: the line hops the bus.

## The limits

Six networks, 24 hosts, 6 groups (the readability budget), past which a network diagram
is an inventory: draw an overview with one host per role, and a diagram per segment. At
most two `emphasis` hosts, as everywhere. A row of hosts wider than the canvas narrows
the boxes (long names wrap) before it is refused by fit.

## Text

It has a text form: buses as heavy rules with their names to the left (`━━┯━━`), hosts as
boxes in the same columns as the SVG, addresses beside the lines, groups as dashed frames.
A hop is the bus broken a cell either side of the line, `━╸│╺━` (`= | =` in ASCII): no
junction glyph, so it cannot be read as a join (`━┿━`).
nwdiag's own example fits 80 columns; the three-tier and office references are wider and
refuse at 80 naming the width they need.

## Status

**Built.** `src/drawspec/kinds/network.py` (drawing and text), the column search in
`src/drawspec/buses.py`, schema and validation in `src/drawspec/schema.py`, a `[network]`
theme section (bus and group washes), reference drawings `docs/reference/network-*.json`,
tests in `tests/test_kinds_network.py`.
