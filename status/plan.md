# Plan: drawspec — declarative diagram spec to themeable SVG

**Date**: 2026-08-11
**Specification**: `status/specification.md`
**Author**: drawspec

---

## Technical solution

### Architecture overview

One pipeline, three rendering families, two shared services, one emitter.

```
document (JSON)
      │
      ├─ schema.parse ──────────► Document        (frozen dataclasses; rejects
      │                                            every field the author must
      │                                            not control)
      ├─ theme.load ────────────► Theme           (TOML → frozen dataclass;
      │                                            greyscale invariant checked
      │                                            at load)
      │
      ▼
  text.measure  ◄──── fonttools ──── font files   (advance widths, kerning,
      │                                            line breaking, block height)
      ▼
  box sizing (geometry derived from measured text + theme padding)
      │
      ├── graph kinds ──► LayoutEngine ──► routing ──► labels ──┐
      │   flow, tree      (protocol:                            │
      │                    sizes in,                            │
      │                    coords out)                          │
      ├── grid kinds ─────────────────────────────────────────► ├──► Scene
      │   stack, timeline, columns                              │    (primitives
      │                                                         │     in final
      ├── shape kinds ────────────────────────────────────────► │     coords,
      │   pyramid, rings, cycle                                 │     tagged by
      │                                                         │     role, no
      └── chart kind ─────────────────────────────────────────► ┘     styling)
                                                                       │
                                                    Scene + Theme ─────┤
                                                                       ▼
                                                                  emit.svg
                                                          (the single place
                                                           styling happens, and
                                                           therefore the single
                                                           place inline-safety
                                                           is enforced)
```

Two seams carry the design.

**`Scene` is the convergence point.** Every family — graph, grid, shape, chart —
produces the same thing: a list of primitives in final coordinates, each tagged
with a semantic role, carrying no styling at all. Styling is applied once, by
the emitter, from the theme. This is why acceptance test 1 ("SVG safe to paste
inline into Markdown") is satisfied in one file rather than four, and why a
fifth family later costs nothing in inline-safety work.

**`LayoutEngine` is the escape hatch.** One method — nodes with measured sizes
in, coordinates out. It is the only coupling to a layout implementation, which
is what makes the spec's recommendation reversible: if the pure-Python default
proves inadequate, a Graphviz (`-Tplain`) or ELK engine is an additive change
behind the same protocol, not a rewrite. T7 exists to make that decision with
pictures rather than argument, and it runs *before* the implementation task.

### Data flow

drawspec is a pure function. A document and a theme go in; a string comes out.
There is no request/response cycle, no queue, no job. The only I/O is reading
the document, the theme and font files, and writing the SVG.

The one flow worth naming is the failure path: `DocumentError` is raised during
parse and names the offending field with its JSON pointer; `ThemeError` during
theme load; `FitError` during sizing, once it is known that content cannot fit
at the theme's minimum legible size; `LayoutError` from the engine. Each is
raised as early as it can be detected, so a model authoring blind gets the most
specific message available.

### State changes

| Service | Database | Change | Description |
|---------|----------|--------|-------------|
| drawspec | — | none | Pure function; no persistence, no migrations, no schema evolution beyond the versioned input contract |

### Technology choices

| Choice | Justification |
|--------|--------------|
| Pure Python, no system binaries | The spec's `system_dependencies == 0` criterion. `pip install graphviz` gives bindings only, so a Graphviz default would push a C binary onto every consumer and every CI job for engine power that a median-4-node corpus does not need |
| `fonttools` | The only runtime dependency. Reads `hmtx`/`kern` from any font file, so an unseen font works exactly like a known one — no hardcoded metric tables, which was an explicit requirement |
| TOML themes | A consumer can version and diff a theme without importing drawspec. Parsed into a frozen dataclass that is also constructible directly for programmatic use |
| Frozen dataclasses throughout | Determinism is a success criterion; immutable values plus explicit sort orders make byte-identical reruns achievable rather than hoped for |
| `LayoutEngine` as a protocol | Defers the engine decision (T7) without blocking the eight tasks that do not depend on it |
| Bundled generic serif / sans / mono | "Replace and warn" needs something to replace *with*. Bundling three permissively-licensed families makes substitution deterministic across hosts instead of depending on what the machine happens to have |
| Own chart rendering (no matplotlib) | matplotlib's SVG fails the inline-Markdown test worse than the diagram tools do — embedded font paths, clip-path ids, hardcoded colours |

### Out of scope

- Any diagram kind beyond the nine in the corpus. A tenth needs evidence, per
  the brief's "no feature nobody asked for".
- Ports, swimlanes, nested compound graphs, animation, interactivity.
- Raster output. SVG only; a consumer who needs PNG can convert.
- Reproducing the anonymized corpus fixtures. They are reference material; the
  test suite uses fixtures authored for the cases under test.
- Any content, vocabulary or styling specific to the consumer whose corpus
  drove this. The theme is the proof of that boundary.

---

## Implementation tasks

The **Gate** column is the objective pass/fail for the task, derived from the
spec's success criteria.

| T# | Description | Service | Size | Depends | Gate | Tests |
|----|-------------|---------|------|---------|------|-------|
| T1 | `Scene` primitives (`Rect`, `Ellipse`, `Polygon`, `Path`, `TextRun`), the SVG emitter with its two embedding profiles, and the embedding-safety validator it enforces on its own output | `drawspec.scene`, `drawspec.emit` | M | — | `embedding_safety_violations == 0` | `test_emit_any_scene_produces_no_style_element` in `tests/test_emit.py` — emitted SVG contains no `<style>` element, in either profile. `test_emit_two_documents_on_one_page_produces_no_duplicate_ids` — concatenating two renders yields no repeated `id`. `test_emit_inline_profile_strokes_use_currentcolor` — the inline profile inherits colour. `test_emit_standalone_profile_leaves_no_unresolved_currentcolor` — the standalone profile resolves every colour and carries explicit `width`/`height`. `test_emit_scene_with_undeclared_role_raises_error` — a primitive tagged with a role the theme does not declare raises. `test_emit_same_scene_twice_produces_identical_bytes` — two emissions are byte-equal |
| T2 | `Theme` frozen dataclass, TOML loader, node **and edge** role vocabularies, the elastic-fit band, and the greyscale invariant checked at load; one bundled default theme | `drawspec.theme` | M | — | `greyscale_ambiguous_role_pairs == 0` | `test_theme_roles_differing_only_by_colour_raises_themeerror` in `tests/test_theme.py` — two roles with identical shape/dash/weight and a luminance delta below 0.25 are rejected. `test_theme_roles_differing_by_dash_pattern_loads_successfully` — a non-colour channel difference is accepted. `test_theme_edge_role_with_head_none_loads_and_renders_a_plain_line` — a headless connector is expressible. `test_theme_edge_role_head_outside_vocabulary_raises_themeerror` — the head vocabulary is closed. `test_bundled_default_theme_loads_without_violations` — the shipped theme passes its own invariant |
| T3 | Text measurement from font files via `fonttools`: advance widths, kerning, cached; plus "replace and warn" substitution against bundled generic serif/sans/mono | `drawspec.text` | L | — | `text_measurement_error_ratio <= 0.02` | `test_measure_reference_strings_match_font_tables_within_two_percent` in `tests/test_measure.py` — measured widths agree with an independent reader of the same font's `hmtx`. `test_measure_previously_unseen_font_returns_metrics` — a font not in any bundled table measures correctly. `test_measure_unresolvable_font_substitutes_and_warns` — emits `FontSubstitutionWarning` naming requested and substituted families. `test_measure_kerned_pair_differs_from_sum_of_advances` — kerning is applied, not ignored |
| T4 | Document model and validation, plus the **published** JSON Schema: a versioned artefact with a stable `$id`, committed and shipped in the package, `additionalProperties: false` throughout so forbidden fields fail by name and by JSON pointer | `drawspec.schema`, `schema/drawspec-v1.schema.json` | L | — | `forbidden_field_acceptance_count == 0` | `test_document_with_forbidden_field_raises_documenterror_naming_field` in `tests/test_schema.py` — parametrized over every field in spec §5.1's rejection table; each raises, and the message carries the field's JSON pointer. `test_document_missing_version_raises_documenterror` — `version` is required. `test_document_with_node_or_edge_role_outside_vocabulary_raises_documenterror` — both vocabularies are closed. `test_published_schema_matches_the_runtime_validator` — the committed `.schema.json` accepts and rejects exactly what the parser does, so editor completion never disagrees with the tool |
| T5 | Line breaking and text block sizing: wrap to a width, compute block height from line count and theme line-height | `drawspec.text` | M | T2, T3 | `text_overflow_count == 0` | `test_wrap_produces_lines_all_within_the_given_width` in `tests/test_wrap.py` — every returned line measures at or below the max width. `test_wrap_word_longer_than_max_width_raises_fiterror` — an unbreakable run wider than the box fails loudly. `test_wrap_block_height_equals_lines_times_line_height` — height is derived, not guessed |
| T6 | Box geometry derived from measured text plus theme padding; vertical centring; same-rank size normalisation; **elastic fit** — one uniform type-scale factor chosen within the theme's band; `FitError` below the minimum legible size | `drawspec.geometry` | M | T13 | `text_outside_shape_count == 0` | `0` — every label corner inside its own trapezoid and inside its own arc, checked against the outlines rather than bounding boxes | `uv run pytest tests/test_kinds_shape.py -q` (24 passed); `make gallery` | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| T6b | `text_overflow_count == 0`, on the real outlines | `0` — the two reference decision nodes drop from 254x103 and 250x133 to 220x74 and 237x103: 38% and 26% less area, and the first now sets on one line instead of two | `uv run pytest tests/test_box.py -q` (66 passed) | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| D-1 | `text_overflow_count == 0`, and a cycle reads as a cycle | `0` — steps evenly spaced to 1e-6 for 2..8 nodes, every arc running one way, no arc leaving its sector or entering a box | `uv run pytest tests/test_kinds_cycle.py -q` (28 passed); `make gallery` | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| T0 | gallery builds for every reference document | `9` reference documents, one per kind; 3 drawn and 6 correctly listed as unimplemented | `uv run pytest tests/test_gallery.py -q` (13 passed); `make gallery` | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| T12 | `same_rank_size_variance == 0` | `0` — one distinct (width, height) per kind across stack, columns and timeline; ticks evenly spaced to 6 decimals | `uv run pytest tests/test_kinds_grid.py -q` (43 passed) | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| T8 | `node_overlap_count == 0` | `0` — across 5 graph shapes × 2 directions and 100 pseudo-random graphs; deterministic, and stable under a reordered input | `uv run pytest tests/test_layout.py -q` (139 passed) | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| T7 | `candidate_engines_rendered == 2` | `2` — both engines, 0 overlaps and 0 crossings on 3 documents × 2 directions, both deterministic | `uv run pytest tests/test_layout_spike.py -q` (35 passed); `uv run python tools/spike_layout.py` | `claude/continuation-yq88jv` | CPython 3.12, Linux, grandalf 0.8 | 2026-08-12 |
| T6 | `text_overflow_count == 0` | `0` — text inside the padding on all four sides for 4 roles × 5 texts; centring within 0.5 px; one fit factor across all four levels | `uv run pytest tests/test_box.py -q` (62 passed) | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| T5 | `text_overflow_count == 0` | `test_box_contains_its_text_with_full_padding_on_all_four_sides` in `tests/test_box.py` — the text extents sit inside the box inset by the theme padding, bottom included. `test_box_text_is_vertically_centred_within_half_a_pixel` — centring is computed from ascent/descent, not approximated. `test_fit_applies_one_scale_factor_to_every_type_level` — the ratios between title, heading, body and label are unchanged after scaling, so no diagram gains a new type size. `test_fit_chooses_the_largest_factor_that_fits_within_the_band` — shrinking stops as soon as the content fits. `test_fit_below_scale_min_or_min_legible_size_raises_fiterror` — refuses to shrink past the band. `test_boxes_of_the_same_rank_are_normalised_to_equal_size` — peers match |
| T7 | **Spike**: implement the `LayoutEngine` protocol against both `grandalf` and a direct layered implementation, render the three reference documents through each, and record the decision with its escape route | `drawspec.layout` | M | T6 | `candidate_engines_rendered == 2` | `test_spike_each_candidate_engine_lays_out_all_reference_documents` in `tests/test_layout_spike.py` — both engines return valid positions for all three reference documents with no overlapping boxes |
| T8 | The chosen default layout engine behind the protocol: ranking, cycle breaking, crossing reduction, coordinate assignment | `drawspec.layout` | L | T7 | `node_overlap_count == 0` | `test_layout_returns_positions_with_no_overlapping_boxes` in `tests/test_layout.py` — no two node boxes intersect. `test_layout_of_a_tree_places_children_after_their_parent` — rank increases with depth. `test_layout_of_a_cyclic_graph_terminates_and_returns_positions` — cycles are broken, not looped on. `test_layout_is_deterministic_across_runs` — identical input yields identical positions |
| T9 | Orthogonal edge routing: border anchoring, axis-aligned segments only, minimum shaft length, no crossing of node boxes | `drawspec.routing` | L | T8 | `edge_anchor_violations == 0` | `test_route_endpoints_lie_exactly_on_node_borders` in `tests/test_routing.py` — every edge starts and ends on a border, neither short nor overshooting. `test_route_produces_only_axis_aligned_segments` — no diagonal segments. `test_route_shaft_length_is_at_least_the_theme_minimum` — no head-without-shaft is expressible. `test_route_does_not_cross_any_node_box` — routes avoid boxes |
| T10 | Edge label placement with overlap avoidance against paths, boxes and other labels | `drawspec.routing` | M | T9 | `label_overlap_count == 0` | `test_edge_label_does_not_intersect_any_edge_path` in `tests/test_labels.py` — the label box misses every path. `test_edge_label_does_not_intersect_any_node_box` — and every node. `test_edge_label_offsets_when_the_default_position_is_occupied` — a fallback position is chosen rather than overlapping |
| T11 | Graph kinds: `flow`, `tree` — document to `Scene`. **`cycle` moved to D-1**, see below | `drawspec.kinds` | L | T4, T10 | `text_overflow_count == 0` | `test_flow_document_renders_svg_passing_inline_safety` in `tests/test_kinds_graph.py` — a flow document round-trips to safe SVG. `test_tree_child_ranks_increase_with_depth` — hierarchy is visible in the geometry |
| T12 | Grid kinds: `stack`, `timeline`, `columns` — positions from counting, no layout engine | `drawspec.kinds` | M | T4, T6 | `same_rank_size_variance == 0` | `test_stack_layers_are_equal_height_and_full_width` in `tests/test_kinds_grid.py` — layers are uniform. `test_columns_of_the_same_role_are_equal_width` — peers match. `test_timeline_ticks_are_evenly_spaced` — spacing is constant |
| T13 | Shape kinds: `pyramid`, `rings` — parametric geometry with text fitted to the usable span | `drawspec.kinds` | M | T4, T6 | `text_outside_shape_count == 0` | `test_pyramid_levels_are_equal_height_with_constant_width_progression` in `tests/test_kinds_shape.py` — proportions are regular. `test_pyramid_level_text_fits_the_narrowest_span_of_its_level` — text never crosses a sloped side. `test_ring_label_is_offset_below_its_own_arc` — labels do not touch their ring. `test_innermost_ring_label_is_centred` — the exception is honoured |
| T14 | Chart kind: scales, ticks, rotated axis labels, series paths, point markers and labels | `drawspec.charts` | L | T4, T6 | `unlabelled_axis_count == 0` | `test_chart_without_an_axis_label_raises_documenterror` in `tests/test_kinds_chart.py` — an unlabelled axis is a validation error. `test_chart_point_markers_lie_on_the_series_path` — markers are on the line, not beside it. `test_chart_point_labels_do_not_intersect_the_series_path` — labels avoid the curve and the plot edge. `test_chart_vertical_axis_label_is_rotated_and_horizontal_is_not` — orientation is constant |
| T15 | CLI: `render`, `validate`, `theme check`, `schema`, with `--width`/`--height`/`--profile` overrides and documented exit codes | `drawspec.cli` | M | T11, T12, T13, T14 | `cli_exit_code_mismatches == 0` | `test_render_valid_document_writes_svg_and_exits_zero` in `tests/test_cli.py` — the happy path. `test_validate_invalid_document_prints_json_pointer_and_exits_one` — the violation is locatable. `test_theme_check_ambiguous_theme_exits_one` — the greyscale invariant is reachable from the CLI. `test_width_flag_overrides_the_document_width` — one document renders at several widths. `test_profile_flag_selects_the_embedding_profile` — `--profile standalone` produces explicit dimensions |
| T16 | The acceptance suite: one test per failure family proving it cannot be expressed | `tests` | M | T11, T12, T13, T14 | `unrepresentable_failure_families == 11` | `test_family_arrow_without_shaft_is_unrepresentable` in `tests/test_failure_families.py`, and one sibling per family — each asserts either that the schema has no field expressing it, or that a layout invariant excludes it, with the family named in the test id |
| T17 | Embedding targets: every fixture rendered in both profiles, embedded in a real Markdown page and a real HTML page, and one converted to PDF, with the safety validator run per profile rather than aggregated | `drawspec.emit`, `tests` | M | T15 | `embedding_safety_violations == 0` | `test_every_fixture_passes_safety_in_both_profiles` in `tests/test_embedding.py` — measured per profile, not summed. `test_two_fixtures_in_one_html_page_have_no_id_or_selector_collision` — the inline promise holds on a shared page. `test_standalone_fixture_converts_to_pdf_without_unresolved_colour` — a converter round-trip produces a document whose ink is the theme's, not a default. `test_greyscale_conversion_preserves_role_distinctions` — every role pair stays distinguishable with colour removed |
| T18 | Acceptance close-out: the three reference documents rendered and committed, a README gallery, and the determinism and zero-dependency checks | `drawspec`, `README.md` | M | T16, T17 | `nondeterministic_reruns == 0` | `test_every_fixture_renders_identically_on_a_second_run` in `tests/test_acceptance.py` — byte-identical reruns across the whole fixture set. `test_package_renders_with_no_system_binaries_available` — import and render succeed with `PATH` emptied of non-Python executables. `test_three_reference_documents_render_without_fit_or_layout_errors` — the brief's second acceptance test passes |

**Status legend**: ☐ not started · ◐ in progress · ☑ merged

**Merge order**: T1, T2, T3, T4 first and in parallel — none depends on another,
and together they are the whole foundation. Then T5 → T6, which unblocks
everything else. Then T7 (the engine decision) on the graph branch while T12,
T13 and T14 proceed independently on the non-graph branches. T8 → T9 → T10 →
T11 completes the graph branch. T15 and T16 gather, T17 proves the output
travels to every target, and T18 closes.

**Branch pattern**: `drawspec-T<N>-description` from the default branch.

## Evidence log

| T# | Gate | Measured | Command | SHA | Env | Date |
|----|------|----------|---------|-----|-----|------|
| T1 | `embedding_safety_violations == 0` | `0` in `inline` and `0` in `standalone`, measured per profile | `uv run pytest tests/test_emit.py -q` (50 passed) | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| T2 | `greyscale_ambiguous_role_pairs == 0` | `0` — all 21 node-role pairs and 10 edge-role pairs differ in a non-colour channel | `uv run pytest tests/test_theme.py -q` (96 passed) | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| T3 | `text_measurement_error_ratio <= 0.02` | `0.0` — exact agreement with an independent `hmtx`/`kern` reader over 9 reference strings × 3 bundled fonts | `uv run pytest tests/test_measure.py -q` (52 passed) | `claude/continuation-yq88jv` | CPython 3.12, Linux, `fonttools` 4.61 | 2026-08-12 |
| T13 | `text_outside_shape_count == 0` | `0` — every label corner inside its own trapezoid and inside its own arc, checked against the outlines rather than bounding boxes | `uv run pytest tests/test_kinds_shape.py -q` (24 passed); `make gallery` | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| T6b | `text_overflow_count == 0`, on the real outlines | `0` — the two reference decision nodes drop from 254x103 and 250x133 to 220x74 and 237x103: 38% and 26% less area, and the first now sets on one line instead of two | `uv run pytest tests/test_box.py -q` (66 passed) | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| D-1 | `text_overflow_count == 0`, and a cycle reads as a cycle | `0` — steps evenly spaced to 1e-6 for 2..8 nodes, every arc running one way, no arc leaving its sector or entering a box | `uv run pytest tests/test_kinds_cycle.py -q` (28 passed); `make gallery` | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| T0 | gallery builds for every reference document | `9` reference documents, one per kind; 3 drawn and 6 correctly listed as unimplemented | `uv run pytest tests/test_gallery.py -q` (13 passed); `make gallery` | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| T12 | `same_rank_size_variance == 0` | `0` — one distinct (width, height) per kind across stack, columns and timeline; ticks evenly spaced to 6 decimals | `uv run pytest tests/test_kinds_grid.py -q` (43 passed) | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| T8 | `node_overlap_count == 0` | `0` — across 5 graph shapes × 2 directions and 100 pseudo-random graphs; deterministic, and stable under a reordered input | `uv run pytest tests/test_layout.py -q` (139 passed) | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| T7 | `candidate_engines_rendered == 2` | `2` — both engines, 0 overlaps and 0 crossings on 3 documents × 2 directions, both deterministic | `uv run pytest tests/test_layout_spike.py -q` (35 passed); `uv run python tools/spike_layout.py` | `claude/continuation-yq88jv` | CPython 3.12, Linux, grandalf 0.8 | 2026-08-12 |
| T6 | `text_overflow_count == 0` | `0` — text inside the padding on all four sides for 4 roles × 5 texts; centring within 0.5 px; one fit factor across all four levels | `uv run pytest tests/test_box.py -q` (62 passed) | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| T5 | `text_overflow_count == 0` | `0` — every line re-measured at or below its width across 5 widths; block height derived from the line count | `uv run pytest tests/test_wrap.py -q` (32 passed) | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |
| T4 | `forbidden_field_acceptance_count == 0` | `0` — all 26 fields in the §5.1 rejection table refused by the parser *and* by the published schema | `uv run pytest tests/test_schema.py -q` (109 passed) | `claude/continuation-yq88jv` | CPython 3.12, Linux | 2026-08-12 |

### Dependency graph

```
T1 (scene + emit) ─────────────────────────────────────┐
T2 (theme) ──────────┬─────────────────────────────────┤
T3 (measure) ────────┴─> T5 (wrap) ─> T6 (box) ──┬─────┤
T4 (schema) ─────────────────────────────────────┤     │
                                                 │     │
                          T7 (engine spike) <────┤     │
                                 │               │     │
                                 v               │     │
                          T8 (layout)            │     │
                                 │               │     │
                                 v               │     │
                          T9 (routing)           │     │
                                 │               │     │
                                 v               │     │
                          T10 (labels)           │     │
                                 │               │     │
                                 v               │     │
                          T11 (flow, tree) <─────┤     │
                          T12 (grid kinds) <─────┤     │
                          D-1 (cycle) <──────────┤     │
                          T13 (shape kinds) <────┤     │
                          T14 (charts) <─────────┘     │
                                 │                     │
                                 ├─> T15 (CLI) ─> T17 (embedding targets)
                                 └─> T16 (acceptance suite)      │
                                          │                      │
                                          └──────┬───────────────┘
                                                 v
                                            T18 (close-out)
```

The critical path is T3 → T5 → T6 → T7 → T8 → T9 → T10 → T11 → T15 → T17 →
T18. Text measurement gates everything, which is why it is Large and first.

---

---

## T7 decision: the default layout engine

**Date**: 2026-08-12 · **Task**: `lo-4c51` · **Gate**: `candidate_engines_rendered == 2`, met.

Both candidates were implemented behind the `LayoutEngine` protocol and run over
the three reference documents in `docs/reference/`, in both flow directions. The
rendered output is committed in `docs/reference/rendered/` — twelve SVGs, one per
document × engine × direction. Regenerate with `uv run python tools/spike_layout.py`.

| Document | Engine | Direction | Overlaps | Crossings | Size | Fits 640 | Deterministic |
|---|---|---|---|---|---|---|---|
| flow-validation | layered | down | 0 | 0 | 539 x 488 | yes | yes |
| flow-validation | layered | right | 0 | 0 | 1237 x 133 | no | yes |
| flow-validation | grandalf | down | 0 | 0 | 672 x 488 | no | yes |
| flow-validation | grandalf | right | 0 | 0 | 1237 x 256 | no | yes |
| cycle-review | layered | down | 0 | 0 | 204 x 280 | yes | yes |
| cycle-review | layered | right | 0 | 0 | 1102 x 37 | no | yes |
| cycle-review | grandalf | down | 0 | 0 | 318 x 280 | yes | yes |
| cycle-review | grandalf | right | 0 | 0 | 1102 x 67 | no | yes |
| tree-decisions | layered | down | 0 | 0 | 1449 x 159 | no | yes |
| tree-decisions | layered | right | 0 | 0 | 666 x 402 | no | yes |
| tree-decisions | grandalf | down | 0 | 0 | 1449 x 159 | no | yes |
| tree-decisions | grandalf | right | 0 | 0 | 666 x 402 | no | yes |

### The decision

**The direct layered implementation (`drawspec.layout.layered.LayeredEngine`) is
the default.** T8 hardens it; it is not rewritten.

The reasoning, in the order the evidence supports it:

1. **Crossing quality did not separate them.** Both produced zero crossings on
   all three documents in both directions. grandalf has the better ordering
   algorithm and it did not matter, because the corpus's median graph has four
   nodes and its largest has seventeen. The argument for a dependency was
   quality; the measurement did not find any to buy.
2. **The layered engine is tighter, and tightness decides whether a diagram
   fits.** grandalf reserves a full column for every dummy vertex on a long
   edge: 672 against 539 on the flow (25% wider), 318 against 204 on the cycle
   (56% wider). At the theme's 640 canvas width that is not cosmetic — the
   seven-node flow *fits* under the layered engine and does *not* under
   grandalf. An engine whose slack turns a valid diagram into a `FitError` is
   the wrong default.
3. **Zero dependencies, which was a success criterion.** `system_dependencies
   == 0` is about binaries, but the same reasoning covers a Python dependency
   that is lightly maintained (v0.8) and dual-licensed GPLv2 / EPL-1.0 — only
   the EPL arm is compatible with shipping MIT code around it. Choosing
   grandalf would mean depending on that arm, and vendoring it later would mean
   carrying EPL notices. Nothing in the measurement pays for that.
4. **Both are deterministic**, so neither wins on the determinism criterion.
   That is not free: `break_cycles` picks its back edges in sorted id order, and
   the barycentre sweeps break ties on id, precisely so the coordinates that end
   up in committed SVG are the same on every run.

### The escape route

`GrandalfEngine` stays in the tree, tested, behind the same protocol. It is not
dead weight — it is the escape route made concrete, and having two working
implementations is the only way to know the seam is real rather than asserted. If
a consumer's graph ever beats the layered engine on crossings, switching is one
constructor call, and grandalf remains an optional `spike` extra rather than a
runtime dependency. A Graphviz (`-Tplain`) or ELK engine would enter the same way.

### What the spike found that was not the question

**No engine can make an eleven-node tree fit a 640 canvas.** `tree-decisions`
overflows in both directions under both engines — 1449 wide going down, 402 tall
and 666 wide going right. This is not an engine defect; it is the style rules
working as intended, and it is the case `FitError` exists for. Two consequences:

- **T8 owes direction selection.** "If the arrows do not fit horizontally, the
  diagram goes vertical" is a real remedy and neither engine chooses for itself.
  The engine takes a direction; something above it has to try both and prefer the
  one that fits. **Delivered in T8 as `layout.best_layout`**, which returns the
  fitting direction, or the narrower attempt with `fits=False` when neither fits —
  because the elastic fit gets a turn before anyone gives up.
- **T11 and T18 will meet real `FitError`s**, and the message is the product.
  Measuring `fit_error_rate` over the fixture set is not optional bookkeeping.

**Edges here are straight lines between box centres**, because routing is T9.
The committed SVGs are for judging where the boxes went and nothing else.

---

## D-1: `cycle` is a parametric template, not a layered graph layout

**Date**: 2026-08-12 · **Task**: `lo-21c8` · Found by looking at
`docs/reference/rendered/cycle-review-layered-down.svg`.

The table above originally grouped `cycle` with `flow` and `tree` in T11, behind
the layout engine and orthogonal routing. That contradicts
`docs/theme-requirements.md` §6, which lists cycles under **Specific shapes**
with pyramids and concentric circles, and says of all three: *"These are
parametric templates, not graph layout."*

What the plan's grouping produced, on the five-node `cycle-review` reference:

```
5 boxes, all at x=24.0, stacked at y = 24.0, 84.8, 145.7, 206.6, 267.4
5 edges, ALL on the vertical line x=126.1
```

A column with one line drawn down it. The back edge retraces the four forward
edges exactly, so the loop is invisible. **T9 cannot repair this** — a layered
cycle routed orthogonally is still a column with a line around the side. The
layout is what is wrong, not the routing.

`cycle` therefore moves to its own task and is rendered like `pyramid` and
`rings`: nodes evenly spaced on a circle, edges following the circumference in
one direction.

**The input contract does not change.** A cycle is still `nodes` and `edges` —
that is what it *means*, and the schema is about meaning. Only the renderer moves,
which is exactly the separation the `Scene` seam exists to allow: a family can
change how it draws without the author's document changing at all. **Its dependencies change with it** — as a parametric template it
needs T1, T4 and T6 only, not T9 or T10, so it is unblocked now, alongside T13.
T11 keeps `flow` and `tree`.

### Consequence for the T7 decision

`cycle-review.json` was one of the three documents in the engine comparison
above. That comparison remains valid as a test of **cycle breaking**, which is a
real engine capability every graph kind needs — but its *render* is not how a
`cycle` document will be drawn, so it should not be read as one. The decision
does not rest on it: the deciding measurement was `flow-validation` at 539,
which fits the 640 canvas, against grandalf's 672, which does not.

## Sign-off

- [ ] Design reviewed by second engineer
- [ ] Contracts agreed with consuming services
- [ ] Migration strategy validated — n/a, no persisted state
- [ ] Ready for execution
