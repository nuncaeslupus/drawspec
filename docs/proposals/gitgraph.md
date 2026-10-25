# `gitgraph` — commits on branches over time

A git graph: commits as marks on lanes, one lane per branch, time running across (or
down) the page, with the lines where a branch forks off and merges back, the tags on
releases, and a commit copied from one branch to another. It is the figure every
branching model is explained with, and nothing drawspec drew could say it: a `timeline`
has one line, a `gantt` has intervals rather than points, and a `flow` has no lanes in
time and would place the commits wherever its ranker liked.

This came as an owner request (new kinds borrowed from similar tools: Mermaid's
`gitGraph`), and it was checked against published originals before building, as the
proposals' *find the originals* rule asks.

## The originals

| # | Figure | What it draws | What it asks of the design |
|---|---|---|---|
| G1 | Vincent Driessen, [*A successful Git branching model*](https://nvie.com/posts/a-successful-git-branching-model/) (2010), the git-flow figure | five lanes — feature branches, develop, release branches, hotfixes, master — time running **down**, tags on master (`0.1`, `0.2`, `1.0`), merges in both directions | `direction: down`; lanes in the order written, not the order created (release sits beside develop); a release merged into master *and* back into develop; tags |
| G2 | Scott Chacon and Ben Straub, *Pro Git*, [3.2 Basic Branching and Merging](https://git-scm.com/book/en/v2/Git-Branching-Basic-Branching-and-Merging) (figures 3-10 to 3-17) | master, `hotfix` and `iss53` forking from C2; commits labelled only by id (C0–C6); a merge commit with two parents | commits labelled by `id` alone; two branches forking from the same commit; a merge commit as its own mark |
| G3 | Atlassian, [*Gitflow workflow*](https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow) | the same model across the page: main and develop lanes, feature, release and hotfix branches coloured per lane | `direction: right` as the default; colour per lane as a convention — so a theme key, never a document field |
| G4 | Paul Hammant, [*Trunk-Based Development: Branch for release*](https://trunkbaseddevelopment.com/branch-for-release/) | one trunk, a release branch cut late and never merged back; a bug fixed on trunk **cherry-picked** to the release branch, which is tagged per point release | `pick` by commit `id`; a picked commit's mark says *copy*; a branch that never merges back |
| — | Mermaid, [*Gitgraph diagrams*](https://mermaid.js.org/syntax/gitgraph.html) | the tool the request names: `commit`, `branch`, `checkout`, `merge`, `cherry-pick`, `tag`, commit types `NORMAL`/`REVERSE`/`HIGHLIGHT`, orientations LR/TB/BT | what to keep (the operations, a highlighted commit, two orientations) and what not to (an imperative `checkout` state; `order` and colour per branch in the document) |

## The design

**The input is a history, written in order — never a layout.**

```json
{
  "version": 1,
  "kind": "gitgraph",
  "direction": "right",
  "branches": [
    {"name": "main"},
    {"name": "feature/login", "from": "main", "role": "emphasis"}
  ],
  "steps": [
    {"on": "main", "id": "a1", "text": "Initial commit", "tag": "v0.1"},
    {"on": "feature/login", "text": "Add the login form"},
    {"on": "main", "text": "Fix a typo"},
    {"on": "main", "merge": "feature/login", "tag": "v1.0"}
  ]
}
```

- `branches` (1–8): a `name`, an optional `from` (a branch name, forking at that branch's
  latest commit when this branch's first step comes, or a commit `id` for an older fork
  point; it defaults to the first branch) and a `role`. One lane each, in the order
  written — G1 puts the release lane beside develop, which is not the order they were made.
- `steps` (1–30): each `on` a branch, with optional `text`, `id`, `tag` and `role`; a
  `merge` (a branch name) makes it a merge commit, a `pick` (an `id`) a cherry-pick. Every
  step names its branch, so there is no `checkout` state to get wrong — the one thing in
  Mermaid's syntax that an author working blind trips on.
- `direction`: `right` (default: labels under the marks, G2–G4) or `down` (G1: messages in
  a column beside the lanes, as `git log --graph` sets them — the one for sentences).

**Everything else is derived by replaying the history as git would:** each commit's
parents (the branch's latest commit; for a merge, the merged branch's latest; for a
branch's first commit, its fork point), the lanes, the spacing (a place in time per step,
the column wide enough for the longest label up to the page), and the lines: a fork leaves
its parent just after it and a merge arrives just before its commit, each turning with a
rounded corner in the band between two steps, so no line ever runs under a label. Lines
between commits on one lane stop at each mark.

**Marks say the kind of commit in greyscale:** a dot; a merge, a ring round a dot; a
cherry-pick, a *dashed* ring round a dot (a copy, G4 — its label is the original's); the
step the figure is about (`role: emphasis`, Mermaid's `HIGHLIGHT`), a square with a bold
label; an emphasised branch, a heavy lane and name. A tag is a luggage tag pointing at its
commit (above it across the page, before the message down it). Branch names head their
lanes in boxes, a dashed guide running to where the lane starts; down the page, long names
are staggered over two rows so the lanes stay close.

**Colour is the theme's, and on by default.** `[gitgraph] colours` gives each lane a
colour for its dots and a faint wash behind its name, as G3 and Mermaid colour lanes;
the lines stay ink, so colour never carries a crossing alone. The default theme sets six
mid-tones (blue, green, ochre, purple, red, grey), each 3:1 or better on white and on
`#121212`; `accent` sets its own; `blueprint` sets `[]`, lanes in the sheet's ink, and a
theme with a ground of its own that the default colours do not read on falls back to ink
too, unless it names colours of its own.

**Text output, yes** — it is the figure `git log --graph` already prints: a row per step,
oldest first, lanes as columns two cells apart, the fork on its own row after the parent
and the merge on its own before the commit, box-drawing corners and `┼` crossings from the
shared `Grid`; the label column carries `[branch]` at a branch's first commit, `(tag)` and
the message. Marks `●` `◉` `○` `■` (`*` `M` `o` `@` in ASCII).

## What it refuses

At its pointer: a step `on` an undeclared branch; a `merge` into itself, of a branch with no
commit yet, or of one already wholly merged (git: *already up to date*); a merge as a
branch's first commit (it would only fast-forward, and draws two lines into one mark); a
`pick` of an unknown or later `id`, of a merge commit (git needs `-m`), or of a commit
already in the branch; a step that is both a merge and a pick; a branch with no commit (a
name on a commit is a `tag`); a `from` on the first branch, naming nothing, or naming a
commit written after the branch starts; duplicate names, ids or tags, or an id equal to a
branch name. Fields refused with a reason: `lane`, `column`, `colour`, `parent`/`parents`,
`branch`, `checkout`, `type`, `date`, `tags`. Not offered, on purpose: Mermaid's `REVERSE`
commit type (a revert is a commit whose message says so), fast-forward merges (drawn, they
are no merge at all), octopus merges, a third orientation (bottom-to-top reads against the
page).

## The limits

8 branches and 30 steps (the readability budget), and the fit: across the page each step
takes a column, so a 640-wide page holds about a dozen steps with one-line labels — a
label whose longest word will not fit its column is a `FitError` whose remedy is
`direction: down`; down the page, branch names too long to leave the messages a third of
the width are one too. At most two `emphasis`, counted with everything else.

## Status

**Built.** `src/drawspec/kinds/gitgraph.py`, schema and validation in
`src/drawspec/schema.py`, `[gitgraph]` in `src/drawspec/theme.py`, reference drawings
`docs/reference/gitgraph-hotfix.json` (G2), `gitgraph-gitflow.json` (G1, down the page) and
`gitgraph-release-branch.json` (G4, in `accent`), tests in `tests/test_kinds_gitgraph.py`.
