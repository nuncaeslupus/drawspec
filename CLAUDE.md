## Keep the repository in step with its kinds

When a kind, a field, a role or an output format is added, removed or changed, the
same pull request updates everything that describes it — never a follow-up:

- `README.md` (the status list and the kind count), `docs/format.md`, `docs/guide.md`
- generated files: `make docs` (`docs/cli.md`, reference docs), `make schema`
- `AGENTS.md` (its kind table and guidance), `llms.txt`, `CHANGELOG.md` (Unreleased)
- the gallery (`make gallery`, commit the result) and `docs/proposals/README.md`'s row

Before opening the PR, grep the docs for the kind's name and for any number or list
the change made stale.

<!-- claude-arsenal: auto-managed -->
## Reviewing and merging

Every PR needs a review before it merges, and a required "CodeRabbit" check gates it.
CodeRabbit does not review this repo on its own (fewer than 10 stars), so comment
`@coderabbitai review` on each PR. If it will not review, review the diff yourself.
Merge only when CI is green and one of those reviews is done.

## Automatic session protocol

Every session, without waiting to be asked:

1. Read `arsenal/session/handover.md` for the previous session's context.
2. List the repository's issues labelled `arsenal:task` — **open and closed** — and
   save the JSON. Use whatever GitHub access this surface has; run
   `claude-arsenal/bin/github_channel.sh --detect` to find out which. Request
   `number`, `title`, `state`, `labels`, `assignees` and **not `body`** — the bodies
   are the bulk of that fetch and nothing downstream reads them.
3. Run `python3 claude-arsenal/scripts/query_status.py --issues <that file>` for the
   board, and report anything it flags.
4. Pick up work: `python3 claude-arsenal/scripts/task_select.py --issues <that file>`
   returns the next unblocked task, then
   `bash claude-arsenal/bin/claim_task.sh <id>` takes it (see `@claude-arsenal/AGENTS.md`).
   - **Nothing returned + workspace plans exist** → seed tasks from each plan.
   - **Nothing at all** → ask what to work on.
5. Open each task's PR with `Closes #<issue>` so merging it closes the task by itself.
6. After any session with tasks: update `arsenal/session/handover.md`.

@claude-arsenal/AGENTS.md
<!-- /claude-arsenal: auto-managed -->
