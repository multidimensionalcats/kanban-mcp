# Changelog

## v0.2.0

### Breaking Changes
- Default database backend changed from MySQL to SQLite
- `install.sh --auto` now sets up SQLite (use `--auto --mysql` for MySQL)
- `install.ps1 -Auto` now sets up SQLite (use `-Auto -MySQL` for MySQL)

### Added
- SQLite backend — zero-config default, no database server required
- Pluggable database backend abstraction (`DatabaseBackend` base class)
- `--mysql` flag for install.sh / `-MySQL` switch for install.ps1
- `[mysql]` extra for MySQL connector dependency
- `[full]` extra combining `[mysql]` and `[semantic]`
- `KANBAN_BACKEND` env var to force backend selection
- `KANBAN_SQLITE_PATH` env var to customize SQLite database location
- Functional test infrastructure (Docker-based, 4 scenarios)
- `install-linux-mysql` CI job for MySQL install path

### Fixed
- web.py: 8 raw SQL queries now use `db._sql()` for cross-backend
  placeholder translation
- SQLite schema: datetime columns use TIMESTAMP type for proper parsing
- SQLite schema: ON DELETE CASCADE on items/updates foreign keys
- Python 3.12+ deprecation warning for sqlite3 timestamp converter

### Changed
- Install scripts default to SQLite (MySQL opt-in via flag)
- CI install jobs use SQLite by default
- macOS CI no longer requires Homebrew MySQL
