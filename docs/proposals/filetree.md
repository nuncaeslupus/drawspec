# Proposal: `files` — a file/folder tree kind

Status: **implemented** (see `docs/format.md` → `files`, and `docs/theme.md` → `[files]`).
This page keeps the prior-art survey and the decisions behind it.

## Prior art surveyed

| Tool | What it taught |
|---|---|
| Unix `tree` | `├── └── │` guides; `--dirsfirst`; `--charset=ascii`; `name -> target` for symlinks |
| `eza --tree`, `lsd --tree` | per-type icons; natural sort; dotfiles as ordinary names |
| Starlight / Nextra `<FileTree>` | trailing `/` marks a directory, `…` placeholder row, a comment per row |
| VS Code / GitHub file view | folders first, case-insensitive natural sort |
| PlantUML `salt`, ASCII tree generators | indentation-based input is easy to write and easy to get wrong |

## Decisions

| Question | Decision |
|---|---|
| Input | Flat `path` per entry; intermediate folders inferred. No nesting to get wrong. |
| File vs folder | Has children or ends in `/` → folder. An empty folder must end in `/`. |
| "More files" | A last segment of `...` (or `…`); its `note` becomes the row's label. Always last among siblings. |
| Symlink | `link: "<target>"` → link picture + `→ target`. Never followed; has no children. |
| Order | `sort`: `given` (default), `name` (natural, case-insensitive), `folders-first`. |
| Diff state | `status`: `added` / `changed` / `removed` → pill with `+ ~ -` and the word; `removed` is struck through. |
| Notes | `note` after the name, in one aligned column. |
| Root | `root` optional; without it, top-level entries have no branches. |
| Look | `style`: `icons` (default), `plain`, `unicode`, `ascii`. Text also via `render --format text`. |
| Folder fill, type pictures, colour | Theme `[files]`: `tint`, `types`, `colours`. Default theme monochrome; `accent` colours folders and type families. |
| Type badges (extension text on the page) | Rejected: at 16 units wide, three letters need type below the theme's 9-point legible minimum. Replaced by five stroke-drawn pictograms (code `</>`, data `{}`, text lines, image, archive); the name beside the picture already spells the extension. |
| Refused | Absolute paths, empty / `.` / `..` segments, a path written twice, a file or link used as a folder, `...` mid-path. |
