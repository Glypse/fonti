import json
import tempfile
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from main import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def temp_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


@pytest.fixture
def mock_config_file(temp_dir: Path) -> Path:
    config_file = temp_dir / ".fontpm" / "config"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    return config_file


@pytest.fixture
def mock_installed_file(temp_dir: Path) -> Path:
    installed_file = temp_dir / ".fontpm" / "installed.json"
    installed_file.parent.mkdir(parents=True, exist_ok=True)
    return installed_file


class TestConfig:
    def test_config_format_valid(
        self, runner: CliRunner, mock_config_file: Path
    ) -> None:
        with patch("main.config_file", mock_config_file):
            result = runner.invoke(app, ["config", "format", "variable-ttf,otf"])
            assert result.exit_code == 0
            assert "Set default format to: variable-ttf,otf" in result.output

    def test_config_path_valid(self, runner: CliRunner, mock_config_file: Path) -> None:
        with patch("main.config_file", mock_config_file):
            result = runner.invoke(app, ["config", "path", "/some/path"])
            assert result.exit_code == 0
            assert "Set default path to: /some/path" in result.output

    def test_config_invalid_key(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["config", "invalid", "value"])
        assert result.exit_code == 1
        assert "Unknown config key: invalid" in result.output


class TestIsVariable:
    @patch("main.is_variable_font")
    def test_is_variable_true(self, mock_is_var: MagicMock, runner: CliRunner) -> None:
        mock_is_var.return_value = True
        result = runner.invoke(app, ["is-variable", "/path/to/font.ttf"])
        assert result.exit_code == 0
        assert "This is a variable font." in result.output

    @patch("main.is_variable_font")
    def test_is_variable_false(self, mock_is_var: MagicMock, runner: CliRunner) -> None:
        mock_is_var.return_value = False
        result = runner.invoke(app, ["is-variable", "/path/to/font.ttf"])
        assert result.exit_code == 0
        assert "This is a static font." in result.output

    @patch("main.is_variable_font")
    def test_is_variable_error(self, mock_is_var: MagicMock, runner: CliRunner) -> None:
        mock_is_var.side_effect = Exception("Error")
        result = runner.invoke(app, ["is-variable", "/path/to/font.ttf"])
        assert result.exit_code == 1
        assert "Error checking font: Error" in result.output


class TestExport:
    def test_export_no_installed_file(
        self, runner: CliRunner, mock_installed_file: Path
    ) -> None:
        with patch("main.Path.home") as mock_home:
            mock_home.return_value = mock_installed_file.parent.parent
            result = runner.invoke(app, ["export"])
            assert result.exit_code == 0
            assert "No installed fonts data found." in result.output

    def test_export_stdout(self, runner: CliRunner, mock_installed_file: Path) -> None:
        installed_data = {
            "repo1": {
                "font1.ttf": {"filename": "font1.ttf", "type": "ttf", "version": "1.0"}
            }
        }
        mock_installed_file.write_text(json.dumps(installed_data))
        with patch("main.Path.home") as mock_home:
            mock_home.return_value = mock_installed_file.parent.parent
            result = runner.invoke(app, ["export", "--stdout"])
            assert result.exit_code == 0
            assert "font1.ttf" in result.output

    def test_export_to_file(
        self, runner: CliRunner, mock_installed_file: Path, temp_dir: Path
    ) -> None:
        installed_data = {
            "repo1": {
                "font1.ttf": {"filename": "font1.ttf", "type": "ttf", "version": "1.0"}
            }
        }
        mock_installed_file.write_text(json.dumps(installed_data))
        output_file = temp_dir / "export.json"
        with patch("main.Path.home") as mock_home:
            mock_home.return_value = mock_installed_file.parent.parent
            result = runner.invoke(app, ["export", "--output", str(output_file)])
            assert result.exit_code == 0
            assert output_file.exists()
            data = json.loads(output_file.read_text())
            assert "repo1" in data


class TestImport:
    def test_import_invalid_file(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["import", "--input", "nonexistent.json"])
        assert result.exit_code == 1
        assert "Error loading nonexistent.json" in result.output

    @patch("main.install_single_repo")
    def test_import_valid(
        self, mock_install: MagicMock, runner: CliRunner, temp_dir: Path
    ) -> None:
        exported_data = {
            "owner/repo": {
                "font1.ttf": {"filename": "font1.ttf", "type": "ttf", "version": "1.0"}
            }
        }
        import_file = temp_dir / "import.json"
        import_file.write_text(json.dumps(exported_data))
        result = runner.invoke(app, ["import", "--input", str(import_file)])
        assert result.exit_code == 0
        mock_install.assert_called_once()


class TestUninstall:
    def test_uninstall_no_installed_file(
        self, runner: CliRunner, mock_installed_file: Path
    ) -> None:
        with patch("main.Path.home") as mock_home:
            mock_home.return_value = mock_installed_file.parent.parent
            result = runner.invoke(app, ["uninstall", "repo1"])
            assert result.exit_code == 0
            assert "No installed fonts data found." in result.output

    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_bytes")
    def test_uninstall_success(
        self,
        mock_read_bytes: MagicMock,
        mock_exists: MagicMock,
        mock_unlink: MagicMock,
        runner: CliRunner,
        mock_installed_file: Path,
    ) -> None:
        mock_exists.return_value = True
        mock_read_bytes.return_value = b"dummy data"
        installed_data = {
            "repo1": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash",
                    "type": "ttf",
                    "version": "1.0",
                }
            }
        }
        mock_installed_file.write_text(json.dumps(installed_data))
        with (
            patch("main.Path.home") as mock_home,
            patch("main.default_path", Path("/fake/path")),
            patch("hashlib.sha256") as mock_hash,
        ):
            mock_home.return_value = mock_installed_file.parent.parent
            mock_hash.return_value.hexdigest.return_value = "hash"
            result = runner.invoke(app, ["uninstall", "repo1"])
            assert result.exit_code == 0
            assert "Deleted font1.ttf" in result.output
            mock_unlink.assert_called_once()


class TestUpdate:
    def test_update_no_installed_file(
        self, runner: CliRunner, mock_installed_file: Path
    ) -> None:
        with patch("main.Path.home") as mock_home:
            mock_home.return_value = mock_installed_file.parent.parent
            result = runner.invoke(app, ["update"])
            assert result.exit_code == 0
            assert "No installed fonts data found." in result.output

    @patch("httpx.get")
    @patch("main.install_single_repo")
    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.exists")
    def test_update_success(
        self,
        mock_exists: MagicMock,
        mock_unlink: MagicMock,
        mock_install: MagicMock,
        mock_get: MagicMock,
        runner: CliRunner,
        mock_installed_file: Path,
    ) -> None:
        mock_exists.return_value = True
        installed_data = {
            "owner/repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash",
                    "type": "ttf",
                    "version": "1.0",
                }
            }
        }
        mock_installed_file.write_text(json.dumps(installed_data))
        mock_response = MagicMock()
        mock_response.json.return_value = {"tag_name": "v2.0"}
        mock_get.return_value = mock_response
        with (
            patch("main.Path.home") as mock_home,
            patch("main.default_path", Path("/fake/path")),
            patch("packaging.version.Version") as mock_version,
        ):
            mock_home.return_value = mock_installed_file.parent.parent
            mock_version.return_value = MagicMock(__gt__=lambda self, other: True)  # type: ignore
            result = runner.invoke(app, ["update", "owner/repo"])
            assert result.exit_code == 0
            mock_install.assert_called_once()


class TestInstall:
    @patch("main.install_single_repo")
    def test_install_valid_repo(
        self, mock_install: MagicMock, runner: CliRunner
    ) -> None:
        result = runner.invoke(app, ["install", "owner/repo"])
        assert result.exit_code == 0
        mock_install.assert_called_once_with(
            "owner",
            "repo",
            "latest",
            ["variable-ttf", "otf", "static-ttf"],
            Path("/Users/sacha/Library/Fonts"),
            False,
            False,
            False,
        )

    def test_install_invalid_repo_format(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["install", "invalidrepo"])
        assert result.exit_code == 0
        assert "Invalid repo format: invalidrepo" in result.output

    def test_install_invalid_format(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["install", "owner/repo", "--format", "invalid"])
        assert result.exit_code == 1
        assert "Invalid --format value" in result.output
