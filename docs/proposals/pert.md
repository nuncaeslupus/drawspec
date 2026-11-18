# `pert` — a project network, activity on node, its schedule computed

A project network: each activity a box, an arrow for each *this cannot start until that
finishes*, and in every box the times the critical path method finds — when the activity
can start and finish at the earliest and at the latest, and how much slack (float) it has.
The chain of activities with no float is the **critical path**, and it is drawn heavy. This
is the precedence diagram method, activity on node, as PMBOK and the project-management
and operations textbooks teach it.

This came as an owner request (new kinds borrowed from similar tools), and it answers a
real gap. A `gantt` places bars at times the author already knows; a `flow` joins boxes
but computes nothing. A network diagram is the step *before* the Gantt chart: the author
knows durations and dependencies, and the diagram's whole job is to show the times and
the critical path those imply — numbers no author should compute by hand and then type.

## The originals

The `find the originals` rule asks for at least two real figures. The owner approved
citing published examples found by web search; these were found that way and the design
was checked against them.

1. **King Saud University, GE 404 lecture notes, "Scheduling networks — activity on
   node"** ([PDF](https://fac.ksu.edu.sa/sites/default/files/ge_404-lecture-5scheduling_networks-aon.pdf);
   companion lecture on precedence diagramming,
   [PDF](https://faculty.ksu.edu.sa/sites/default/files/ge_404-lecture-6scheduling_networks-precedence_diagramming_and_time_scaled_diagram.pdf);
   and [topic 4a, activity on node](https://faculty.ksu.edu.sa/sites/default/files/topic_4a_activity_on_node.pdf)).
   Construction-management course notes: activity boxes with ES and EF in the top corners
   and the duration between them, the activity in the middle, LS and LF in the bottom
   corners with the float between them; forward and backward pass; critical activities
   are the ones with zero total float, and they form a continuous chain from start to
   finish.
2. **Bilkent University IE 102 / IE 400 lecture decks, the "Milwaukee Paper
   Manufacturing" exercise** ([Lecture 6, CPM](https://courses.ie.bilkent.edu.tr/ie102/wp-content/uploads/sites/11/2018/02/Lecture-6-CPM-2018.pdf);
   [IE 400 Set 8](https://courses.ie.bilkent.edu.tr/ie102/wp-content/uploads/sites/8/2020/07/IE400_Set8_Project-Management.pdf)).
   The operations-management textbook example (Heizer and Render's): eight activities A
   to H, drawn activity-on-node with Start and Finish nodes, durations 2, 3, 2, 4, 4, 3, 5,
   2 weeks; the slack table gives A, C, E, G, H zero slack (critical path A-C-E-G-H,
   15 weeks), B and D one week, F six. This is `docs/reference/pert-textbook.json`, and
   the test suite checks drawspec computes exactly that schedule.
3. **PMI-style references on the precedence diagram method**:
   [Firebrand's PMP course material, 6.3 Sequence Activities](https://firebrand.training/no/learn/pmp/course-material/project-time-management/sequence-activities)
   and [PM Study Circle on PDM](https://pmstudycircle.com/precedence-diagramming-method/)
   (activities in nodes, joined by their logical relationships; finish-to-start the
   commonest), and the [PrepCast network diagram notes](https://www.project-management-prepcast.com/network-diagram),
   which say node layouts vary between sources — so the cell layout here follows the
   course notes above and a key names the cells on every figure.
4. **Three-point estimates**: [Wikipedia, three-point estimation](https://en.wikipedia.org/wiki/Three-point_estimation)
   and [Brunel University's OR notes on PERT](https://people.brunel.ac.uk/~mastjjb/jeb/or/netpert.html):
   expected duration (a + 4m + b) / 6, the 1-4-1 weighting fixed by the beta-distribution
   argument behind it.

Checked against them: every figure draws one box per activity with the computed times
in it, arrows finish-to-start, the critical path marked; none writes a time that was not
derived. Sources differ on whether the first activity starts at day 0 or day 1; drawspec
counts from 0 (EF = ES + duration), as Heizer and Render and every scheduling tool do,
and says so in the key.

## The design

**The author writes only what they know.** `activities`, each `{id, text, duration,
after}` — `after` is the ids of the activities that must finish first. No coordinates,
no ES/EF/LS/LF, no float, no critical flag: all of those are computed, and refused with
the reason if written. A top-level `unit` (`days`, `weeks`) goes in the key; optional
`start` and `finish` strings add milestones, joined to every activity that waits for
nothing and every one nothing waits for.

**drawspec computes the schedule.** A forward pass (ES = latest EF of what it is after,
or 0), a backward pass (LF = earliest LS of what comes after it, or the project's end),
float = LS − ES. The arithmetic is exact (`Fraction`), so a float of zero is zero and the
critical path never depends on rounding. A **loop** has no schedule, and is refused at
the `after` entry that closes it, with the loop's path in the message.

**PERT three-point estimates**, because they are cheap: an activity may give
`optimistic`, `likely` and `pessimistic` instead of `duration`, and its expected duration
(o + 4m + p) / 6 is what the schedule uses and the box shows, to two places. Variances
and the probability of finishing by a date are not drawn: that is a table.

**The drawing reuses what exists.** Boxes are sized once for the whole network (three
cells as wide as the widest number, the name wrapped above a minimum), so the cells line
up rank to rank. Placement is the layered engine's, across the page first and down it
when across does not fit; routing is the router's. A critical box is the `emphasis`
role, an arrow between two critical activities that leaves no gap the `strong` edge role
— weight, never colour alone. A key under the network names the cells, gives the
project's length and says heavy means critical; the theme's `[pert] key` turns it off.

**Text output** is cheap through the graph text router: each activity becomes a flow box
of its name and two lines of times (`ES=0 D=2 EF=2`, `LS=0 F=0 LF=2`), critical boxes
and lines heavy. A refusal is re-pointed at the activity it is about.

## The limits

Twenty activities and thirty-two dependencies — textbook exercises run to eight to
fourteen. Finish-to-start only: no lag, no start-to-start or finish-to-finish (a wait is
an activity of its own). No dates or calendars, as with `gantt`.

## Status

**Built.** `src/drawspec/kinds/pert.py`, schema and validation in `src/drawspec/schema.py`,
reference drawings `docs/reference/pert-textbook.json`, `pert-house.json` and
`pert-release.json`, tests in `tests/test_kinds_pert.py`.
