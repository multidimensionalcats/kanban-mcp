# HANDOVER

## Last Session (2026-02-25)

### Completed

**`kanban-setup` console script (#7538)** — Cross-platform Python DB setup replacing shell scripts as the primary install path for pip users:
- Created `kanban_mcp/setup.py` — interactive mode (prompts) and `--auto` mode (env vars / CLI args / defaults)
- Connects as MySQL root, creates DB + user + grants, runs all migrations via `cursor.execute(sql, multi=True)`, writes `.env`, prints MCP config JSON
- CLI args: `--auto`, `--with-semantic`, `--db-name`, `--db-user`, `--db-password`, `--db-host`, `--mysql-root-user`, `--mysql-root-password`
- Added `kanban-setup` entry point in `pyproject.toml`
- Created `tests/test_setup.py` — 17 unit tests (arg parsing, password gen, migration discovery, .env writing, config resolution)
- Updated README.md: Quick Start, Database Setup, AI Agent Install Guide, Entry Points table all use `kanban-setup` as canonical path. Shell scripts demoted to "Alternative: from source" section.
- `install.sh` / `install.ps1` kept in repo for source installs

**parent_id epic-only bug fix (planned)** — Plan written at `.claude/plans/peaceful-swimming-spindle.md`. `set_parent()` already enforces epic-only parents but `create_item()` does not. One-line fix + test update. **Execute this plan before doing anything else next session.**

### Decisions Made This Session
- **Run tests under python3.13**, not 3.14. Live deployment uses 3.13, onnxruntime is installed there. 3.14 lacks onnxruntime ebuild on Gentoo. All 405 tests pass with 0 skips under 3.13.
- **No venv needed** — project runs against system python. The `.venv/` directory in the repo is vestigial and can be deleted.
- **`--break-system-packages` was used incorrectly** — an editable install was put into `~/.local/lib/python3.14/`. Should be cleaned up (`pip3.14 uninstall kanban-mcp`).
- **Shell scripts stay** — `install.sh` and `install.ps1` remain for from-source users but are no longer the primary path.

### Environment State (messy, needs cleanup)
- **Live deployment**: `~/kanban_mcp/` — old flat-file layout, runs under python3.13, has onnxruntime. MCP server processes are running from here.
- **Dev tree**: `./kanban_mcp/` — the packaged version. Editable-installed into python3.14 system site-packages via `--break-system-packages`.
- **System python3.14**: has kanban-mcp editable install in `~/.local/lib/python3.14/`. Missing onnxruntime.
- **System python3.13**: has onnxruntime. Tests should run under this.
- **`.venv/`**: exists but empty/unused. Should be deleted.

### Current Branch State
- `rebase-clean` — 7 clean commits + uncommitted work from this session
- `master` — old 41-commit history (will be replaced)
- `backup-pre-rebase` — safety copy of old master

### Test Results
- 405 passed, 0 skipped under python3.13 (`python3.13 -m pytest tests/ -v`)

## Next Session

### Primary: PyPI publish and v0.1.0 tag

Presuming parent_id fix is already committed:

1. **Final pre-publish checks**:
   - `python3.13 -m pytest tests/` — all 405+ tests pass
   - `python3.13 -m build` — produces dist/
   - Verify README renders correctly on PyPI (use `twine check dist/*`)

2. **Publish to PyPI**:
   - `pip install build twine`
   - `python3.13 -m build`
   - `twine upload dist/*` (user has PyPI account created)

3. **Replace master with rebase-clean**:
   - Tag `v0.1.0` on rebase-clean
   - Force-push to main/master

4. **Clean up dev environment** (optional):
   - `pip3.14 uninstall kanban-mcp` to remove the --break-system-packages mess
   - Delete `.venv/`

### Blocked: Docker testing (#7535)
User is recompiling Gentoo kernel with Docker-required CONFIG options. Docker compose setup exists but is untested.

### Remaining open-source epic (#7532) children:
- #7535 Docker and docker-compose setup (blocked on kernel recompile)
- #7538 Manual install documentation (in_progress — kanban-setup done, README updated)
