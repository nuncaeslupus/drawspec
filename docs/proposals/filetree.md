# Proposal: `files` — a file/folder tree kind

Status: draft, awaiting decisions (see *Open questions*). Mockups: `filetree-mock-*.svg`.

## Prior art surveyed

| Tool | What it teaches |
|---|---|
| Unix `tree` | `├── └── │` guides; `--dirsfirst`; `--charset=ascii`; `name -> target` for symlinks; summary line "3 directories, 5 files" |
| `eza --tree`, `lsd --tree` | per-type icons (Nerd Font glyphs); natural sort; dotfiles as ordinary names |
| Starlight `<FileTree>` / Nextra `<FileTree>` | docs-oriented: trailing `/` marks a directory, `…` placeholder row, **highlight** a name, trailing comment per row |
| VS Code / GitHub file view | folders first, case-insensitive natural sort; *compact folders* (`src/main/java` on one row) |
| PlantUML `salt` tree, tree.nathanfriend.io | indentation-based text input is easy to write and easy to get wrong |

## Proposed spec (sketch)

```json
{ "version": 1, "kind": "files",
  "root": "my-app",
  "entries": [
    {"path": "src/components/Button.tsx"},
    {"path": "src/components/", "more": 12},
    {"path": "src/index.ts", "note": "entry point"},
    {"path": "src/utils", "link": "../shared/utils"},
    {"path": "tests/index.test.ts", "status": "added"},
    {"path": "dist/", "note": "empty, git-ignored"},
    {"path": "package.json", "status": "changed"}
  ] }
```

Flat paths instead of nested JSON: no indentation or nesting depth to get wrong,
intermediate folders are inferred. That matches the project rule "nothing the
author can misplace".

## Edge cases → rule

| Case | Rule |
|---|---|
| File vs folder | Has children or trailing `/` → folder. Empty folder **must** end in `/`. |
| Same path twice | Error. |
| Path used as file *and* folder (`a` and `a/b`) | Error. |
| "More files" | `more: N` on a folder → a muted `… N more files` row last in it; `more: true` → `…` with no count. |
| Symlink | `link: "<target>"` → link glyph + `→ target`. Never followed or validated. Link to folder has no children. |
| Order | Default: as written (author's meaning). `sort: "name"` (natural, case-insensitive) or `"folders-first"`. |
| Dotfiles, spaces, unicode | Plain names; no special handling. Names containing `/` impossible by construction. |
| Highlight / diff state | `status: added \| changed \| removed \| highlight` → pill with `+ ~ −` symbol text, never colour alone; `removed` also struck through. |
| Annotation | `note` → muted italic after the name, notes aligned into one column. |
| Single-child folder chains | Optional `compact: true` → `src/main/java/` on one row. Off by default. |
| Several roots / no root | `root` optional; omitted → forest with no top row. |
| Long trees | Width/height from content; a size budget refuses rather than shrinking text. |
| Icons | Small monochrome set: folder, file, link, more (+ type badge in style B). No brand/Nerd-Font icons. |
| ASCII | `style: "ascii"` → box-drawing text in SVG; `charset: "ascii"` → `|-- \`--`. Also exportable as plain text (for code blocks). |
