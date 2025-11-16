from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest
import typer

from fontpm.library import export_fonts, fix_fonts, import_fonts


class TestExportFonts:
    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.console.print")
    def test_export_fonts_no_data(
        self, mock_print: MagicMock, mock_load: MagicMock
    ) -> None:
        """Test exporting when no installed data exists."""
        mock_load.return_value = {}

        export_fonts("output.json", stdout=False)

        mock_print.assert_called_once_with(
            "[yellow]No installed fonts data found.[/yellow]"
        )

    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.console.print")
    def test_export_fonts_stdout(
        self, mock_print: MagicMock, mock_load: MagicMock
    ) -> None:
        """Test exporting to stdout."""
        mock_load.return_value = {
            "test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }

        export_fonts("", stdout=True)

        mock_print.assert_called_once()
        args = mock_print.call_args[0][0]
        assert '"test-repo"' in args
        assert '"font1.ttf"' in args

    @patch("builtins.open", new_callable=mock_open)
    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.console.print")
    def test_export_fonts_to_file_success(
        self, mock_print: MagicMock, mock_load: MagicMock, mock_file: MagicMock
    ) -> None:
        """Test exporting to file successfully."""
        mock_load.return_value = {
            "test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }

        export_fonts("output.json", stdout=False)

        mock_file.assert_called_once_with("output.json", "w")
        mock_print.assert_called_once_with("[green]Exported to output.json[/green]")

    @patch("builtins.open", side_effect=OSError("Write error"))
    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.console.print")
    def test_export_fonts_to_file_error(
        self, mock_print: MagicMock, mock_load: MagicMock, _mock_file: MagicMock
    ) -> None:
        """Test exporting to file with write error."""
        mock_load.return_value = {
            "test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "type": "static-ttf",
                    "version": "1.0.0",
                }
            }
        }

        with pytest.raises(typer.Exit):
            export_fonts("output.json", stdout=False)

        mock_print.assert_called_with(
            "[red]Error writing to output.json: Write error[/red]"
        )


class TestImportFonts:
    @patch("fontpm.library.install_single_repo")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=(
            '{"test-repo": {"font1.ttf": {"filename": "font1.ttf", '
            '"type": "static-ttf", "version": "1.0.0", "owner": "owner", '
            '"repo_name": "test-repo"}}}'
        ),
    )
    @patch("fontpm.library.console.print")
    def test_import_fonts_success_new_format(
        self, _mock_print: MagicMock, _mock_file: MagicMock, mock_install: MagicMock
    ) -> None:
        """Test importing with new format successfully."""
        import_fonts("input.json", force=False, local=False)

        mock_install.assert_called_once_with(
            "owner",
            "test-repo",
            "test-repo",
            "1.0.0",
            ["static-ttf"],
            Path.home() / "Library" / "Fonts",
            False,
            False,
            [],
            ["roman", "italic"],
        )

    @patch("fontpm.library.install_single_repo")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=(
            '{"owner/test-repo": {"font1.ttf": {"filename": "font1.ttf", '
            '"type": "static-ttf", "version": "1.0.0"}}}'
        ),
    )
    @patch("fontpm.library.console.print")
    def test_import_fonts_success_old_format(
        self, _mock_print: MagicMock, _mock_file: MagicMock, mock_install: MagicMock
    ) -> None:
        """Test importing with old format successfully."""
        import_fonts("input.json", force=False, local=False)

        mock_install.assert_called_once_with(
            "owner",
            "test-repo",
            "owner/test-repo",
            "1.0.0",
            ["static-ttf"],
            Path.home() / "Library" / "Fonts",
            False,
            False,
            [],
            ["roman", "italic"],
        )

    @patch("builtins.open", side_effect=OSError("Read error"))
    @patch("fontpm.library.console.print")
    def test_import_fonts_file_error(
        self, mock_print: MagicMock, _mock_file: MagicMock
    ) -> None:
        """Test importing with file read error."""
        with pytest.raises(typer.Exit):
            import_fonts("input.json", force=False, local=False)

        mock_print.assert_called_with("[red]Error loading input.json: Read error[/red]")

    @patch("fontpm.library.install_single_repo")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data=(
            '{"invalid-repo": {"font1.ttf": {"filename": "font1.ttf", '
            '"type": "static-ttf", "version": "1.0.0"}}}'
        ),
    )
    @patch("fontpm.library.console.print")
    def test_import_fonts_invalid_repo_old_format(
        self, mock_print: MagicMock, _mock_file: MagicMock, mock_install: MagicMock
    ) -> None:
        """Test importing with invalid repo format in old format."""
        import_fonts("input.json", force=False, local=False)

        mock_print.assert_called_with(
            "[red]Invalid repo format in import: invalid-repo[/red]"
        )
        mock_install.assert_not_called()


class TestFixFonts:
    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.console.print")
    def test_fix_fonts_no_data(
        self, mock_print: MagicMock, mock_load: MagicMock
    ) -> None:
        """Test fixing when no installed data exists."""
        mock_load.return_value = {}

        fix_fonts(backup=False, granular=False)

        mock_print.assert_called_once_with(
            "[yellow]No installed fonts data found.[/yellow]"
        )

    @patch("fontpm.library.save_installed_data")
    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.console.print")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("fontpm.library.TTFont")
    @patch("fontpm.library.is_variable_font", return_value=False)
    @patch("pathlib.Path.read_bytes", return_value=b"font data")
    @patch("fontpm.library.hashlib.sha256")
    @patch("typer.confirm", return_value=True)
    def test_fix_fonts_no_issues(
        self,
        _mock_confirm: MagicMock,
        mock_sha256: MagicMock,
        _mock_read_bytes: MagicMock,
        _mock_is_var: MagicMock,
        _mock_ttfont: MagicMock,
        _mock_exists: MagicMock,
        mock_print: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test fixing when no issues are found."""
        mock_load.return_value = {
            "owner/test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                    "hash": "hash123",
                }
            }
        }
        mock_sha256.return_value.hexdigest.return_value = "hash123"

        fix_fonts(backup=False, granular=False)

        mock_print.assert_called_once_with("[green]No issues found.[/green]")
        mock_save.assert_not_called()

    @patch("fontpm.library.save_installed_data")
    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.console.print")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("fontpm.library.TTFont")
    @patch("fontpm.library.is_variable_font", return_value=False)
    @patch("pathlib.Path.read_bytes", return_value=b"font data")
    @patch("fontpm.library.hashlib.sha256")
    @patch("typer.confirm", return_value=True)
    @patch("fontpm.library.install_single_repo")
    def test_fix_fonts_invalid_repo(
        self,
        _mock_install: MagicMock,
        _mock_confirm: MagicMock,
        mock_sha256: MagicMock,
        _mock_read_bytes: MagicMock,
        _mock_is_var: MagicMock,
        _mock_ttfont: MagicMock,
        _mock_exists: MagicMock,
        mock_print: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test fixing invalid repo."""
        mock_load.return_value = {
            "invalid-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }
        mock_sha256.return_value.hexdigest.return_value = "hash123"

        fix_fonts(backup=False, granular=False)

        # Should detect invalid repo and remove it
        mock_print.assert_any_call("[yellow]Found 1 issue(s):[/yellow]")
        mock_print.assert_any_call("  Remove invalid repo: invalid-repo")
        mock_print.assert_any_call("[green]Removed invalid repo: invalid-repo[/green]")
        mock_print.assert_any_call("[green]Fixed 1 issue(s).[/green]")
        mock_save.assert_called_once()

    @patch("fontpm.library.save_installed_data")
    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.console.print")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("fontpm.library.TTFont")
    @patch("fontpm.library.is_variable_font", return_value=False)
    @patch("pathlib.Path.read_bytes", return_value=b"font data")
    @patch("fontpm.library.hashlib.sha256")
    @patch("typer.confirm", return_value=True)
    @patch("fontpm.library.install_single_repo")
    def test_fix_fonts_type_extension_mismatch(
        self,
        _mock_install: MagicMock,
        _mock_confirm: MagicMock,
        mock_sha256: MagicMock,
        _mock_read_bytes: MagicMock,
        _mock_is_var: MagicMock,
        _mock_ttfont: MagicMock,
        _mock_exists: MagicMock,
        mock_print: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test fixing type/extension mismatch."""
        mock_load.return_value = {
            "owner/test-repo": {
                "font1.woff": {  # .woff but type static-ttf
                    "filename": "font1.woff",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }
        mock_sha256.return_value.hexdigest.return_value = "hash123"

        fix_fonts(backup=False, granular=False)

        mock_print.assert_any_call("[yellow]Found 1 issue(s):[/yellow]")
        mock_print.assert_any_call(
            "  Remove invalid entry: owner/test-repo/font1.woff (type/extension mismatch)"
        )
        mock_print.assert_any_call(
            "[green]Removed invalid entry: owner/test-repo/font1.woff (type/extension mismatch)[/green]"
        )
        mock_save.assert_called_once()

    @patch("fontpm.library.save_installed_data")
    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.console.print")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("fontpm.library.TTFont")
    @patch("fontpm.library.is_variable_font", return_value=False)
    @patch("pathlib.Path.read_bytes", return_value=b"font data")
    @patch("fontpm.library.hashlib.sha256")
    @patch("typer.confirm", return_value=True)
    @patch("fontpm.library.install_single_repo")
    def test_fix_fonts_duplicates(
        self,
        _mock_install: MagicMock,
        _mock_confirm: MagicMock,
        mock_sha256: MagicMock,
        _mock_read_bytes: MagicMock,
        _mock_is_var: MagicMock,
        _mock_ttfont: MagicMock,
        _mock_exists: MagicMock,
        mock_print: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test fixing duplicates."""
        mock_load.return_value = {
            "owner/repo1": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "repo1",
                }
            },
            "owner/repo2": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "repo2",
                }
            },
        }
        mock_sha256.return_value.hexdigest.return_value = "hash123"

        fix_fonts(backup=False, granular=False)

        mock_print.assert_any_call("[yellow]Found 2 issue(s):[/yellow]")
        mock_print.assert_any_call("  Remove duplicate font1.ttf from owner/repo2")
        mock_print.assert_any_call(
            "[green]Removed duplicate font1.ttf from owner/repo2[/green]"
        )
        mock_save.assert_called_once()

    @patch("fontpm.library.save_installed_data")
    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.console.print")
    @patch("pathlib.Path.exists", return_value=False)
    @patch("typer.confirm", return_value=True)
    @patch("fontpm.library.install_single_repo")
    def test_fix_fonts_missing_file(
        self,
        _mock_install: MagicMock,
        _mock_confirm: MagicMock,
        _mock_exists: MagicMock,
        mock_print: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test fixing missing file."""
        mock_load.return_value = {
            "owner/test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }

        fix_fonts(backup=False, granular=False)

        mock_print.assert_any_call("[yellow]Found 1 issue(s):[/yellow]")
        mock_print.assert_any_call(
            "  Reinstall repo (missing file(s)): owner/test-repo"
        )
        mock_print.assert_any_call(
            "[green]Reinstalled repo (missing file(s)): owner/test-repo[/green]"
        )
        mock_save.assert_called_once()

    @patch("fontpm.library.save_installed_data")
    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.console.print")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("fontpm.library.TTFont", side_effect=Exception("Invalid font"))
    @patch("typer.confirm", return_value=True)
    @patch("fontpm.library.install_single_repo")
    def test_fix_fonts_invalid_font(
        self,
        _mock_install: MagicMock,
        _mock_confirm: MagicMock,
        _mock_ttfont: MagicMock,
        _mock_exists: MagicMock,
        mock_print: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test fixing invalid font file."""
        mock_load.return_value = {
            "owner/test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }

        fix_fonts(backup=False, granular=False)

        mock_print.assert_any_call("[yellow]Found 1 issue(s):[/yellow]")
        mock_print.assert_any_call(
            "  Reinstall repo (invalid font file(s)): owner/test-repo"
        )
        mock_print.assert_any_call(
            "[green]Reinstalled repo (invalid font file(s)): owner/test-repo[/green]"
        )
        mock_save.assert_called_once()

    @patch("fontpm.library.save_installed_data")
    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.console.print")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("fontpm.library.TTFont")
    @patch("fontpm.library.is_variable_font", return_value=True)
    @patch("typer.confirm", return_value=True)
    @patch("fontpm.library.install_single_repo")
    def test_fix_fonts_variable_mismatch(
        self,
        _mock_install: MagicMock,
        _mock_confirm: MagicMock,
        _mock_is_var: MagicMock,
        _mock_ttfont: MagicMock,
        _mock_exists: MagicMock,
        mock_print: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test fixing variable/static mismatch."""
        mock_load.return_value = {
            "owner/test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "type": "static-ttf",  # Should be variable
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }

        fix_fonts(backup=False, granular=False)

        mock_print.assert_any_call("[yellow]Found 1 issue(s):[/yellow]")
        mock_print.assert_any_call(
            "  Reinstall repo (variable/static mismatch): owner/test-repo"
        )
        mock_print.assert_any_call(
            "[green]Reinstalled repo (variable/static mismatch): owner/test-repo[/green]"
        )
        mock_save.assert_called_once()

    @patch("fontpm.library.save_installed_data")
    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.console.print")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("fontpm.library.TTFont")
    @patch("fontpm.library.is_variable_font", return_value=False)
    @patch("pathlib.Path.read_bytes", return_value=b"modified font data")
    @patch("fontpm.library.hashlib.sha256")
    @patch("typer.confirm", return_value=True)
    @patch("fontpm.library.install_single_repo")
    def test_fix_fonts_hash_mismatch(
        self,
        _mock_install: MagicMock,
        _mock_confirm: MagicMock,
        mock_sha256: MagicMock,
        _mock_read_bytes: MagicMock,
        _mock_is_var: MagicMock,
        _mock_ttfont: MagicMock,
        _mock_exists: MagicMock,
        mock_print: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test fixing hash mismatch."""
        mock_load.return_value = {
            "owner/test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                    "hash": "oldhash",
                }
            }
        }
        mock_sha256.return_value.hexdigest.return_value = "newhash"

        fix_fonts(backup=False, granular=False)

        mock_print.assert_any_call("[yellow]Found 1 issue(s):[/yellow]")
        mock_print.assert_any_call(
            "  Update hash for modified file: owner/test-repo/font1.ttf"
        )
        mock_print.assert_any_call(
            "[green]Updated hash for modified file: owner/test-repo/font1.ttf[/green]"
        )
        mock_save.assert_called_once()

    @patch("shutil.copy")
    @patch("fontpm.library.save_installed_data")
    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.console.print")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("fontpm.library.TTFont")
    @patch("fontpm.library.is_variable_font", return_value=False)
    @patch("pathlib.Path.read_bytes", return_value=b"font data")
    @patch("fontpm.library.hashlib.sha256")
    @patch("typer.confirm", return_value=True)
    @patch("fontpm.library.install_single_repo")
    def test_fix_fonts_backup_success(
        self,
        _mock_install: MagicMock,
        _mock_confirm: MagicMock,
        mock_sha256: MagicMock,
        _mock_read_bytes: MagicMock,
        _mock_is_var: MagicMock,
        _mock_ttfont: MagicMock,
        _mock_exists: MagicMock,
        mock_print: MagicMock,
        mock_load: MagicMock,
        _mock_save: MagicMock,
        mock_copy: MagicMock,
    ) -> None:
        """Test fixing with backup creation."""
        mock_load.return_value = {
            "invalid-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }
        mock_sha256.return_value.hexdigest.return_value = "hash123"

        fix_fonts(backup=True, granular=False)

        mock_copy.assert_called_once()
        mock_print.assert_any_call(
            f"[green]Backup created: {Path.home() / '.fontpm' / 'installed.json.backup'}[/green]"
        )

    @patch("shutil.copy", side_effect=OSError("Copy error"))
    @patch("fontpm.library.load_installed_data")
    @patch("fontpm.library.console.print")
    @patch("typer.confirm", return_value=True)
    @patch("fontpm.library.install_single_repo")
    def test_fix_fonts_backup_error(
        self,
        _mock_install: MagicMock,
        _mock_confirm: MagicMock,
        mock_print: MagicMock,
        mock_load: MagicMock,
        _mock_copy: MagicMock,
    ) -> None:
        """Test fixing with backup creation error."""
        mock_load.return_value = {
            "owner/test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }

        with pytest.raises(typer.Exit):
            fix_fonts(backup=True, granular=False)

        mock_print.assert_called_with("[red]Failed to create backup: Copy error[/red]")
