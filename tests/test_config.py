import base64
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
import typer
from cryptography.fernet import Fernet

from fontpm.config import (
    get_encryption_key,
    load_config,
    load_installed_data,
    save_installed_data,
    set_config,
)
from fontpm.constants import DEFAULT_CACHE_SIZE, DEFAULT_PATH, DEFAULT_PRIORITIES


class TestGetEncryptionKey:
    """Test get_encryption_key function."""

    @patch("fontpm.config.KEY_FILE")
    @patch("fontpm.config.Fernet.generate_key")
    def test_get_encryption_key_existing(
        self, mock_generate_key: MagicMock, mock_key_file: MagicMock
    ) -> None:
        """Test getting existing encryption key."""
        mock_key_file.exists.return_value = True
        mock_key_file.read_bytes.return_value = b"existing_key"
        mock_key_file.parent.mkdir = MagicMock()

        result = get_encryption_key()

        assert result == b"existing_key"
        mock_key_file.exists.assert_called_once()
        mock_key_file.read_bytes.assert_called_once()
        mock_generate_key.assert_not_called()

    @patch("fontpm.config.KEY_FILE")
    @patch("fontpm.config.Fernet.generate_key")
    def test_get_encryption_key_generate_new(
        self, mock_generate_key: MagicMock, mock_key_file: MagicMock
    ) -> None:
        """Test generating new encryption key."""
        mock_key_file.exists.return_value = False
        mock_generate_key.return_value = b"new_key"
        mock_key_file.parent.mkdir = MagicMock()
        mock_key_file.write_bytes = MagicMock()

        result = get_encryption_key()

        assert result == b"new_key"
        mock_key_file.exists.assert_called_once()
        mock_key_file.parent.mkdir.assert_called_once_with(exist_ok=True)
        mock_key_file.write_bytes.assert_called_once_with(b"new_key")


class TestLoadConfig:
    """Test load_config function."""

    @patch("fontpm.config.CONFIG_FILE", new_callable=lambda: MagicMock())
    def test_load_config_no_file(self, mock_config_file: MagicMock) -> None:
        """Test loading config when no config file exists."""
        mock_config_file.exists.return_value = False

        result = load_config()

        priorities, path, cache_size, github_token = result
        assert priorities == DEFAULT_PRIORITIES
        assert path == DEFAULT_PATH
        assert cache_size == DEFAULT_CACHE_SIZE
        assert github_token == ""

    @patch("fontpm.config.get_encryption_key")
    def test_load_config_with_valid_config(self, mock_get_key: MagicMock) -> None:
        """Test loading config with valid configuration."""
        # Create a temporary config file
        key = Fernet.generate_key()
        mock_get_key.return_value = key
        fernet = Fernet(key)
        encrypted_token = base64.b64encode(fernet.encrypt(b"test_token")).decode()

        config_content = (
            "format=otf,static-ttf\n"
            "path=/custom/path\n"
            "cache-size=100000000\n"
            f"github_token={encrypted_token}\n"
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(config_content)
            temp_path = Path(f.name)

        try:
            with patch("fontpm.config.CONFIG_FILE", temp_path):
                result = load_config()

                priorities, path, cache_size, github_token = result
                assert priorities == ["otf", "static-ttf"]
                assert path == Path("/custom/path")
                assert cache_size == 100000000
                assert github_token == "test_token"
        finally:
            temp_path.unlink(missing_ok=True)

    @patch("fontpm.config.get_encryption_key")
    @patch("fontpm.config.CONFIG_FILE")
    @patch("builtins.open", new_callable=mock_open)
    def test_load_config_invalid_format(
        self,
        mock_file: MagicMock,
        mock_config_file: MagicMock,
        mock_get_key: MagicMock,
    ) -> None:
        """Test loading config with invalid format."""
        mock_config_file.exists.return_value = True
        mock_file.return_value.read.return_value = "format=invalid,format\n"
        mock_get_key.return_value = Fernet.generate_key()

        result = load_config()

        priorities, _, _, _ = result
        # Should use defaults when invalid format
        assert priorities == DEFAULT_PRIORITIES

    @patch("fontpm.config.get_encryption_key")
    @patch("fontpm.config.CONFIG_FILE")
    @patch("builtins.open", side_effect=Exception("File error"))
    def test_load_config_file_error(
        self,
        _mock_file: MagicMock,
        mock_config_file: MagicMock,
        mock_get_key: MagicMock,
    ) -> None:
        """Test loading config when file read fails."""
        mock_config_file.exists.return_value = True
        mock_get_key.return_value = Fernet.generate_key()
        mock_config_file.exists.return_value = True

        result = load_config()

        priorities, path, cache_size, github_token = result
        assert priorities == DEFAULT_PRIORITIES
        assert path == DEFAULT_PATH
        assert cache_size == DEFAULT_CACHE_SIZE
        assert github_token == ""


class TestSetConfig:
    """Test set_config function."""

    @patch("fontpm.config.CONFIG_FILE")
    @patch("fontpm.config.console.print")
    @patch("builtins.open", new_callable=mock_open)
    def test_set_config_format_valid(
        self, mock_file: MagicMock, mock_print: MagicMock, mock_config_file: MagicMock
    ) -> None:
        """Test setting valid format config."""
        mock_config_file.exists.return_value = False
        mock_file_handle = mock_file.return_value.__enter__.return_value

        set_config("format", "otf,static-ttf")

        mock_file_handle.write.assert_called_once_with("format=otf,static-ttf\n")
        mock_print.assert_called_once_with(
            "[green]Set format to: otf,static-ttf[/green]"
        )

    @patch("fontpm.config.CONFIG_FILE")
    @patch("fontpm.config.console.print")
    def test_set_config_format_invalid(
        self, mock_print: MagicMock, _mock_config_file: MagicMock
    ) -> None:
        """Test setting invalid format config."""
        with pytest.raises(typer.Exit):
            set_config("format", "invalid,format")

        mock_print.assert_called_once_with(
            "[red]Invalid format values: invalid,format[/red]"
        )

    @patch("fontpm.config.CONFIG_FILE")
    @patch("fontpm.config.console.print")
    @patch("builtins.open", new_callable=mock_open)
    def test_set_config_path(
        self, mock_file: MagicMock, mock_print: MagicMock, mock_config_file: MagicMock
    ) -> None:
        """Test setting path config."""
        mock_config_file.exists.return_value = False
        mock_file_handle = mock_file.return_value.__enter__.return_value

        set_config("path", "/new/path")

        mock_file_handle.write.assert_called_once_with("path=/new/path\n")
        mock_print.assert_called_once_with("[green]Set path to: /new/path[/green]")

    @patch("fontpm.config.CONFIG_FILE")
    @patch("fontpm.config.console.print")
    def test_set_config_cache_size_invalid(
        self, mock_print: MagicMock, _mock_config_file: MagicMock
    ) -> None:
        """Test setting invalid cache size."""
        with pytest.raises(typer.Exit):
            set_config("cache-size", "not_a_number")

        mock_print.assert_called_once_with(
            "[red]Invalid cache size: must be integer[/red]"
        )

    @patch("fontpm.config.get_encryption_key")
    @patch("fontpm.config.CONFIG_FILE")
    @patch("fontpm.config.console.print")
    @patch("builtins.open", new_callable=mock_open)
    def test_set_config_github_token(
        self,
        mock_file: MagicMock,
        mock_print: MagicMock,
        mock_config_file: MagicMock,
        mock_get_key: MagicMock,
    ) -> None:
        """Test setting GitHub token config."""
        mock_config_file.exists.return_value = False
        mock_get_key.return_value = Fernet.generate_key()
        mock_file_handle = mock_file.return_value.__enter__.return_value

        set_config("github_token", "test_token")

        # Should write encrypted token
        args = mock_file_handle.write.call_args[0][0]
        assert args.startswith("github_token=")
        assert args != "github_token=test_token\n"  # Should be encrypted
        mock_print.assert_called_once_with("[green]Set github_token to: ***[/green]")

    @patch("fontpm.config.CONFIG_FILE")
    @patch("builtins.open", side_effect=Exception("Write error"))
    @patch("fontpm.config.console.print")
    def test_set_config_write_error(
        self, mock_print: MagicMock, _mock_file: MagicMock, mock_config_file: MagicMock
    ) -> None:
        """Test config write error."""
        mock_config_file.exists.return_value = False

        with pytest.raises(typer.Exit):
            set_config("path", "/test/path")

        mock_print.assert_any_call("[red]Error writing config: Write error[/red]")


class TestLoadInstalledData:
    """Test load_installed_data function."""

    @patch("fontpm.config.INSTALLED_FILE")
    def test_load_installed_data_no_file(self, mock_installed_file: MagicMock) -> None:
        """Test loading installed data when file doesn't exist."""
        mock_installed_file.exists.return_value = False

        result = load_installed_data()

        assert result == {}

    @patch("fontpm.config.INSTALLED_FILE")
    @patch("builtins.open", new_callable=mock_open)
    @patch("json.load")
    def test_load_installed_data_success(
        self,
        mock_json_load: MagicMock,
        _mock_file: MagicMock,
        mock_installed_file: MagicMock,
    ) -> None:
        """Test successful loading of installed data."""
        mock_installed_file.exists.return_value = True
        mock_json_load.return_value = {
            "OWNER/REPO": {"font.ttf": {"filename": "font.ttf"}},
            "owner/repo2": {"font2.ttf": {"filename": "font2.ttf"}},
        }

        result = load_installed_data()

        expected = {
            "owner/repo": {"font.ttf": {"filename": "font.ttf"}},
            "owner/repo2": {"font2.ttf": {"filename": "font2.ttf"}},
        }
        assert result == expected

    @patch("fontpm.config.INSTALLED_FILE")
    @patch("builtins.open", side_effect=Exception("Read error"))
    @patch("fontpm.config.console.print")
    def test_load_installed_data_error(
        self,
        mock_print: MagicMock,
        _mock_file: MagicMock,
        mock_installed_file: MagicMock,
    ) -> None:
        """Test loading installed data with file error."""
        mock_installed_file.exists.return_value = True

        result = load_installed_data()

        assert result == {}
        mock_print.assert_called_once_with(
            "[yellow]Warning: Could not load installed data: Read error[/yellow]"
        )


class TestSaveInstalledData:
    """Test save_installed_data function."""

    @patch("fontpm.config.INSTALLED_FILE")
    @patch("builtins.open", new_callable=mock_open)
    @patch("json.dump")
    def test_save_installed_data_success(
        self,
        mock_json_dump: MagicMock,
        mock_file: MagicMock,
        mock_installed_file: MagicMock,
    ) -> None:
        """Test successful saving of installed data."""
        mock_installed_file.parent.mkdir = MagicMock()
        mock_file_handle = mock_file.return_value.__enter__.return_value

        test_data = {
            "repo": {
                "font.ttf": {
                    "filename": "font.ttf",
                    "hash": "abc123",
                    "type": "static-ttf",
                    "version": "1.0",
                    "owner": "test",
                    "repo_name": "repo",
                }
            }
        }
        save_installed_data(test_data)  # type: ignore

        mock_installed_file.parent.mkdir.assert_called_once_with(exist_ok=True)
        mock_json_dump.assert_called_once_with(test_data, mock_file_handle, indent=2)

    @patch("fontpm.config.INSTALLED_FILE")
    @patch("builtins.open", side_effect=Exception("Write error"))
    @patch("fontpm.config.console.print")
    def test_save_installed_data_error(
        self,
        mock_print: MagicMock,
        _mock_file: MagicMock,
        mock_installed_file: MagicMock,
    ) -> None:
        """Test saving installed data with write error."""
        mock_installed_file.parent.mkdir = MagicMock()

        test_data = {
            "repo": {
                "font.ttf": {
                    "filename": "font.ttf",
                    "hash": "abc123",
                    "type": "static-ttf",
                    "version": "1.0",
                    "owner": "test",
                    "repo_name": "repo",
                }
            }
        }
        save_installed_data(test_data)  # type: ignore

        mock_print.assert_called_once_with(
            "[yellow]Warning: Could not save installed data: Write error[/yellow]"
        )
