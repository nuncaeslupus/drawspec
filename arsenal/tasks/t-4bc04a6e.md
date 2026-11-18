---
id: t-4bc04a6e
title: "review: Glyphs outside the bundled font subset are mis-measured; PNG drops them"
priority: 5
requires: [human:gate]
---

Imported from issue #183

**Severity:** high · **Confidence:** high · **Category:** correctness

**Where:** `src/drawspec/text/fontlib.py:199-220, src/drawspec/export.py:120-130, tools/subset_fonts.py:30-40`

### Finding
The bundled DejaVu subsets cover ~1400 code points (no CJK, no emoji). An uncovered character is measured at the .notdef advance (1229/2048 em = 0.6em) with no warning, while a browser draws CJK/emoji at ~1em from a fallback font, so the text overruns the box drawspec sized for it - the exact failure the tool promises to prevent. In PNG export (skip_system_fonts=True) the glyphs are not drawn at all.

### Evidence
Repro: flow with one node of 15 CJK characters -> rect width 123 at font-size 11 (real text ~165 wide). render_png of '数据库' and '服务器' yields byte-identical PNGs (same sha1), i.e. no glyph is drawn; 'abc' vs 'abd' differ. No FontSubstitutionWarning is emitted.

### Suggested direction
Measure uncovered characters by East Asian width (1em for W/F, as textgrid.py already does) or warn/refuse; for PNG, either allow system fallback for uncovered scripts or refuse with a message naming the characters.

_From the full repo review of 2026-11-11 (finding #2). Not fixed yet; verify before acting._

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
