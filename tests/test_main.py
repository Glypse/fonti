import json
import tempfile
from pathlib import Path
from typing import Iterator, List, Tuple, cast
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from main import DEFAULT_PATH, DEFAULT_PRIORITIES, Asset, app, load_config


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


@pytest.fixture(autouse=True)
def mock_installed_file_path(temp_dir: Path) -> Iterator[None]:
    with patch("main.INSTALLED_FILE", temp_dir / ".fontpm" / "installed.json"):
        yield


class TestConfig:
    def test_config_format_valid(
        self, runner: CliRunner, mock_config_file: Path
    ) -> None:
        with patch("main.CONFIG_FILE", mock_config_file):
            result = runner.invoke(app, ["config", "format", "variable-ttf,otf"])
            assert result.exit_code == 0
            assert "Set format to: variable-ttf,otf" in result.output

    def test_config_path_valid(self, runner: CliRunner, mock_config_file: Path) -> None:
        with patch("main.CONFIG_FILE", mock_config_file):
            result = runner.invoke(app, ["config", "path", "/some/path"])
            assert result.exit_code == 0
            assert "Set path to: /some/path" in result.output

    def test_config_cache_size_valid(
        self, runner: CliRunner, mock_config_file: Path
    ) -> None:
        with patch("main.CONFIG_FILE", mock_config_file):
            result = runner.invoke(app, ["config", "cache-size", "100000000"])
            assert result.exit_code == 0
            assert "Set cache-size to: 100000000" in result.output

    def test_config_cache_size_invalid(
        self, runner: CliRunner, mock_config_file: Path
    ) -> None:
        with patch("main.CONFIG_FILE", mock_config_file):
            result = runner.invoke(app, ["config", "cache-size", "invalid"])
            assert result.exit_code == 1
            assert "Invalid cache size: must be integer" in result.output


class TestConfigLoading:
    def test_load_config_no_file(self, temp_dir: Path) -> None:
        with patch("main.CONFIG_FILE", temp_dir / "nonexistent"):
            priorities, path, cache_size = load_config()
            assert priorities == DEFAULT_PRIORITIES
            assert path == DEFAULT_PATH
            assert cache_size == 200 * 1024 * 1024

    def test_load_config_valid_format(self, temp_dir: Path) -> None:
        config_file = temp_dir / "config"
        config_file.write_text("format=otf,variable-ttf\npath=/custom/path\n")
        with patch("main.CONFIG_FILE", config_file):
            priorities, path, cache_size = load_config()
            assert priorities == ["otf", "variable-ttf"]
            assert path == Path("/custom/path")
            assert cache_size == 200 * 1024 * 1024

    def test_load_config_invalid_format(self, temp_dir: Path) -> None:
        config_file = temp_dir / "config"
        config_file.write_text("format=invalid,format\n")
        with patch("main.CONFIG_FILE", config_file):
            priorities, path, cache_size = load_config()
            assert priorities == DEFAULT_PRIORITIES  # Should fallback to default
            assert path == DEFAULT_PATH
            assert cache_size == 200 * 1024 * 1024

    def test_load_config_auto_format(self, temp_dir: Path) -> None:
        config_file = temp_dir / "config"
        config_file.write_text("format=auto\n")
        with patch("main.CONFIG_FILE", config_file):
            priorities, path, cache_size = load_config()
            assert priorities == DEFAULT_PRIORITIES  # auto should be ignored
            assert path == DEFAULT_PATH
            assert cache_size == 200 * 1024 * 1024

    def test_load_config_empty_path(self, temp_dir: Path) -> None:
        config_file = temp_dir / "config"
        config_file.write_text("path=\n")
        with patch("main.CONFIG_FILE", config_file):
            priorities, path, cache_size = load_config()
            assert priorities == DEFAULT_PRIORITIES
            assert path == DEFAULT_PATH  # empty path should be ignored
            assert cache_size == 200 * 1024 * 1024

    def test_load_config_file_error(self, temp_dir: Path) -> None:
        config_file = temp_dir / "config"
        config_file.write_text("invalid content that causes error")
        # Make the file unreadable or something, but for now, since the parsing is robust, it should work.
        # Actually, the code catches all exceptions, so to test the error, I can patch open to raise.
        with (
            patch("main.CONFIG_FILE", config_file),
            patch("builtins.open", side_effect=Exception("File error")),
        ):
            priorities, path, cache_size = load_config()
            assert priorities == DEFAULT_PRIORITIES
            assert path == DEFAULT_PATH
            assert cache_size == 200 * 1024 * 1024

    def test_load_config_with_cache_size(self, temp_dir: Path) -> None:
        config_file = temp_dir / "config"
        config_file.write_text("cache-size=100000000\n")
        with patch("main.CONFIG_FILE", config_file):
            priorities, path, cache_size = load_config()
            assert priorities == DEFAULT_PRIORITIES
            assert path == DEFAULT_PATH
            assert cache_size == 100000000


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
    def test_export_no_installed_file(self, runner: CliRunner) -> None:
        with patch("main.load_installed_data", return_value={}):
            result = runner.invoke(app, ["export"])
            assert result.exit_code == 0
            assert "No installed fonts data found." in result.output

    def test_export_stdout(self, runner: CliRunner) -> None:
        installed_data = {
            "repo1": {
                "font1.ttf": {"filename": "font1.ttf", "type": "ttf", "version": "1.0"}
            }
        }
        with patch("main.load_installed_data", return_value=installed_data):
            result = runner.invoke(app, ["export", "--stdout"])
            assert result.exit_code == 0
            assert "font1.ttf" in result.output

    def test_export_to_file(self, runner: CliRunner, temp_dir: Path) -> None:
        installed_data = {
            "repo1": {
                "font1.ttf": {"filename": "font1.ttf", "type": "ttf", "version": "1.0"}
            }
        }
        with patch("main.load_installed_data", return_value=installed_data):
            output_file = temp_dir / "export.json"
            result = runner.invoke(app, ["export", "--output", str(output_file)])
            assert result.exit_code == 0
            assert output_file.exists()
            data = json.loads(output_file.read_text())
            assert "repo1" in data
            assert "Exported to" in result.output
            assert str(output_file) in result.output


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
        with patch("main.default_path", Path("/fake/path")):
            result = runner.invoke(app, ["import", "--input", str(import_file)])
            assert result.exit_code == 0
            mock_install.assert_called_once_with(
                "owner",
                "repo",
                "1.0",
                ["ttf"],
                Path("/fake/path"),
                False,
                False,
                [],
                ["roman", "italic"],
            )


class TestUninstall:
    def test_uninstall_no_installed_file(self, runner: CliRunner) -> None:
        with patch("main.load_installed_data", return_value={}):
            result = runner.invoke(app, ["uninstall", "repo1"])
            assert result.exit_code == 0
            assert "No installed fonts data found." in result.output

    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_bytes")
    @patch("main.save_installed_data")
    def test_uninstall_success(
        self,
        mock_save: MagicMock,
        mock_read_bytes: MagicMock,
        mock_exists: MagicMock,
        mock_unlink: MagicMock,
        runner: CliRunner,
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
        with (
            patch("main.load_installed_data", return_value=installed_data),
            patch("main.default_path", Path("/fake/path")),
            patch("hashlib.sha256") as mock_hash,
        ):
            mock_hash.return_value.hexdigest.return_value = "hash"
            result = runner.invoke(app, ["uninstall", "repo1"])
            assert result.exit_code == 0
            assert "Deleted font1.ttf" in result.output
            mock_unlink.assert_called_once()
            # Assert installed_data is updated (repo removed)
            mock_save.assert_called_once()
            saved_data = mock_save.call_args[0][0]
            assert "repo1" not in saved_data

    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_bytes")
    def test_uninstall_file_not_found(
        self,
        mock_read_bytes: MagicMock,
        mock_exists: MagicMock,
        mock_unlink: MagicMock,
        runner: CliRunner,
    ) -> None:
        mock_exists.return_value = False
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
        with (
            patch("main.load_installed_data", return_value=installed_data),
            patch("main.default_path", Path("/fake/path")),
            patch("hashlib.sha256") as mock_hash,
        ):
            mock_hash.return_value.hexdigest.return_value = "hash"
            result = runner.invoke(app, ["uninstall", "repo1"])
            assert result.exit_code == 0
            assert "Font font1.ttf not found" in result.output
            mock_unlink.assert_not_called()

    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_bytes")
    def test_uninstall_permission_error(
        self,
        mock_read_bytes: MagicMock,
        mock_exists: MagicMock,
        mock_unlink: MagicMock,
        runner: CliRunner,
    ) -> None:
        mock_exists.return_value = True
        mock_read_bytes.return_value = b"dummy data"
        mock_unlink.side_effect = PermissionError("Permission denied")
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
        with (
            patch("main.load_installed_data", return_value=installed_data),
            patch("main.default_path", Path("/fake/path")),
            patch("hashlib.sha256") as mock_hash,
        ):
            mock_hash.return_value.hexdigest.return_value = "hash"
            result = runner.invoke(app, ["uninstall", "repo1"])
            assert result.exit_code == 0
            assert "Could not delete font1.ttf: Permission denied" in result.output
            mock_unlink.assert_called_once()

    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_bytes")
    def test_uninstall_hash_mismatch(
        self,
        mock_read_bytes: MagicMock,
        mock_exists: MagicMock,
        mock_unlink: MagicMock,
        runner: CliRunner,
    ) -> None:
        mock_exists.return_value = True
        mock_read_bytes.return_value = b"modified data"
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
        with (
            patch("main.load_installed_data", return_value=installed_data),
            patch("main.default_path", Path("/fake/path")),
            patch("hashlib.sha256") as mock_hash,
        ):
            mock_hash.return_value.hexdigest.return_value = "different_hash"
            result = runner.invoke(app, ["uninstall", "repo1"])
            assert result.exit_code == 0
            assert "Font font1.ttf has been modified" in result.output
            mock_unlink.assert_not_called()


class TestUpdate:
    def test_update_no_installed_file(self, runner: CliRunner) -> None:
        with patch("main.load_installed_data", return_value={}):
            result = runner.invoke(app, ["update"])
            assert result.exit_code == 0
            assert "No installed fonts data found." in result.output

    @patch("httpx.get")
    @patch("main.install_single_repo")
    @patch("main.save_installed_data")
    def test_update_success(
        self,
        mock_save: MagicMock,
        mock_install: MagicMock,
        mock_get: MagicMock,
        runner: CliRunner,
    ) -> None:
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
        mock_response = MagicMock()
        mock_response.json.return_value = {"tag_name": "v2.0"}
        mock_get.return_value = mock_response
        with (
            patch("main.load_installed_data", return_value=installed_data),
            patch("main.default_path", Path("/fake/path")),
            patch("packaging.version.Version") as mock_version,
            patch("pathlib.Path.exists", return_value=True) as mock_exists,
            patch("pathlib.Path.unlink") as mock_unlink,
        ):
            mock_version.return_value = MagicMock(__gt__=lambda *_: True)  # type: ignore
            result = runner.invoke(app, ["update", "owner/repo"])
            assert result.exit_code == 0
            assert "Updating owner/repo from 1.0 to v2.0..." in result.output
            mock_install.assert_called_once_with(
                "owner",
                "repo",
                "latest",
                ["variable-ttf", "otf", "static-ttf"],
                Path("/fake/path"),
                False,
                True,
                [],
                ["roman", "italic"],
            )
            # Assert old fonts are deleted
            mock_exists.assert_called_once_with()
            mock_unlink.assert_called_once_with()
            # Assert installed_data is updated (repo removed before reinstall)
            mock_save.assert_called_once()
            saved_data = mock_save.call_args[0][0]
            assert "owner/repo" not in saved_data

    @patch("httpx.get")
    def test_update_version_equal(self, mock_get: MagicMock, runner: CliRunner) -> None:
        installed_data = {
            "owner/repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash",
                    "type": "ttf",
                    "version": "v2.0",
                }
            }
        }
        mock_response = MagicMock()
        mock_response.json.return_value = {"tag_name": "v2.0"}
        mock_get.return_value = mock_response
        with (
            patch("main.load_installed_data", return_value=installed_data),
            patch("packaging.version.Version") as mock_version,
        ):
            mock_version.return_value = MagicMock(__gt__=lambda *_: False)  # type: ignore
            result = runner.invoke(app, ["update", "owner/repo"])
            assert result.exit_code == 0
            assert "owner/repo is up to date (v2.0)." in result.output

    @patch("httpx.get")
    def test_update_api_error(self, mock_get: MagicMock, runner: CliRunner) -> None:
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
        mock_get.side_effect = Exception("API Error")
        with patch("main.load_installed_data", return_value=installed_data):
            result = runner.invoke(app, ["update", "owner/repo"])
            assert result.exit_code == 0
            assert "Could not fetch latest for owner/repo: API Error" in result.output

    @patch("httpx.get")
    @patch("main.install_single_repo")
    @patch("main.save_installed_data")
    def test_update_specific_repo(
        self,
        _mock_save: MagicMock,
        mock_install: MagicMock,
        mock_get: MagicMock,
        runner: CliRunner,
    ) -> None:
        installed_data = {
            "owner/repo1": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash",
                    "type": "ttf",
                    "version": "1.0",
                }
            },
            "owner/repo2": {
                "font2.ttf": {
                    "filename": "font2.ttf",
                    "hash": "hash2",
                    "type": "ttf",
                    "version": "1.0",
                }
            },
        }
        mock_response = MagicMock()
        mock_response.json.return_value = {"tag_name": "v2.0"}
        mock_get.return_value = mock_response
        with (
            patch("main.load_installed_data", return_value=installed_data),
            patch("main.default_path", Path("/fake/path")),
            patch("packaging.version.Version") as mock_version,
        ):
            mock_version.return_value = MagicMock(__gt__=lambda *_: True)  # type: ignore
            result = runner.invoke(app, ["update", "owner/repo1"])
            assert result.exit_code == 0
            assert "Updating owner/repo1 from 1.0 to v2.0..." in result.output
            # Only repo1 should be checked when specified
            mock_install.assert_called_once_with(
                "owner",
                "repo1",
                "latest",
                ["variable-ttf", "otf", "static-ttf"],
                Path("/fake/path"),
                False,
                True,
                [],
                ["roman", "italic"],
            )

    @patch("httpx.get")
    def test_update_version_comparison_error(
        self, mock_get: MagicMock, runner: CliRunner
    ) -> None:
        installed_data = {
            "owner/repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash",
                    "type": "ttf",
                    "version": "invalid-version",
                }
            }
        }
        mock_response = MagicMock()
        mock_response.json.return_value = {"tag_name": "v2.0"}
        mock_get.return_value = mock_response
        with patch("main.load_installed_data", return_value=installed_data):
            result = runner.invoke(app, ["update", "owner/repo"])
            assert result.exit_code == 0
            assert "Could not compare versions for owner/repo" in result.output

    @patch("httpx.get")
    @patch("main.install_single_repo")
    @patch("main.save_installed_data")
    def test_update_partial_success(
        self,
        _mock_save: MagicMock,
        mock_install: MagicMock,
        mock_get: MagicMock,
        runner: CliRunner,
    ) -> None:
        installed_data = {
            "owner/repo1": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash",
                    "type": "ttf",
                    "version": "1.0",
                }
            },
            "owner/repo2": {
                "font2.ttf": {
                    "filename": "font2.ttf",
                    "hash": "hash2",
                    "type": "ttf",
                    "version": "1.0",
                }
            },
        }

        def mock_get_side_effect(url: str) -> MagicMock:
            if "repo1" in url:
                mock_response = MagicMock()
                mock_response.json.return_value = {"tag_name": "v2.0"}
                return mock_response
            elif "repo2" in url:
                raise Exception("API Error for repo2")
            raise Exception("Unexpected URL")

        mock_get.side_effect = mock_get_side_effect
        with (
            patch("main.load_installed_data", return_value=installed_data),
            patch("main.default_path", Path("/fake/path")),
            patch("packaging.version.Version") as mock_version,
        ):
            mock_version.return_value = MagicMock(__gt__=lambda *_: True)  # type: ignore
            result = runner.invoke(app, ["update"])
            assert result.exit_code == 0
            assert "Updating owner/repo1 from 1.0 to v2.0..." in result.output
            assert (
                "Could not fetch latest for owner/repo2: API Error for repo2"
                in result.output
            )
            # Should only call install for repo1
            assert mock_install.call_count == 1
            mock_install.assert_called_with(
                "owner",
                "repo1",
                "latest",
                ["variable-ttf", "otf", "static-ttf"],
                Path("/fake/path"),
                False,
                True,
                [],
                ["roman", "italic"],
            )

    @patch("httpx.get")
    @patch("main.install_single_repo")
    @patch("main.save_installed_data")
    def test_update_with_changelog(
        self,
        mock_save: MagicMock,
        mock_install: MagicMock,
        mock_get: MagicMock,
        runner: CliRunner,
    ) -> None:
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
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "tag_name": "v2.0",
            "body": "This is the changelog for v2.0.",
        }
        mock_get.return_value = mock_response
        with (
            patch("main.load_installed_data", return_value=installed_data),
            patch("main.default_path", Path("/fake/path")),
            patch("packaging.version.Version") as mock_version,
            patch("pathlib.Path.exists", return_value=True) as mock_exists,
            patch("pathlib.Path.unlink") as mock_unlink,
        ):
            mock_version.return_value = MagicMock(__gt__=lambda *_: True)  # type: ignore
            result = runner.invoke(app, ["update", "owner/repo", "--changelog"])
            assert result.exit_code == 0
            assert "Updating owner/repo from 1.0 to v2.0..." in result.output
            assert "Changelog for owner/repo v2.0:" in result.output
            assert "This is the changelog for v2.0." in result.output
            mock_install.assert_called_once_with(
                "owner",
                "repo",
                "latest",
                ["variable-ttf", "otf", "static-ttf"],
                Path("/fake/path"),
                False,
                True,
                [],
                ["roman", "italic"],
            )
            # Assert old fonts are deleted
            mock_exists.assert_called_once_with()
            mock_unlink.assert_called_once_with()
            # Assert installed_data is updated (repo removed before reinstall)
            mock_save.assert_called_once()
            saved_data = mock_save.call_args[0][0]
            assert "owner/repo" not in saved_data


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
            [],
            ["roman", "italic"],
        )

    def test_install_invalid_repo_format(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["install", "invalidrepo"])
        assert result.exit_code == 0
        assert "Invalid repo format: invalidrepo" in result.output

    def test_install_invalid_format(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["install", "owner/repo", "--format", "invalid"])
        assert result.exit_code == 1
        assert "Invalid --format value" in result.output

    @patch("main.install_single_repo")
    def test_install_with_force(
        self, mock_install: MagicMock, runner: CliRunner
    ) -> None:
        result = runner.invoke(app, ["install", "owner/repo", "--force"])
        assert result.exit_code == 0
        mock_install.assert_called_once_with(
            "owner",
            "repo",
            "latest",
            ["variable-ttf", "otf", "static-ttf"],
            Path("/Users/sacha/Library/Fonts"),
            False,
            True,  # force=True
            [],
            ["roman", "italic"],
        )

    @patch("main.install_single_repo")
    def test_install_with_local(
        self, mock_install: MagicMock, runner: CliRunner
    ) -> None:
        result = runner.invoke(app, ["install", "owner/repo", "--local"])
        assert result.exit_code == 0
        mock_install.assert_called_once_with(
            "owner",
            "repo",
            "latest",
            ["variable-ttf", "otf", "static-ttf"],
            Path.cwd(),  # local=True so uses cwd
            True,  # local=True
            False,
            [],
            ["roman", "italic"],
        )

    @patch("main.install_single_repo")
    def test_install_with_release(
        self, mock_install: MagicMock, runner: CliRunner
    ) -> None:
        result = runner.invoke(app, ["install", "owner/repo", "--release", "v1.0"])
        assert result.exit_code == 0
        mock_install.assert_called_once_with(
            "owner",
            "repo",
            "v1.0",  # release specified
            ["variable-ttf", "otf", "static-ttf"],
            Path("/Users/sacha/Library/Fonts"),
            False,
            False,
            [],
            ["roman", "italic"],
        )

    @patch("main.install_single_repo")
    def test_install_with_custom_format(
        self, mock_install: MagicMock, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app, ["install", "owner/repo", "--format", "otf,static-ttf"]
        )
        assert result.exit_code == 0
        mock_install.assert_called_once_with(
            "owner",
            "repo",
            "latest",
            ["otf", "static-ttf"],  # custom format
            Path("/Users/sacha/Library/Fonts"),
            False,
            False,
            [],
            ["roman", "italic"],
        )

    @patch("main.install_single_repo")
    def test_install_with_weights(
        self, mock_install: MagicMock, runner: CliRunner
    ) -> None:
        result = runner.invoke(app, ["install", "owner/repo", "--weights", "400,700"])
        assert result.exit_code == 0
        mock_install.assert_called_once_with(
            "owner",
            "repo",
            "latest",
            ["variable-ttf", "otf", "static-ttf"],
            Path("/Users/sacha/Library/Fonts"),
            False,
            False,
            [400, 700],
            ["roman", "italic"],
        )

    @patch("main.install_single_repo")
    def test_install_with_weights_names(
        self, mock_install: MagicMock, runner: CliRunner
    ) -> None:
        result = runner.invoke(
            app, ["install", "owner/repo", "--weights", "Regular,Bold"]
        )
        assert result.exit_code == 0
        mock_install.assert_called_once_with(
            "owner",
            "repo",
            "latest",
            ["variable-ttf", "otf", "static-ttf"],
            Path("/Users/sacha/Library/Fonts"),
            False,
            False,
            [400, 700],
            ["roman", "italic"],
        )

    def test_install_invalid_weights(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["install", "owner/repo", "--weights", "invalid"])
        assert result.exit_code == 1
        assert "Unknown weight: invalid" in result.output

    @patch("main.install_single_repo")
    def test_install_with_style(
        self, mock_install: MagicMock, runner: CliRunner
    ) -> None:
        result = runner.invoke(app, ["install", "owner/repo", "--style", "roman"])
        assert result.exit_code == 0
        mock_install.assert_called_once_with(
            "owner",
            "repo",
            "latest",
            ["variable-ttf", "otf", "static-ttf"],
            Path("/Users/sacha/Library/Fonts"),
            False,
            False,
            [],
            ["roman"],
        )

    def test_install_invalid_style(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["install", "owner/repo", "--style", "invalid"])
        assert result.exit_code == 1
        assert "Invalid --style value" in result.output


class TestFontFunctions:
    @patch("main.TTFont")
    def test_is_variable_font_true(self, mock_ttfont: MagicMock) -> None:
        mock_font = MagicMock()
        mock_font.__contains__ = lambda *args: args[1] == "fvar"  # type: ignore
        mock_ttfont.return_value = mock_font
        from main import is_variable_font

        assert is_variable_font("dummy.ttf") is True

    @patch("main.TTFont")
    def test_is_variable_font_false(self, mock_ttfont: MagicMock) -> None:
        mock_font = MagicMock()
        mock_font.__contains__ = lambda *args: args[1] != "fvar"  # type: ignore
        mock_ttfont.return_value = mock_font
        from main import is_variable_font

        assert is_variable_font("dummy.ttf") is False

    @patch("main.TTFont")
    def test_is_variable_font_error(self, mock_ttfont: MagicMock) -> None:
        mock_ttfont.side_effect = Exception("Font error")
        from main import is_variable_font

        with pytest.raises(Exception, match="Font error"):
            is_variable_font("dummy.ttf")

    @patch("main.TTFont")
    def test_get_font_weight(self, mock_ttfont: MagicMock) -> None:
        mock_font = MagicMock()
        mock_os2 = MagicMock()
        mock_os2.usWeightClass = 700
        mock_font.__getitem__ = lambda *args: mock_os2 if args[1] == "OS/2" else None  # type: ignore
        mock_ttfont.return_value = mock_font
        from main import get_font_weight

        weight = get_font_weight("dummy.ttf")
        assert weight == 700

    @patch("main.TTFont")
    def test_get_font_weight_error(self, mock_ttfont: MagicMock) -> None:
        mock_ttfont.side_effect = Exception("Font error")
        from main import get_font_weight

        weight = get_font_weight("dummy.ttf")
        assert weight == 400  # default

    def test_parse_repo_valid(self) -> None:
        from main import parse_repo

        owner, repo = parse_repo("owner/repo")
        assert owner == "owner"
        assert repo == "repo"

    def test_parse_repo_invalid(self) -> None:
        from main import parse_repo

        with pytest.raises(ValueError, match="Invalid repo format"):
            parse_repo("invalidrepo")

    @patch("main.is_variable_font")
    def test_categorize_fonts(self, mock_is_var: MagicMock) -> None:
        from pathlib import Path

        from main import categorize_fonts

        # Mock variable and static fonts
        mock_is_var.side_effect = [True, False, False, True]

        font_files = [
            Path("var1.ttf"),
            Path("static1.ttf"),
            Path("var2.otf"),
            Path("static2.woff"),
            Path("var3.woff2"),
        ]

        result = categorize_fonts(font_files)
        (
            var_ttfs,
            static_ttfs,
            otfs,
            var_woffs,
            static_woffs,
            var_woff2s,
            static_woff2s,
        ) = result

        assert len(var_ttfs) == 1
        assert len(static_ttfs) == 1
        assert len(otfs) == 1
        assert len(var_woffs) == 0
        assert len(static_woffs) == 1
        assert len(var_woff2s) == 1
        assert len(static_woff2s) == 0

    def test_select_archive_asset_single(self) -> None:
        from main import select_archive_asset

        assets = cast(
            "List[Asset]",
            [
                {"name": "font.zip", "size": 1000, "browser_download_url": "url1"},
                {"name": "font.tar.gz", "size": 2000, "browser_download_url": "url2"},
            ],
        )

        result = select_archive_asset(assets)
        assert result["name"] == "font.tar.gz"  # tar.gz has higher priority

    def test_select_archive_asset_multiple_groups(self) -> None:
        from main import select_archive_asset

        assets = cast(
            "List[Asset]",
            [
                {"name": "font-v1.zip", "size": 1000, "browser_download_url": "url1"},
                {"name": "font-v1.tar.gz", "size": 800, "browser_download_url": "url2"},
                {"name": "font-v2.zip", "size": 1200, "browser_download_url": "url3"},
            ],
        )

        result = select_archive_asset(assets)
        assert (
            result["name"] == "font-v1.tar.gz"
        )  # smallest in group with highest priority

    def test_select_archive_asset_no_archive(self) -> None:
        from main import select_archive_asset

        assets = cast(
            "List[Asset]",
            [
                {"name": "font.ttf", "size": 1000, "browser_download_url": "url1"},
            ],
        )

        with pytest.raises(ValueError, match="No archive asset found"):
            select_archive_asset(assets)

    def test_select_fonts_priority_order(self) -> None:
        from main import select_fonts

        categorized = cast(
            "Tuple[List[Path], List[Path], List[Path], List[Path], List[Path], List[Path], List[Path]]",
            (
                [Path("var.ttf")],  # variable_ttfs
                [Path("static.ttf")],  # static_ttfs
                [Path("font.otf")],  # otf_files
                [],
                [],
                [],
                [],  # empty others
            ),
        )

        selected, pri = select_fonts(
            categorized, ["variable-ttf", "otf", "static-ttf"], [], ["roman", "italic"]
        )
        assert selected == [Path("var.ttf")]
        assert pri == "variable-ttf"

    def test_select_fonts_fallback(self) -> None:
        from main import select_fonts

        categorized = cast(
            "Tuple[List[Path], List[Path], List[Path], List[Path], List[Path], List[Path], List[Path]]",
            (
                [],  # variable_ttfs
                [Path("static.ttf")],  # static_ttfs
                [],  # otf_files
                [],
                [],
                [],
                [],  # empty others
            ),
        )

        selected, pri = select_fonts(
            categorized, ["variable-ttf", "otf", "static-ttf"], [], ["roman", "italic"]
        )
        assert selected == [Path("static.ttf")]
        assert pri == "static-ttf"

    def test_select_fonts_no_match(self) -> None:
        from main import select_fonts

        categorized = cast(
            "Tuple[List[Path], List[Path], List[Path], List[Path], List[Path], List[Path], List[Path]]",
            ([], [], [], [], [], [], []),  # all empty
        )

        selected, pri = select_fonts(
            categorized, ["variable-ttf"], [], ["roman", "italic"]
        )
        assert selected == []
        assert pri == ""

    @patch("httpx.get")
    def test_fetch_release_info_latest(self, mock_get: MagicMock) -> None:
        from main import fetch_release_info

        mock_response = MagicMock()
        mock_response.json.return_value = {"tag_name": "v1.0"}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        version, assets, body = fetch_release_info("owner", "repo", "latest")
        assert version == "v1.0"
        assert assets == []
        assert body == ""
        mock_get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/releases/latest"
        )

    @patch("httpx.get")
    def test_fetch_release_info_specific_version(self, mock_get: MagicMock) -> None:
        from main import fetch_release_info

        mock_response = MagicMock()
        mock_response.json.return_value = {"tag_name": "v2.0"}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        version, assets, body = fetch_release_info("owner", "repo", "2.0")
        assert version == "v2.0"
        assert assets == []
        assert body == ""
        mock_get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/releases/tags/v2.0"
        )

    @patch("shutil.copy")
    @patch("main.CACHE")
    @patch("pathlib.Path.stat")
    @patch("builtins.open")
    @patch("tempfile.NamedTemporaryFile")
    @patch("tempfile.mkdtemp")
    @patch("httpx.stream")
    @patch("zipfile.ZipFile")
    def test_download_and_extract_zip(
        self,
        mock_zip: MagicMock,
        mock_stream: MagicMock,
        mock_mkdtemp: MagicMock,
        mock_named_temp: MagicMock,
        mock_open: MagicMock,
        mock_stat: MagicMock,
        mock_cache: MagicMock,
        _mock_copy: MagicMock,
    ) -> None:
        from main import get_or_download_and_extract_archive

        # Mock mkdtemp
        mock_mkdtemp.return_value = "/tmp/test"

        # Mock named temporary file
        mock_file = MagicMock()
        mock_file.name = "/tmp/test/temp.archive"
        mock_named_temp.return_value = mock_file

        # Mock HTTP stream
        mock_response = MagicMock()
        mock_response.iter_bytes.return_value = [b"fake zip data"]
        mock_response.raise_for_status.return_value = None
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_response
        mock_stream.return_value = mock_context

        # Mock open
        mock_open.return_value.__enter__.return_value = MagicMock()

        # Mock stat
        mock_stat.return_value.st_size = 1000

        # Mock cache
        mock_cache.__contains__.return_value = False
        mock_cache.volume.return_value = 0

        # Mock zip file
        mock_zip.return_value.__enter__.return_value.extractall.return_value = None

        result = get_or_download_and_extract_archive(
            "owner", "repo", "v1.0", "http://example.com/file.zip", ".zip", "file.zip"
        )
        assert str(result) == "/tmp/test"

        mock_zip.assert_called_once()
        mock_zip.return_value.__enter__.return_value.extractall.assert_called_once_with(
            Path("/tmp/test")
        )


class TestInstallSingleRepo:
    @patch("shutil.rmtree")
    @patch("main.CACHE")
    @patch("main.fetch_release_info")
    @patch("tempfile.mkdtemp")
    @patch("zipfile.ZipFile")
    def test_cache_hit_specific_release(
        self,
        mock_zip: MagicMock,
        mock_mkdtemp: MagicMock,
        mock_fetch: MagicMock,
        mock_cache: MagicMock,
        _mock_rmtree: MagicMock,
    ) -> None:
        from main import install_single_repo

        # Mock cache hit
        mock_cache.__contains__.return_value = True
        mock_cache.__getitem__.return_value = "/cache/path.zip"

        # Mock temp dir
        mock_mkdtemp.return_value = "/tmp/extract"

        # Mock zip extraction
        mock_zip.return_value.__enter__.return_value.extractall.return_value = None

        # Call with specific release
        install_single_repo(
            "rsms",
            "inter",
            "4.1",
            ["static-ttf"],
            Path("/dest"),
            True,
            False,
            [],
            ["roman", "italic"],
        )

        # Should not call fetch_release_info
        mock_fetch.assert_not_called()

        # Should extract from cache
        mock_zip.assert_called_once_with("/cache/path.zip", "r")
        mock_zip.return_value.__enter__.return_value.extractall.assert_called_once_with(
            Path("/tmp/extract")
        )

    @patch("shutil.rmtree")
    @patch("main.CACHE")
    @patch("main.fetch_release_info")
    @patch("main.get_or_download_and_extract_archive")
    def test_cache_miss_specific_release(
        self,
        mock_get_or_download: MagicMock,
        mock_fetch: MagicMock,
        mock_cache: MagicMock,
        _mock_rmtree: MagicMock,
    ) -> None:
        from main import install_single_repo

        # Mock cache miss
        mock_cache.__contains__.return_value = False

        # Mock fetch for assets
        mock_fetch.return_value = (
            "4.1",
            [{"name": "inter.zip", "size": 1000, "browser_download_url": "url"}],
            "Changelog here",
        )

        # Mock download and extract
        mock_get_or_download.return_value = Path("/tmp/extract")

        # Call with specific release
        install_single_repo(
            "rsms",
            "inter",
            "4.1",
            ["static-ttf"],
            Path("/dest"),
            True,
            False,
            [],
            ["roman", "italic"],
        )

        # Should call fetch_release_info once for assets
        mock_fetch.assert_called_once_with("rsms", "inter", "4.1")

        # Should download
        mock_get_or_download.assert_called_once()

    @patch("shutil.rmtree")
    @patch("main.CACHE")
    @patch("main.fetch_release_info")
    @patch("main.get_or_download_and_extract_archive")
    def test_latest_release_always_fetches(
        self,
        mock_get_or_download: MagicMock,
        mock_fetch: MagicMock,
        _mock_cache: MagicMock,
        _mock_rmtree: MagicMock,
    ) -> None:
        from main import install_single_repo

        # Mock fetch
        mock_fetch.return_value = (
            "4.1",
            [{"name": "inter.zip", "size": 1000, "browser_download_url": "url"}],
            "Changelog here",
        )

        # Mock download and extract
        mock_get_or_download.return_value = Path("/tmp/extract")

        # Call with latest
        install_single_repo(
            "rsms",
            "inter",
            "latest",
            ["static-ttf"],
            Path("/dest"),
            True,
            False,
            [],
            ["roman", "italic"],
        )

        # Should call fetch_release_info
        mock_fetch.assert_called_once_with("rsms", "inter", "latest")

        # Should download
        mock_get_or_download.assert_called_once()


class TestFix:
    def test_fix_no_installed_file(self, runner: CliRunner) -> None:
        with patch("main.load_installed_data", return_value={}):
            result = runner.invoke(app, ["fix"])
            assert result.exit_code == 0
            assert "No installed fonts data found." in result.output

    def test_fix_no_duplicates(self, runner: CliRunner) -> None:
        installed_data = {
            "owner1/repo1": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash1",
                    "type": "ttf",
                    "version": "1.0",
                }
            },
            "owner2/repo2": {
                "font2.ttf": {
                    "filename": "font2.ttf",
                    "hash": "hash2",
                    "type": "ttf",
                    "version": "1.0",
                }
            },
        }
        with patch("main.load_installed_data", return_value=installed_data):
            result = runner.invoke(app, ["fix"])
            assert result.exit_code == 0
            assert "No issues found." in result.output

    @patch("main.save_installed_data")
    def test_fix_with_duplicates(self, mock_save: MagicMock, runner: CliRunner) -> None:
        installed_data = {
            "owner1/repo1": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash1",
                    "type": "static-ttf",
                    "version": "1.0",
                }
            },
            "owner2/repo2": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash1",
                    "type": "static-ttf",
                    "version": "1.0",
                }
            },
            "owner3/repo3": {
                "font2.ttf": {
                    "filename": "font2.ttf",
                    "hash": "hash2",
                    "type": "static-ttf",
                    "version": "1.0",
                }
            },
        }
        with patch("main.load_installed_data", return_value=installed_data):
            result = runner.invoke(app, ["fix"], input="y\n")
            assert result.exit_code == 0
            assert "Found 1 issue(s):" in result.output
            assert "Remove duplicate font1.ttf from owner2/repo2" in result.output
            assert "Proceed with fixes?" in result.output
            assert "Removed duplicate font1.ttf from owner2/repo2" in result.output
            assert "Fixed 1 issue(s)." in result.output
            mock_save.assert_called_once()
            # Check that repo2 is removed
            saved_data = mock_save.call_args[0][0]
            assert "repo2" not in saved_data

    @patch("main.save_installed_data")
    def test_fix_invalid_repo(self, mock_save: MagicMock, runner: CliRunner) -> None:
        installed_data = {
            "invalidrepo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash1",
                    "type": "static-ttf",
                    "version": "1.0",
                }
            },
            "owner/repo": {
                "font2.ttf": {
                    "filename": "font2.ttf",
                    "hash": "hash2",
                    "type": "static-ttf",
                    "version": "1.0",
                }
            },
        }
        with patch("main.load_installed_data", return_value=installed_data):
            result = runner.invoke(app, ["fix"], input="y\n")
            assert result.exit_code == 0
            assert "Found 1 issue(s):" in result.output
            assert "Remove invalid repo: invalidrepo" in result.output
            assert "Proceed with fixes?" in result.output
            assert "Removed invalid repo: invalidrepo" in result.output
            assert "Fixed 1 issue(s)." in result.output
            mock_save.assert_called_once()
            saved_data = mock_save.call_args[0][0]
            assert "invalidrepo" not in saved_data
            assert "owner/repo" in saved_data

    @patch("main.save_installed_data")
    def test_fix_invalid_entry(self, mock_save: MagicMock, runner: CliRunner) -> None:
        installed_data = {
            "owner/repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash1",
                    "type": "otf",  # mismatch: .ttf but type otf
                    "version": "1.0",
                },
                "font2.otf": {
                    "filename": "font2.otf",
                    "hash": "hash2",
                    "type": "otf",
                    "version": "1.0",
                },
            },
        }
        with patch("main.load_installed_data", return_value=installed_data):
            result = runner.invoke(app, ["fix"], input="y\n")
            assert result.exit_code == 0
            assert "Found 1 issue(s):" in result.output
            assert (
                "Remove invalid entry: owner/repo/font1.ttf (type/extension mismatch)"
                in result.output
            )
            assert "Proceed with fixes?" in result.output
            assert "Removed invalid entry: owner/repo/font1.ttf" in result.output
            assert "Fixed 1 issue(s)." in result.output
            mock_save.assert_called_once()
            saved_data = mock_save.call_args[0][0]
            assert "font1.ttf" not in saved_data["owner/repo"]
            assert "font2.otf" in saved_data["owner/repo"]

    @patch("main.save_installed_data")
    def test_fix_abort(self, mock_save: MagicMock, runner: CliRunner) -> None:
        installed_data = {
            "owner1/repo1": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash1",
                    "type": "static-ttf",
                    "version": "1.0",
                }
            },
            "owner2/repo2": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash1",
                    "type": "static-ttf",
                    "version": "1.0",
                }
            },
        }
        with patch("main.load_installed_data", return_value=installed_data):
            result = runner.invoke(app, ["fix"], input="n\n")
            assert result.exit_code == 0
            assert "Found 1 issue(s):" in result.output
            assert "Remove duplicate font1.ttf from owner2/repo2" in result.output
            assert "Proceed with fixes?" in result.output
            assert "Aborted." in result.output
            mock_save.assert_not_called()

    @patch("shutil.copy")
    def test_fix_backup(
        self, mock_copy: MagicMock, runner: CliRunner, temp_dir: Path
    ) -> None:
        installed_file = temp_dir / ".fontpm" / "installed.json"
        installed_file.parent.mkdir(parents=True, exist_ok=True)
        installed_file.write_text("{}")
        installed_data = {
            "owner/repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash1",
                    "type": "ttf",
                    "version": "1.0",
                }
            },
        }
        with (
            patch("main.load_installed_data", return_value=installed_data),
            patch("main.INSTALLED_FILE", installed_file),
        ):
            result = runner.invoke(app, ["fix", "--backup"])
            assert result.exit_code == 0
            assert "Backup created:" in result.output
            mock_copy.assert_called_once_with(
                installed_file, installed_file.with_suffix(".json.backup")
            )


class TestCache:
    @patch("main.CACHE")
    def test_cache_purge(self, mock_cache: MagicMock, runner: CliRunner) -> None:
        result = runner.invoke(app, ["cache", "purge"])
        assert result.exit_code == 0
        assert "Cache purged." in result.output
        mock_cache.clear.assert_called_once()
