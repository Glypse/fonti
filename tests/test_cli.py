import hashlib
from unittest.mock import MagicMock, patch

import pytest
import typer

from fontpm.cli import (
    config_format,
    config_github_token,
    config_path,
    config_test_auth,
    export,
    fix,
    import_fonts,
    install,
    purge,
    uninstall,
    update,
)


class TestInstall:
    """Test the install command."""

    @patch("fontpm.cli.install_single_repo")
    @patch("fontpm.cli.console")
    def test_install_success(
        self, _mock_console: MagicMock, mock_install: MagicMock
    ) -> None:
        """Test successful font installation."""
        mock_install.return_value = None

        install(
            ["owner/repo"],
            release="v1.0.0",
            format="otf,static-ttf",
            local=False,
            force=False,
            weights="",
            style="both",
        )

        assert mock_install.called

    @patch("fontpm.cli.install_single_repo")
    @patch("fontpm.cli.console")
    def test_install_failure(
        self, _mock_console: MagicMock, mock_install: MagicMock
    ) -> None:
        """Test failed font installation."""
        mock_install.side_effect = Exception("Install failed")

        with pytest.raises(Exception, match="Install failed"):
            install(
                repo=["owner/repo"],
                release="latest",
                format="otf,static-ttf",
                local=False,
                force=False,
                weights="",
                style="both",
            )

    @patch("fontpm.cli.fetch_google_fonts_repo")
    @patch("fontpm.cli.parse_repo")
    @patch("fontpm.cli.install_single_repo")
    @patch("fontpm.cli.console")
    def test_install_google_font(
        self,
        _mock_console: MagicMock,
        mock_install: MagicMock,
        mock_parse: MagicMock,
        mock_fetch: MagicMock,
    ) -> None:
        """Test installing a Google Font."""
        mock_fetch.return_value = ("google", "test-font", "extract_dir", False)
        mock_parse.return_value = ("google", "test-font")
        mock_install.return_value = None

        install(
            repo=["Test Font"],
            release="latest",
            format="otf,static-ttf",
            local=False,
            force=False,
            weights="",
            style="both",
        )

        mock_fetch.assert_called_once_with("Test Font")
        mock_install.assert_called_once()


class TestConfigCommands:
    """Test config subcommands."""

    @patch("fontpm.cli.set_config")
    def test_config_format_valid(self, mock_set_config: MagicMock) -> None:
        """Test setting valid config format."""
        config_format("otf,static-ttf")

        mock_set_config.assert_called_once_with("format", "otf,static-ttf")

    @patch("fontpm.cli.set_config")
    def test_config_format_invalid(self, mock_set_config: MagicMock) -> None:
        """Test setting invalid config format."""
        mock_set_config.side_effect = typer.Exit(1)

        with pytest.raises(typer.Exit):
            config_format("invalid")

    @patch("fontpm.cli.set_config")
    def test_config_path(self, mock_set_config: MagicMock) -> None:
        """Test setting config path."""
        config_path("/new/path")

        mock_set_config.assert_called_once_with("path", "/new/path")

    @patch("fontpm.cli.set_config")
    def test_config_github_token(self, mock_set_config: MagicMock) -> None:
        """Test setting GitHub token."""
        config_github_token("token123")

        mock_set_config.assert_called_once_with("github_token", "token123")

    @patch("fontpm.cli.typer")
    @patch("fontpm.cli.httpx")
    @patch("fontpm.cli.console")
    def test_config_test_auth_success(
        self, mock_console: MagicMock, mock_httpx: MagicMock, _mock_typer: MagicMock
    ) -> None:
        """Test successful auth test."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"login": "testuser"}
        mock_httpx.get.return_value = mock_response

        config_test_auth()

        mock_console.print.assert_called_with(
            "[green]Authentication successful! Logged in as: testuser[/green]"
        )

    @patch("fontpm.cli.httpx")
    @patch("fontpm.cli.console")
    def test_config_test_auth_failure(
        self, mock_console: MagicMock, mock_httpx: MagicMock
    ) -> None:
        """Test failed auth test."""
        mock_httpx.get.side_effect = Exception("Auth failed")

        config_test_auth()

        mock_console.print.assert_called_with(
            "[red]Error testing authentication: Auth failed[/red]"
        )


class TestUninstall:
    """Test the uninstall command."""

    @patch("fontpm.uninstaller.load_installed_data")
    @patch("fontpm.uninstaller.save_installed_data")
    @patch("fontpm.uninstaller.default_path")
    @patch("fontpm.uninstaller.console")
    def test_uninstall_success(
        self,
        mock_console: MagicMock,
        mock_path: MagicMock,
        _mock_save: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        """Test successful font uninstallation."""
        mock_load.return_value = {
            "repo": {
                "font.ttf": {
                    "filename": "font.ttf",
                    "hash": "testhash",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "repo",
                }
            }
        }
        # Simulate an actual file with readable bytes that match the stored hash
        data_bytes = b"testbytes"
        hash_val = hashlib.sha256(data_bytes).hexdigest()
        mock_load.return_value["repo"]["font.ttf"]["hash"] = hash_val
        font_file = MagicMock()
        font_file.exists.return_value = True
        font_file.read_bytes.return_value = data_bytes
        font_file.unlink = MagicMock()
        mock_path.__truediv__ = MagicMock(return_value=font_file)

        uninstall(["owner/repo"])

        mock_console.print.assert_called_with("[green]Uninstalled 1 font.[/green]")

    @patch("fontpm.config.load_installed_data")
    @patch("fontpm.uninstaller.console")
    def test_uninstall_not_found(
        self, mock_console: MagicMock, mock_load: MagicMock
    ) -> None:
        """Test uninstalling non-existent font."""
        mock_load.return_value = {}

        uninstall(["owner/repo"])

        mock_console.print.assert_called_with(
            "[yellow]No installed fonts data found.[/yellow]"
        )


class TestUpdate:
    """Test the update command."""

    @patch("fontpm.updater.install_single_repo")
    @patch("fontpm.updater.fetch_release_info")
    @patch("fontpm.updater.load_installed_data")
    @patch("fontpm.updater.console")
    def test_update_success(
        self,
        mock_console: MagicMock,
        mock_load: MagicMock,
        mock_fetch: MagicMock,
        mock_install: MagicMock,
    ) -> None:
        """Test successful font update."""
        mock_load.return_value = {
            "repo": {
                "font.ttf": {
                    "filename": "font.ttf",
                    "hash": "hash",
                    "type": "static-ttf",
                    "version": "v1.0.0",
                    "owner": "owner",
                    "repo_name": "repo",
                }
            }
        }
        mock_fetch.return_value = ("v2.0.0", None, "changelog", "owner", "repo")
        mock_install.return_value = None

        update(["owner/repo"], False)

        mock_install.assert_called_once()
        mock_console.print.assert_called_with(
            "[bold]Updating owner/repo from v1.0.0 to v2.0.0...[/bold]"
        )

    @patch("fontpm.updater.load_installed_data")
    @patch("fontpm.updater.console")
    def test_update_not_found(
        self, mock_console: MagicMock, mock_load: MagicMock
    ) -> None:
        """Test updating non-existent font."""
        mock_load.return_value = {}

        update(["owner/repo"], False)

        mock_console.print.assert_called_with(
            "[yellow]No installed fonts data found.[/yellow]"
        )


class TestExport:
    """Test the export command."""

    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.open")
    @patch("fontpm.library.console")
    def test_export_success(
        self, mock_console: MagicMock, mock_open: MagicMock, mock_load: MagicMock
    ) -> None:
        """Test successful export."""
        mock_load.return_value = {
            "repo": {
                "font.ttf": {
                    "filename": "font.ttf",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "repo",
                }
            }
        }

        # Provide a harmless file-like object to prevent actual file creation
        mock_file = MagicMock()
        mock_file.__enter__.return_value.write = MagicMock()
        mock_open.return_value = mock_file

        export("export.json", False)

        mock_console.print.assert_called_with("[green]Exported to export.json[/green]")

    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.open")
    @patch("fontpm.library.console")
    def test_export_write_error(
        self, mock_console: MagicMock, mock_open: MagicMock, mock_load: MagicMock
    ) -> None:
        """Test export write error."""
        mock_load.return_value = {
            "repo": {
                "font.ttf": {
                    "filename": "font.ttf",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "repo",
                }
            }
        }
        mock_open.side_effect = Exception("Write failed")

        with pytest.raises(typer.Exit):
            export("export.json", False)

        mock_console.print.assert_called_with(
            "[red]Error writing to export.json: Write failed[/red]"
        )


class TestImportFonts:
    """Test the import command."""

    @patch("fontpm.library.import_fonts")
    def test_import_success(self, mock_import_func: MagicMock) -> None:
        """Test successful import."""
        # CLI import invokes library.import_fonts internally; patch the library func
        import_fonts(file="import.json", force=False, local=False)

        mock_import_func.assert_called_once_with("import.json", False, False)

    @patch("fontpm.library.import_fonts")
    @patch("fontpm.library.console")
    def test_import_read_error(
        self, _mock_console: MagicMock, mock_import_func: MagicMock
    ) -> None:
        """Test import read error."""
        mock_import_func.side_effect = typer.Exit(1)

        with pytest.raises(typer.Exit):
            import_fonts(file="import.json", force=False, local=False)

        # library.import_fonts raised typer.Exit: CLI import likely didn't print any
        # extra message — ensure the exception bubbles up.


class TestFix:
    """Test the fix command."""

    @patch("typer.confirm", return_value=True)
    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.save_installed_data")
    @patch("fontpm.library.Path")
    def test_fix_success(
        self,
        _mock_confirm: MagicMock,
        mock_path: MagicMock,
        _mock_save: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        """Test successful fix."""
        mock_load.return_value = {
            "repo": {
                "font.ttf": {
                    "filename": "font.ttf",
                    "hash": "hash",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "repo",
                }
            }
        }
        mock_path.return_value.exists.return_value = True

        fix(backup=False, granular=False)

    @patch("typer.confirm", return_value=True)
    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.save_installed_data")
    @patch("fontpm.library.Path")
    def test_fix_broken_installation(
        self,
        _mock_confirm: MagicMock,
        mock_path: MagicMock,
        _mock_save: MagicMock,
        mock_load: MagicMock,
    ) -> None:
        """Test fixing broken installation."""
        mock_load.return_value = {
            "repo": {
                "font.ttf": {
                    "filename": "font.ttf",
                    "hash": "hash",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "repo",
                }
            }
        }
        mock_path.return_value.exists.return_value = False

        fix(backup=False, granular=False)


class TestPurge:
    """Test the cache purge command."""

    @patch("fontpm.cli.CACHE")
    @patch("fontpm.cli.console")
    def test_purge_success(
        self, mock_console: MagicMock, mock_cache: MagicMock
    ) -> None:
        """Test successful cache purge."""
        purge()

        mock_cache.clear.assert_called_once()
        mock_console.print.assert_called_with("[green]Cache purged.[/green]")

    @patch("fontpm.cli.CACHE")
    @patch("fontpm.cli.console")
    def test_purge_error(self, _mock_console: MagicMock, mock_cache: MagicMock) -> None:
        """Test cache purge error."""
        mock_cache.clear.side_effect = Exception("Purge failed")

        with pytest.raises(Exception, match="Purge failed"):
            purge()
