"""Unit tests for sota_sdk.cli — cmd_init, cmd_check, cmd_docker, helpers."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from sota_sdk.cli import _to_class_name, cmd_init, cmd_docker

pytestmark = pytest.mark.unit


class TestToClassName:
    def test_hyphen(self):
        assert _to_class_name("my-agent") == "MyAgentAgent"

    def test_underscore(self):
        assert _to_class_name("my_agent") == "MyAgentAgent"

    def test_single_word(self):
        assert _to_class_name("scraper") == "ScraperAgent"

    def test_mixed(self):
        assert _to_class_name("web-scraper_pro") == "WebScraperProAgent"

    def test_already_capitalized(self):
        assert _to_class_name("MyAgent") == "MyagentAgent"


class TestCmdInit:
    def test_creates_all_files(self, tmp_path):
        args = MagicMock()
        args.name = "test-agent"
        args.tags = ["nlp", "test"]
        args.directory = str(tmp_path / "test-agent")

        cmd_init(args)

        project = tmp_path / "test-agent"
        assert (project / "agent.py").exists()
        assert (project / ".env.example").exists()
        assert (project / "requirements.txt").exists()
        assert (project / "Dockerfile").exists()
        assert (project / ".dockerignore").exists()
        assert (project / "README.md").exists()

    def test_correct_class_name(self, tmp_path):
        args = MagicMock()
        args.name = "my-cool-agent"
        args.tags = ["test"]
        args.directory = str(tmp_path / "my-cool-agent")

        cmd_init(args)

        content = (tmp_path / "my-cool-agent" / "agent.py").read_text()
        assert "MyCoolAgentAgent" in content

    def test_tags_in_output(self, tmp_path):
        args = MagicMock()
        args.name = "tagged"
        args.tags = ["nlp", "web"]
        args.directory = str(tmp_path / "tagged")

        cmd_init(args)

        content = (tmp_path / "tagged" / "agent.py").read_text()
        assert '"nlp"' in content
        assert '"web"' in content

    def test_fails_on_non_empty_dir(self, tmp_path):
        existing = tmp_path / "existing"
        existing.mkdir()
        (existing / "something.txt").write_text("x")

        args = MagicMock()
        args.name = "existing"
        args.tags = []
        args.directory = str(existing)

        with pytest.raises(SystemExit):
            cmd_init(args)


class TestCmdDocker:
    def test_creates_files(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        args = MagicMock()
        args.force = False

        cmd_docker(args)

        assert (tmp_path / "Dockerfile").exists()
        assert (tmp_path / ".dockerignore").exists()

    def test_force_overwrites(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "Dockerfile").write_text("old")

        args = MagicMock()
        args.force = True

        cmd_docker(args)

        content = (tmp_path / "Dockerfile").read_text()
        assert "old" not in content


class TestCmdCheck:
    def test_prints_pass(self, capsys, tmp_path, monkeypatch):
        # Create a minimal agent file
        agent_file = tmp_path / "agent.py"
        agent_file.write_text('''
from sota_sdk import SOTAAgent, Job
class TestAgent(SOTAAgent):
    name = "test"
    tags = ["test"]
    description = "A test"
    async def execute(self, job: Job) -> dict:
        return {"success": True}
''')
        args = MagicMock()
        args.agent_file = str(agent_file)
        args.skip_rpc = True

        with patch("sota_sdk.config.SOTA_MARKETPLACE_URL", "ws://localhost:3002/ws/agent"):
            with patch("sota_sdk.config.SOTA_AGENT_PRIVATE_KEY", None):
                from sota_sdk.cli import cmd_check
                cmd_check(args)

        captured = capsys.readouterr()
        assert "passed" in captured.out.lower()


class TestFindAgentFile:
    def test_prefers_agent_py(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "agent.py").write_text("# agent")
        (tmp_path / "main.py").write_text("# main")

        from sota_sdk.cli import _find_agent_file
        result = _find_agent_file()
        assert result == "agent.py"

    def test_falls_back_to_main(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "main.py").write_text("# main")

        from sota_sdk.cli import _find_agent_file
        result = _find_agent_file()
        assert result == "main.py"

    def test_exits_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        from sota_sdk.cli import _find_agent_file
        with pytest.raises(SystemExit):
            _find_agent_file()
