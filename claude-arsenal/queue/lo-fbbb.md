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
