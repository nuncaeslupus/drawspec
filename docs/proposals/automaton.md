# `automaton` — a finite automaton, as the textbooks draw it

A finite automaton drawn the way the theory of computation teaches it: each state a
circle with its name inside, an accepting state a double circle, the start state entered
by an arrow that comes from nowhere, and each transition an arrow labelled by the input
symbol it reads — several symbols between the same two states merged into one label
`a, b`, ε on an empty move, a move to the same state a loop on the circle. Deterministic
and nondeterministic automata (with or without ε-moves) and the two transducers, Mealy
(output on the transition, `a / 1`) and Moore (output in the state, `q0 / 1`).

This came as an owner request, and the owner chose a **new kind** over a style of
`states`. The two draw different notations for different readers. `states` is UML's state
machine: rounded boxes, a filled initial dot, a ringed final dot, `event [guard] /
action`, composite states and regions — a software design document. An automaton is the
notation of a formal-languages course and its exam: circles, a doubled ring, an arrow
from nowhere, symbols, and the conventions a student is marked on. Folding it into
`states` would have meant a style that changes every shape, the start marker, the
label grammar and half the validation; a kind is the honest boundary.

## The originals

The `find the originals` rule asks for at least two real figures. The owner approved
citing published examples found by web search; these were found that way. **The pages
themselves could not be opened from this session** (the fetch tool could not reach the
hosts), so what is said of each below is what the search results and their excerpts
show — a search-result reading, not a check of the figure itself.

1. **Wikipedia, "Deterministic finite automaton"**
   ([article](https://en.wikipedia.org/wiki/Deterministic_finite_automaton)) — *seen as a
   search result.* Its example accepts binary numbers that are multiples of 3: states
   S0, S1, S2 drawn as circles, S0 both the start and the accepting state; from S0, 0
   stays and 1 goes to S1; from S1, 0 goes to S2 and 1 back to S0; from S2, 0 goes to S1
   and 1 stays. A Princeton course page lists the same machine as a table
   ([COS 217, textual DFAs](https://www.cs.princeton.edu/courses/archive/fall16/cos217/asgts/01decomment/TextualDFAs)).
   This is `docs/reference/automaton-divisible-by-three.json`, and a test reads `1001`
   (nine) through it to S0.
2. **Sipser, *Introduction to the Theory of Computation*, the machine M1** — *seen
   through course notes built on the book, found by search*
   ([ECU notes, 3.1 Finite State Machines](https://cs.ecu.edu/abrahamsonk/6420/spr16/Notes/FiniteState/finiteState.html);
   [Fordham CISC 4090, lecture 1](https://storm.cis.fordham.edu/leeds/cisc4090/Lecture1.pdf)).
   The notes say the start state is marked by an arrow pointing at it from nowhere and
   the accept state is drawn as a double circle; they also give M1's transition table,
   which is the form the formal 5-tuple definition uses. The book itself was not opened.
3. **JFLAP** — *seen as search results*: the
   [JFLAP manual](https://www.inf.unibz.it/~calvanese/teaching/10-11-fl/lecture-notes/JFLAP-manual.pdf)
   (an initial state marked by an arrowhead, a final state by a double outline) and the
   [Kalamazoo College JFLAP cheat sheet](https://www.cs.kzoo.edu/cs105/labs/fsa/JFLAPcheatsheet.html)
   (drag from state to state, label the line with its symbol).
4. **Graphviz's `fsm` gallery example** — *seen through copies, found by search*: the
   Python `graphviz` package's
   [examples page](https://graphviz.readthedocs.io/en/stable/examples.html) reproduces
   it (`rankdir=LR`; LR_0, LR_3, LR_4 and LR_8 `doublecircle`, the rest `circle`; edge
   labels such as `SS(B)` and `S($end)`), as does the
   [PSGraph gallery](https://psgraph.readthedocs.io/en/stable/Example-Gallery/). The
   graphviz.org page was not reachable.
5. **TikZ's `automata` library** — *seen as a search result*: the
   [PGF/TikZ manual, automata chapter](https://tikz.dev/library-automata) (states as
   nodes with `state`, `initial` and `accepting` options; `loop above` for a self-loop;
   `bend left` for opposite arcs), and a [TUGboat article on drawing automata with
   TikZ](https://TUG.org/TUGboat/tb44-1/tb136prado-automata.pdf).
6. **Mealy and Moore** — *seen as search results*:
   [Wikipedia, "Mealy machine"](https://en.wikipedia.org/wiki/Mealy_machine) (each
   transition labelled with its input and its output; the example machine outputs the
   XOR of the last two inputs, an edge detector — `automaton-edge-detector.json`) and
   [Wikipedia, "Moore machine"](https://en.wikipedia.org/wiki/Moore_machine) (the output
   written in the state). For ε, the Korea University COSE215 slides
   ([lecture 5](https://plrg.korea.ac.kr/courses/cose215/2024_1/slides/lec5.pdf)) draw an
   ε-NFA and print its table with an ε column.

Checked against them: every source draws states as circles with the name inside, the
start marked by an arrow with no source (JFLAP's is an arrowhead on the state, TikZ's an
arrow labelled `start`; drawspec draws the plain arrow Sipser's notes describe), accepting
states doubled, transitions labelled by symbols, loops on the circle, and the formal
table beside the picture.

## The design

**The author writes the machine, nothing about its drawing.** `states` (`id`, optional
`text`, a Moore `output`), `start` (one id), `accepting` (ids), `transitions` (`from`,
`to`, and `on` — one symbol — or `"epsilon": true`; a Mealy `output`), and
`"deterministic": true` to have a DFA checked. One symbol per transition keeps every
move a row of the formal definition and lets validation check determinism; drawspec
does the merging into `a, b` that the textbooks do by hand.

**What is refused.** Ids that land nowhere (with the nearest offered); a move with
neither `on` nor `epsilon`, or both; ε written as a symbol (`"on": "ε"`, `λ`, `eps`),
so the empty move is never mistaken for input; a move written twice; in a declared
DFA, an ε-move or a second move on one symbol from one state, pointed at the second;
half a Mealy or Moore machine, or both at once; a name past 12 characters or over two
lines (that machine wants boxes — `states`); and the fields an author borrows from
elsewhere — `initial`, `final`, `alphabet`, `event`, `guard`, `label`, `role` — each
with what to write instead. A missing move in a DFA is allowed, as the textbooks leave
the dead state out; an unreachable state is allowed, as minimisation exercises draw one.

**The drawing.** Circles of one size (the widest name's), placed by the layered engine
from the start state, read across the page and down it when across does not fit. The
**arcs are the kind's own**: a straight line between two circles where nothing is in the
way; otherwise a quadratic bow, or for a long run a bracket that leaves both circles
sideways, each tried least-detour first and refused if it comes within the edge
clearance of a circle it does not belong to or runs along another stroke. A pair of
opposite moves is always two arcs bowed to the left of the way each travels (TikZ's
`bend left`), so they sit either side of the line between their states. **Loops and the
start arrow are placed first**, at sides of their circles the arrows are not expected to
use; the arcs then land clear of a loop's feet and of the start arrow's tip. Each label
is set beside its own arc — outside a bowed pair, nearer its own arc than any other — at
the first place along it that touches no stroke, circle or other label. When nothing
fits, the states are spread further apart and placed again, and only then is the
drawing refused, which lets the fit retry at a smaller type scale.

**Text output** is the transition table, which is how the textbooks print an automaton:
a row per state, a column per symbol (ε last), `→` for the start and `*` for accepting;
an NFA's cells are sets with `∅` for none, a DFA's a state or `—`; Mealy cells carry the
output, a Moore table ends in an `output` column. ASCII spells `->`, `eps` and `{}`.
Default width 100 columns, like `sequence` and `lanes`, because the table grows a column
per symbol.

## The limits

Twelve states and thirty-six transitions — the textbook figures hold three to eight
states. No pushdown or Turing machines (their labels are `a, X → Y` and `a → b, R`; a
later extension of the label, not of the drawing), no regular-expression transitions
(GNFAs), and no positions: placement is the layered engine's, which suits the
left-to-right machines textbooks draw and is weaker on rings (a mod-n counter comes out
as a column with one long return arc).

## Status

**Built.** `src/drawspec/kinds/automaton.py`, schema and validation in
`src/drawspec/schema.py`, references `docs/reference/automaton-divisible-by-three.json`,
`automaton-ends-in-ab.json`, `automaton-epsilon-nfa.json`,
`automaton-edge-detector.json` and `automaton-moore-parity.json`, tests in
`tests/test_kinds_automaton.py` and the text goldens.
