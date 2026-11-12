---
id: t-f47f4fb6
title: "review: test diet — tests to cut or move off every-push CI"
priority: 5
requires: [human:gate]
---

Imported from issue #199

From the test-diet pass of the repo review of 2026-11-11. Nothing was changed; tick or delete as triaged.

**Numbers:** test_files=81, tests=8413, test_lines=34193, source_lines=72370, suite_seconds=620, ci_jobs_per_push=2, ran_suite=True, note=suite_seconds is an estimate: the single serial run was killed at 480s having reached 34% (2,877 of 8,413 tests, inside test_embedding.py). Every file was then timed on its own (4 at a time on 4 cores): test_acceptance 346s, test_embedding 60s, test_gallery 39s, the other 78 files ~196s summed. CI runs the whole suite twice per push (Python 3.12 and 3.13 legs), plus a gallery job on PRs (3 jobs).

**Estimated saving:** ~70% of every-push CI test time (roughly 620s -> ~180s per leg serial) from findings 1-4 with no test deleted outright: ~320s from batching subprocesses, ~80s from a shared render cache, ~30s gallery, ~20s duplicate determinism test. Adding pytest-xdist on the 4-core runner would cut the remainder a further 2-3x. Test lines removed: under 2% - this is a time problem, not a volume problem. Derived from per-file wall times measured in this session; the split inside test_acceptance.py is inferred from its --durations list, not measured per function.

- The suite is 0.47 test lines per source line and mostly behavioural (layout/routing/schema refusals per diagram kind) - the line count is proportionate. The time is not: ~10 minutes serial, and about 55% of it is one test function.
- tests/test_acceptance.py::test_every_fixture_renders_identically_on_a_second_run starts 4 fresh Python interpreters for each of 223 reference documents (892 subprocesses). The file takes 346s of a ~620s suite; the 12 slowest tests in it are all this function (2-9s each).
- About 2,900 of the 8,413 tests are '223 reference documents x one invariant' sweeps spread over 7 files; each test renders its document again from scratch, with no shared cache and no conftest.py, so the reference set is rendered roughly 15 times per run.
- CI has no parallelism (no pytest-xdist), runs the full suite on both Python legs, and has no fast/slow split or path filter. tests/golden (60 text goldens) and the text sweeps are cheap (7-11s) and are not the problem; corpus/fixtures is not swept by the slow tests at all - the sweeps run over docs/reference (223 files).
- Single biggest win: batch the fresh-interpreter determinism check into one subprocess per hash seed (2 instead of 892). Same protection, about 5 minutes less per CI leg.

### Cuts and moves
- [ ] **[slow-tier] Determinism check spawns 892 interpreters; over half of all CI test time** (223 tests) — For each of 223 reference documents the test renders in-process and then in 4 fresh subprocesses (2 profiles x 2 PYTHONHASHSEED values). The file takes 346s; the other 463 tests in it are in-process renders. The check itself is valuable (hash-seed-dependent ordering is a real failure mode) but it does not need one interpreter per document. `tests/test_acceptance.py:81-116`
  - Protection lost: none if batched: one subprocess per seed renders every document in both profiles and prints them, compared against the in-process renders. If instead moved to main-only/nightly: a seed-dependent diff would be caught after merge rather than on the PR.
  - Action: Change RENDER_SCRIPT to take a list of paths and render all of them in both profiles, emitting JSON; run it twice (seed 1, seed 7919) from a module-scoped fixture and keep the 223 parametrized cases as cheap dictionary comparisons. Alternative: keep per-document subprocesses for one document per kind and mark the full sweep slow.
- [ ] **[ci-config] No parallelism, full suite on both Python legs, no fast/slow split** (8413 tests) — ci.yml runs `uv run pytest -q` serially in a 3.12 and a 3.13 leg, on every PR and every push to main, with no path filter and no marker for slow tests. pytest-xdist is not a dependency. The tests are independent parametrized renders, which is the ideal case for xdist. `.github/workflows/ci.yml (check job); pyproject.toml [project.optional-dependencies].dev, [tool.pytest.ini_options]`
  - Protection lost: none for xdist. Running the slow sweeps on only one Python leg loses a 3.13-only rendering difference on those sweeps until main/nightly - small for a pure-Python library with one dependency.
  - Action: Add pytest-xdist to the dev extra and run `pytest -q -n auto`. Register a `slow` marker; run `-m 'not slow'` on the 3.13 leg and the full suite on 3.12. Check that tests writing to shared paths (gallery, packaging wheel build) are xdist-safe first.
- [ ] **[slow-tier] Reference set re-rendered ~15 times: sweep files share no render cache** (2900 tests) — Seven files each parametrize over the same 223 docs/reference documents and render every one independently: acceptance (3 sweeps), embedding (4 sweeps, 892 tests), arrow_runs (2), margins, clearance, clipping, readability (2). That is ~2,900 tests and about 190s outside the subprocess cost. There is no tests/conftest.py and no session-scoped fixture. `tests/test_embedding.py:39, tests/test_arrow_runs.py:22, tests/test_margins.py:54, tests/test_clearance.py:150, tests/test_clipping.py:101, tests/test_readability.py:52,125, tests/test_acceptance.py:191,391`
  - Protection lost: none - the same invariants are asserted on the same documents; only the repeated rendering goes.
  - Action: Add tests/conftest.py with a session-scoped, memoised `reference_scene(name)` / `reference_svg(name, profile)` and have the sweep tests read from it. Results are deterministic (that is what finding 1 proves), so caching is sound.
- [ ] **[duplicate] Gallery is built four times in tests and again by a CI job** (4 tests) — Four tests each build the whole gallery (7.4-7.8s each, 30s of the file's 39s): both profiles, --check mode, and write mode. On every PR the separate `gallery` CI job also runs tools/gallery.py end to end. `tests/test_gallery.py:98-121; .github/workflows/ci.yml (gallery job)`
  - Protection lost: none - build once per profile in a module-scoped fixture and let the --check and write tests reuse those entries; the CI job still exercises the real script.
  - Action: Module-scoped fixture holding gallery.build('inline') and gallery.build('standalone'); monkeypatch gallery.build in the main() tests so they only test writing/check logic.
- [ ] **[duplicate] In-process determinism sweep duplicates the acceptance one** (223 tests) — test_every_fixture_renders_identically_twice_in_both_profiles renders each of 223 documents twice per profile and compares - the exact assertion that test_acceptance.py:112-113 already makes for the same documents before its subprocess comparison. Its own docstring in test_acceptance.py explains why the in-process version proves little. `tests/test_embedding.py:244-251`
  - Protection lost: none - covered by tests/test_acceptance.py::test_every_fixture_renders_identically_on_a_second_run (same documents, same profiles, stricter).
  - Action: Delete the function.
- [ ] **[meta] Prose and history checks on README, guide and AGENTS.md** (6 tests) — A handful of tests grep the repo's own prose: README must not contain 'No renderer yet' (true since the renderer landed), guide must contain the heading '## Choosing a role', AGENTS.md must be <= 200 lines, README must mention two paths, plus tests/test_skill.py front-matter limits. They cost milliseconds, so this is tidiness, not CI time. `tests/test_acceptance.py:172-183; tests/test_docs.py:108-124,245-250; tests/test_skill.py:28`
  - Protection lost: small: a broken README link or an oversized AGENTS.md would no longer fail CI; a line-count/link linter covers it. Keep the test_docs.py tests that check generated references are current and that README/AGENTS examples validate - those catch real drift.
  - Action: Delete test_the_readme_no_longer_says_there_is_no_renderer (historic). Leave the rest unless the owner wants them in a lint step.

### Keep
- tests/test_kinds_*.py (36 files, ~18k lines, ~1.9k tests, about 1s each): behavioural layout/refusal tests per diagram kind against 35k lines of kinds source - proportionate and fast.
- tests/test_text_output.py and tests/test_text_graph.py with tests/golden/text (60 goldens): 1,607 tests in ~18s total - cheap, keep on every push.
- tests/test_schema.py, test_routing.py, test_layout.py, test_wrap.py, test_measure.py: parser/geometry logic with real branches, all under 2s.
- tests/test_packaging.py (builds the wheel once, module-scoped, 1.3s) and test_acceptance.py's PATH-emptied render: real release-day protection.
- The 'Test without the png extra' CI step (3 files): cheap and guards an optional-import path.
- tests/test_docs.py generated-reference-is-current and example-validates tests.

## Acceptance gate

<!-- This task came from an issue, so its "gate" is prose. Write a real check
     below, then DELETE the `requires: [human:gate]` line in the front matter.
     Until that line is gone the selector will not offer this task, which is
     deliberate: a prose gate runs nothing, and a gate that runs nothing passes
     everything. -->

```bash
# arsenal:gate-placeholder — replace with the real check; it may land in this task's own PR
false
```
