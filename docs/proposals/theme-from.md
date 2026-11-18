# Proposal: `drawspec theme from` — a theme derived from a brand

Status: **implemented** — see *As built* at the end. Size **S** (no layout; one reader, one mapping, one check).

## Why

A project that already has a design system wants its diagrams to look like its site: the
same typeface, the same accent where the diagram points at something. Today that means
reading `docs/theme.md`, finding the five roles the `accent` theme colours, and copying hex
values across by hand — and then finding out at render time that the brand's pale yellow
highlight cannot be seen on a white page.

The brand already exists as data: CSS custom properties (`--color-accent: #0f7b8a`) or a
[W3C design-tokens](https://tr.designtokens.org/format/) JSON file. drawspec can read
either and write the theme, keeping every guarantee the default theme makes.

## What it must not break

A brand is a page's palette; a drawspec SVG is not a page. Three guarantees hold whatever
the brand says (`docs/theme-requirements.md` §3):

1. **The drawing inherits the page.** Strokes and text are `currentColor`; there is no
   background. So a brand's background, surface and text colours are *not* applied — they
   are reported as ignored, with that reason. The one exception is the brand's text colour
   as `[canvas] ink`, which only the `standalone` profile uses (there is no page there).
2. **Colour points, never carries.** Brand colours go only where the `accent` theme puts
   colour — onto roles that already differ from their neighbours by weight, dash or shape —
   and onto `[mark] colours`, whose patterns stay distinct. The loader's greyscale check
   runs on the result.
3. **It survives dark mode.** A pinned colour does not follow the page, so it must read on
   both: at least **3:1** (WCAG's figure for graphics) against a white page *and* against a
   near-black one (`#121212`). A brand colour outside that band is darkened or lightened,
   keeping its hue, until it fits — and the report says so. `--strict` refuses instead.

## The command

```bash
drawspec theme from brand.css                       # TOML on stdout, report on stderr
drawspec theme from brand.css tokens.json -o house.toml --name house
drawspec theme from tokens.json --strict            # refuse rather than adjust
```

Local files only: a URL is a usage error (exit 2), saying to save the stylesheet first.
drawspec makes no network request, here or anywhere.

## What maps onto what

| Brand token (by name) | Theme key |
|---|---|
| `accent`, `primary`, `brand`, `highlight` colour | `stroke` of `[role.emphasis]`, `[role.terminal]`, `[edge_role.strong]`; `[mark] colours[0]` |
| `secondary`, `tertiary` colour | `[mark] colours[1]`, `[2]` |
| `muted`, `subtle`, `neutral` colour | `stroke` of `[role.note]`, `[role.group]`, `[edge_role.link]`; `[mark] colours[3..4]` |
| `text`, `foreground`, `ink` colour | `[canvas] ink` (standalone only), checked at 4.5:1 on white |
| `font` family: `sans`/`body`/`base`, `serif`, `mono`/`code` | `[font] sans`, `serif`, `mono` (a serif body also sets `default = "serif"`) |
| `radius` | `[box] corner_radius`, clamped to 0–12 |
| `border-width`/`stroke-width` | every stroke weight, scaled together so their ratios hold (factor 0.75–1.5) |
| `line-height` (unitless) | `[box] line_height`, clamped to 1.2–1.6 |

Ignored, each with its reason: backgrounds and surfaces; status colours (`success`,
`danger`…: colour would carry meaning); border colours; interaction states (`hover`…);
other shades of a colour already taken; heading/display faces (one family per drawing);
font sizes and weights, spacing, shadows (the type scale is relative to the canvas, not to
CSS pixels; spacing is derived from measured text); dark-mode overrides (inside `@media`
or under a selector other than `:root`/`html`).

## Example

```css
:root {
  --font-sans: "Tidemark Sans", "DejaVu Sans", sans-serif;
  --color-accent: #0f7b8a;
  --color-highlight: #f2c230;       /* too light for a white page: darkened */
  --color-background: #fafaf7;      /* ignored: drawspec draws no background */
  --radius-md: 6px;
}
```

```toml
version = 1
name = "tidemark"

[font]
sans = ["Tidemark Sans", "DejaVu Sans", "sans-serif"]  # --font-sans

[role.emphasis]
stroke = "#0f7b8a"  # --color-accent
…
```

## Refusals

* No file read, or nothing in it maps onto a theme key — exit 1, naming the file.
* A colour that cannot be brought into the band, or any adjustment under `--strict`.
* A result the loader refuses (it should not happen; it is checked anyway).

## As built

* **`drawspec theme from`, not `drawspec theme --from`.** `theme` already takes
  subcommands (`check`), and a flag beside them would make `theme --from x check y` legal.
* **A later file wins a tie** — on names that fit a slot equally well — so a tokens file
  can refine a stylesheet. Within one slot the plainest name wins (`--color-accent` over
  `--color-accent-600`), then, in a numbered scale, a shade that already reads on both
  pages, nearest `600`.
* **The standalone ink is held to 4.5:1 on white**, not 3:1 on both pages: it is a text
  colour, and only the `standalone` profile, which has no page to inherit, draws it.
* **A font the machine does not have is reported, not refused**: the line says which
  family it is measured as until it is installed, as `render` itself warns.
* **A relative `theme` path in a document file is read from the document's folder** when
  the theme is there (`load_document`), and from the working directory otherwise, as
  before. The gallery's three `*-brand-*` documents still name
  `docs/reference/brand/tidemark.toml` from the repository root, because the test suite
  and the MCP server render documents that have no file location.
* The committed `docs/reference/brand/tidemark.toml` is pinned to what the command writes
  from `tidemark.css` by a test, so the sample cannot drift from the tool.
