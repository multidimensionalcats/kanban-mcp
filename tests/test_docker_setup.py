#!/usr/bin/env python3
"""Tests for Docker setup files (Dockerfile, docker-compose.yml, deploy.sh)."""

import unittest
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent


class TestDockerfile(unittest.TestCase):
    """Validate Dockerfile structure."""

    def setUp(self):
        self.content = (ROOT / "Dockerfile").read_text()

    def test_base_image(self):
        assert "python:3.13-slim" in self.content

    def test_copies_package(self):
        assert "kanban_mcp/" in self.content, "Should COPY kanban_mcp/ package"

    def test_copies_pyproject(self):
        assert "pyproject.toml" in self.content, "Should COPY pyproject.toml"

    def test_pip_installs_package(self):
        assert "pip install" in self.content

    def test_exposes_port_5000(self):
        assert "EXPOSE 5000" in self.content

    def test_cmd_runs_web_ui(self):
        assert "kanban-web" in self.content
        assert "0.0.0.0" in self.content


class TestDockerCompose(unittest.TestCase):
    """Validate docker-compose.yml structure."""

    def setUp(self):
        with open(ROOT / "docker-compose.yml") as f:
            self.config = yaml.safe_load(f)

    def test_has_db_and_web_services(self):
        assert "db" in self.config["services"]
        assert "web" in self.config["services"]

    def test_db_image_is_mysql8(self):
        assert self.config["services"]["db"]["image"] == "mysql:8.0"

    def test_db_port_mapping(self):
        assert "3306:3306" in self.config["services"]["db"]["ports"]

    def test_db_environment(self):
        env = self.config["services"]["db"]["environment"]
        assert env["MYSQL_DATABASE"] == "kanban"
        assert env["MYSQL_USER"] == "kanban"
        assert "MYSQL_PASSWORD" in env
        assert "MYSQL_ROOT_PASSWORD" in env

    def test_db_mounts_migrations(self):
        volumes = self.config["services"]["db"]["volumes"]
        migration_mount = [v for v in volumes if "migrations" in v and "initdb" in v]
        assert len(migration_mount) == 1, "Should mount migrations to docker-entrypoint-initdb.d"

    def test_db_has_persistent_volume(self):
        volumes = self.config["services"]["db"]["volumes"]
        data_mount = [v for v in volumes if "kanban_data" in v]
        assert len(data_mount) == 1, "Should have persistent data volume"
        assert "kanban_data" in self.config.get("volumes", {})

    def test_db_healthcheck(self):
        hc = self.config["services"]["db"]["healthcheck"]
        assert "mysqladmin" in hc["test"]

    def test_web_port_mapping(self):
        assert "5000:5000" in self.config["services"]["web"]["ports"]

    def test_web_overrides_db_host(self):
        env = self.config["services"]["web"]["environment"]
        assert env["KANBAN_DB_HOST"] == "db", "Web container should connect to 'db' service, not localhost"

    def test_web_depends_on_db_healthy(self):
        depends = self.config["services"]["web"]["depends_on"]
        assert depends["db"]["condition"] == "service_healthy"

    def test_web_builds_from_dockerfile(self):
        assert self.config["services"]["web"]["build"] == "."


class TestDockerignore(unittest.TestCase):
    """Validate .dockerignore contents."""

    def setUp(self):
        self.content = (ROOT / ".dockerignore").read_text()

    def test_excludes_unnecessary_dirs(self):
        for entry in ["node_modules/", "__pycache__/", ".git/", "tests/", "models/"]:
            assert entry in self.content, f"Should exclude {entry}"

    def test_excludes_env_file(self):
        assert ".env" in self.content

    def test_excludes_markdown(self):
        assert "*.md" in self.content


class TestDeployScript(unittest.TestCase):
    """Validate deploy.sh structure."""

    def setUp(self):
        self.content = (ROOT / "deploy.sh").read_text()

    def test_is_bash_script(self):
        assert self.content.startswith("#!/bin/bash")

    def test_rsyncs_docker_files(self):
        assert "Dockerfile" in self.content
        assert "docker-compose.yml" in self.content
        assert ".dockerignore" in self.content

    def test_docker_compose_instructions(self):
        assert "docker compose" in self.content

    def test_no_auto_configure_jq_for_mcp_clients(self):
        """Old auto-configure jq logic for MCP clients should be removed."""
        # The old pattern was: jq ... '.mcpServers.kanban = ...' "$CLAUDE_DESKTOP_CONFIG" > "$tmp"
        # Hooks still use jq (that's fine), but MCP client config should just print snippets
        lines = self.content.split("\n")
        for i, line in enumerate(lines):
            if "mcpServers" in line and "jq" in line:
                self.fail(f"Line {i+1}: Found jq auto-configure for mcpServers — should print snippets instead")

    def test_prints_claude_desktop_snippet(self):
        assert "Claude Desktop" in self.content

    def test_prints_claude_code_snippet(self):
        assert "Claude Code" in self.content

    def test_prints_gemini_snippet(self):
        assert "Gemini CLI" in self.content

    def test_prints_vscode_snippet(self):
        assert "VS Code" in self.content
        assert '"servers"' in self.content, "VS Code uses 'servers' key, not 'mcpServers'"

    def test_prints_codex_snippet(self):
        assert "Codex CLI" in self.content
        assert "mcp_servers.kanban" in self.content, "Codex uses TOML format"

    def test_prints_lmstudio_snippet(self):
        assert "LM Studio" in self.content

    def test_prints_cherry_studio_snippet(self):
        assert "Cherry Studio" in self.content

    def test_client_detection(self):
        """Each client snippet should be gated behind detection."""
        # Check that we detect installed clients rather than always printing
        assert "command -v claude" in self.content or ".claude.json" in self.content
        assert "command -v gemini" in self.content or ".gemini" in self.content
        assert "command -v code" in self.content

    def test_quick_start_instructions(self):
        assert "Quick start" in self.content
        assert "docker compose up -d" in self.content
        assert "localhost:5000" in self.content


if __name__ == "__main__":
    unittest.main()
