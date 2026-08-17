# B3: a consumer-facing skill so an agent can use drawspec without reading docs

The repository vendors Claude Code skills under `.claude/skills` for **its own
development** and ships none for **consumers**. The difference matters: an agent
working on somebody else's project, which needs a diagram, has no packaged way to
reach for drawspec — it would have to already know the tool exists, find the docs,
and read them.

A skill (and/or a small MCP server exposing `render` and `validate`) closes that
last gap. B1's `AGENTS.md` is the knowledge; this is the delivery.

**Decide before building, and the decision is the task's first half:**

* **Skill vs MCP server.** A skill is a document and costs nothing to ship in
  this repo; an MCP server is a process the consumer must run but works across
  clients. They are not exclusive, and the skill is the cheaper first move.
* **Where it lives.** In this repository under a consumer-facing path, or in the
  marketplace this project already consumes (`ARSENAL_REPO` in the `Makefile`)?
  Shipping it here keeps it versioned with the format it describes, which is the
  same argument that put the JSON Schema in the wheel.

Blocked on **B1** in substance — a skill whose content is not the brief would be a
second thing to keep current, which is the failure this project keeps designing
out.

## Acceptance gate

Prose, and deliberately so: the deliverable is a decision plus an artefact, and
what "works" means depends on which was chosen. Record the decision in the PR
description with the reasoning, and gate the artefact on the same rule B1 uses —
any document example it carries must validate against the live schema.

Do not mark this done without a written decision on skill-vs-MCP and on where it
lives. An artefact without that is a fork in the road taken silently.

## Tests

Whatever pins the examples. If it ships in this repo, extend B1's example-validation
test to cover the skill's documents too.

## Location

To be decided by the first half of this task.

---

## Recommendation, 2026-08-17 — after B1 landed

B1 changed what this task is worth, so the analysis is recorded before anything
is built.

**`AGENTS.md` + `llms.txt` already deliver most of what a skill would.** They are
the tool-agnostic convention: every coding agent that looks for repository
instructions finds `AGENTS.md`, and it is now gated so it cannot rot. A skill
would reach a narrower audience for the same content, and would be a *second*
copy of the format to keep current — which is the failure this project keeps
designing out.

**So the recommendation is: do not ship a skill from this repository.** The
remaining gap is not knowledge, it is *reach*: an agent has to already know
drawspec exists. That gap is closed by **A3** (so `pip install drawspec` works)
and **C1** (so GitHub search finds it), not by a skill.

**If something is built later, build the MCP server rather than the skill.** A
skill is a document — and the document already exists, one directory up. An MCP
server would add what no document can: `render` and `validate` as callable tools,
so an agent gets the JSON-pointer refusal back in its own loop instead of having
to shell out and parse stderr. That is a real capability, it is client-agnostic,
and it is worth its maintenance in a way a second copy of the brief is not.

Left **open** rather than closed: the owner may want the reach for a specific
client, and that is their call. But it should not be picked up as routine work —
reassess after A3 and C1 are done, since they address the same gap more cheaply.
