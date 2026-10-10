# Proposal: image exports — PNG next to SVG

Status: **implemented** — see *As built* at the end. Size **S** (no layout; one renderer
behind an optional extra, one CLI flag set).

## Why

The SVG is the product: it scales, inherits the page's ink and diffs in review. But a lot
of the places a diagram is wanted take only a picture file — a chat message, a slide, an
issue attachment, a word processor. Today a user has to find a converter, and a converter
that sets the text in a different font draws a label wider than the box it was measured
into, which is the one overflow drawspec exists to prevent.

## Owner requirements

* Every drawing as SVG (exists) **and** as PNG or similar that can be attached anywhere.
* As few dependencies as possible: the core install stays `fonttools` only.
* No PDF. No JPEG (lossy compression smears line art). WebP only if it adds no dependency.

## Design

**One optional extra, `drawspec[png]`, holding `resvg-py`.** resvg is a complete SVG
renderer written in Rust; `resvg-py` ships it compiled into a single abi3 wheel for Linux
(glibc and musl), macOS and Windows on every common architecture, with no Cairo, no
system libraries and no browser. Alternatives considered:

| Option | Why not |
|---|---|
| `cairosvg` | needs the system Cairo library — exactly the "apt-get in CI" drawspec refuses |
| Playwright / headless Chromium | a 150 MB browser download for a picture |
| `svglib` + `reportlab` | two dependencies, Pillow among them, and weak text rendering |
| Pillow (for WebP) | a second, larger dependency for a format PNG already covers |

**Rasterise the `standalone` profile.** Inline SVG draws in `currentColor`, which means "the
page's ink" and has no meaning in a picture file; standalone resolves it to the theme's
`[canvas] ink`.

**Three backgrounds, not a colour.** `light` (theme ink on white, the default), `dark`
(ink `#e8e8e8` on `#121212`) and `transparent` (theme ink, no page). `#121212` is the dark
page `drawspec theme from` checks every brand colour against, so accents read on it.

**A scale, default 2.** Pixels per SVG unit; 2 keeps a 640-wide drawing crisp on a
high-density screen. Capped at 8 so a typo cannot allocate gigabytes.

**The fonts the layout was measured with.** The renderer ignores system fonts and is handed
the bundled DejaVu files plus whatever file each theme font role resolved to when measured.
With the bundled fonts the PNG is byte-identical on every machine.

**Surfaces.** CLI: `render --format png`, inferred from `-o *.png`, with `--scale` and
`--background`. Python: `drawspec.render_png(...) -> bytes`. MCP: `render` takes
`format: "png"` and returns a base64 image block.

## As built

Built as designed, with these details settled in the building:

* **WebP is omitted.** `resvg-py` encodes PNG only; WebP would need Pillow (or another
  encoder), which is the extra dependency the owner ruled out. PNG is accepted everywhere
  WebP is, so nothing is lost but a few kilobytes.
* **`resvg-py>=0.5`.** 0.5 is the release whose `svg_to_bytes` returns `bytes` and takes
  `font_files` / `skip_system_fonts`, which the font guarantee depends on. It ships type
  stubs, so strict mypy needs no override.
* **The format is inferred from `-o`** for `.png`, `.svg` and `.txt` (the `files` text
  form), because the extension already says what the file is. An explicit `--format` that
  contradicts the extension, or `--scale`/`--background` with a non-PNG format, is a usage
  error (exit 2) rather than silently ignored. A PNG is not written to a terminal.
* **`--profile` does not apply to PNG**: the standalone profile is always used, for the
  reason above, and the help says so.
* **A missing extra is `ExportError`** (a `DrawspecError`), so the CLI refuses with exit 1
  and the message `pip install 'drawspec[png]'`, and the MCP server returns it as a
  refusal like any other. An out-of-range `scale` or unknown `background` from Python is a
  `ValueError`, matching `emit`'s handling of an unknown profile.
* **Pixel size** is the standalone canvas rounded to whole units, times the scale: resvg
  rounds the SVG size before zooming, so a 666.5 × 148.4 canvas is 1334 × 296 at scale 2.
* **CI** installs every extra, so the export tests run; a second step re-syncs without
  `png` and re-runs the export, CLI and MCP tests, proving they skip cleanly and the
  refusal names the install line.
