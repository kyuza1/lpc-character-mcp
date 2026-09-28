# Changelog

## 0.4.0 — 2026-09-28
### Added
- Messages in English by default; Portuguese with `LPC_LANG=pt` (warnings, errors,
  animation report, credits, command line and web demo).
- Official MCP Registry listing (`io.github.kyuza1/lpc-character-mcp`), published
  automatically on each release.
- MCP Bundle (`lpc-character-mcp.mcpb`) attached to each release: one-click install in
  Claude Desktop, with output folder and language options.
- `glama.json` for the Glama directory.

### Changed
- Tool descriptions and server instructions in English; the assistant replies in the
  user's language.

## 0.3.0 — 2026-09-28
### Added
- `output_dir` in `generate_character` and `generate_batch`: save straight into a game
  project. Godot export detects `project.godot` and writes the correct `res://` path.
- Unity export now includes an `AnimatorController` with one state per animation
  (starts at `idle_down`) and `.anim.meta` files with stable GUIDs.
- `clear_cache` tool and `--clear-cache [days]` command.
- `animation_check.body_missing`: animations the LPC body itself lacks (muscular,
  child, pregnant).
- Tests for the command line, `update_definitions` and batch errors; `ruff` in CI.

### Changed
- `missing` and the web demo use the same rules as `animation_check` (no warnings for
  weapons/tools or intentional gaps such as a beard while climbing).
- The assistant is instructed to ask before using `prefer_complete`.
- Random characters always get a torso item (fallback parts for bodies without shirts).
- Code split into `catalog`, `render`, `links` and `server` modules.
- English README; Portuguese moved to `README.pt-BR.md`.

### Fixed
- Body and head are never suggested as replacements.

## 0.2.0 — 2026-09-28
### Added
- Python package with the `lpc-character-mcp` command (`--setup`, `--where`,
  `--version`, `--help`); one-line install with `uvx`.
- Data and cache live in the user data folder; characters in `~/lpc-characters`
  (`LPC_DATA_DIR` / `LPC_OUTPUT_DIR` override).
- `animation_check` in every result, `prefer_complete`, complete items first in
  `search_items`, complete-only random characters.
- PyPI publishing workflow (trusted publishing) and package smoke test in CI.

### Fixed
- Facial expressions (`head/faces/${head}/...`) were never rendered.

## 0.1.0 — 2026-09-28
First version: MCP tools to search items and generate LPC spritesheets (site layout,
oversized weapon animations, multi-color items, masks, credits), animated preview,
random characters and batches, site links (including legacy aliases), and exports for
Godot 4, Unity 6, the web (Phaser/PixiJS) and the generator site.
