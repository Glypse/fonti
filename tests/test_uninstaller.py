from unittest.mock import MagicMock, patch

from fontpm.uninstaller import uninstall_fonts


class TestUninstallFonts:
    @patch("fontpm.uninstaller.save_installed_data")
    @patch("fontpm.uninstaller.load_installed_data")
    @patch("fontpm.uninstaller.console.print")
    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("pathlib.Path.read_bytes", return_value=b"font data")
    @patch("fontpm.uninstaller.hashlib.sha256")
    def test_uninstall_fonts_success(
        self,
        mock_sha256: MagicMock,
        _mock_read_bytes: MagicMock,
        _mock_exists: MagicMock,
        mock_unlink: MagicMock,
        mock_print: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test successful uninstallation with matching hashes."""
        mock_load.return_value = {
            "test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash123",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }
        mock_sha256.return_value.hexdigest.return_value = "hash123"

        uninstall_fonts(["owner/test-repo"], force=False)

        # Should delete the file
        mock_unlink.assert_called_once()

        # Should update installed data
        mock_save.assert_called_once_with({})

        # Should print success
        mock_print.assert_called_with("[green]Uninstalled 1 font.[/green]")

    @patch("fontpm.uninstaller.save_installed_data")
    @patch("fontpm.uninstaller.load_installed_data")
    @patch("fontpm.uninstaller.console.print")
    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("pathlib.Path.read_bytes", return_value=b"font data")
    @patch("fontpm.uninstaller.hashlib.sha256")
    def test_uninstall_fonts_force_mismatch(
        self,
        mock_sha256: MagicMock,
        _mock_read_bytes: MagicMock,
        _mock_exists: MagicMock,
        mock_unlink: MagicMock,
        mock_print: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test uninstallation with force when hashes don't match."""
        mock_load.return_value = {
            "test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash123",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }
        mock_sha256.return_value.hexdigest.return_value = "different_hash"

        uninstall_fonts(["owner/test-repo"], force=True)

        # Should delete the file despite hash mismatch
        mock_unlink.assert_called_once()

        # Should update installed data
        mock_save.assert_called_once_with({})

        # Should print success
        mock_print.assert_called_with("[green]Uninstalled 1 font.[/green]")

    @patch("fontpm.uninstaller.save_installed_data")
    @patch("fontpm.uninstaller.load_installed_data")
    @patch("fontpm.uninstaller.console.print")
    @patch("pathlib.Path.exists", return_value=False)
    def test_uninstall_fonts_missing_file(
        self,
        _mock_exists: MagicMock,
        mock_print: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test uninstallation when font file is missing."""
        mock_load.return_value = {
            "test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash123",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }

        uninstall_fonts(["owner/test-repo"], force=False)

        # Should not save (font still in data)
        mock_save.assert_called_once()
        saved_data = mock_save.call_args[0][0]
        assert "test-repo" in saved_data

        # Should print warning
        mock_print.assert_any_call(
            "[yellow]Font font1.ttf not found in /Users/sacha/Library/Fonts.[/yellow]"
        )

    @patch("fontpm.uninstaller.save_installed_data")
    @patch("fontpm.uninstaller.load_installed_data")
    @patch("fontpm.uninstaller.console.print")
    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("pathlib.Path.read_bytes", side_effect=OSError("Read error"))
    def test_uninstall_fonts_hash_error(
        self,
        _mock_read_bytes: MagicMock,
        _mock_exists: MagicMock,
        mock_unlink: MagicMock,
        mock_print: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test uninstallation when hashing fails."""
        mock_load.return_value = {
            "test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash123",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }

        uninstall_fonts(["owner/test-repo"], force=False)

        # Should not delete the file
        mock_unlink.assert_not_called()

        # Should not save (font still in data)
        mock_save.assert_called_once()
        saved_data = mock_save.call_args[0][0]
        assert "test-repo" in saved_data

        # Should print error
        mock_print.assert_any_call(
            "[yellow]Could not hash font1.ttf: Read error[/yellow]"
        )

    @patch("fontpm.uninstaller.save_installed_data")
    @patch("fontpm.uninstaller.load_installed_data")
    @patch("fontpm.uninstaller.console.print")
    def test_uninstall_fonts_no_data(
        self,
        mock_print: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test uninstallation when no installed data exists."""
        mock_load.return_value = {}

        uninstall_fonts(["owner/test-repo"], force=False)

        # Should not save
        mock_save.assert_not_called()

        # Should print warning
        mock_print.assert_called_with("[yellow]No installed fonts data found.[/yellow]")

    @patch("fontpm.uninstaller.save_installed_data")
    @patch("fontpm.uninstaller.load_installed_data")
    @patch("fontpm.uninstaller.console.print")
    def test_uninstall_fonts_invalid_repo(
        self,
        mock_print: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test uninstallation with invalid repo format."""
        mock_load.return_value = {}

        uninstall_fonts(["invalid-repo-format"], force=False)

        # Should not save
        mock_save.assert_not_called()

        # Should print error
        mock_print.assert_called_with("[yellow]No installed fonts data found.[/yellow]")

    @patch("fontpm.uninstaller.save_installed_data")
    @patch("fontpm.uninstaller.load_installed_data")
    @patch("fontpm.uninstaller.console.print")
    @patch("pathlib.Path.unlink", side_effect=OSError("Delete error"))
    @patch("pathlib.Path.exists", return_value=True)
    @patch("pathlib.Path.read_bytes", return_value=b"font data")
    @patch("fontpm.uninstaller.hashlib.sha256")
    def test_uninstall_fonts_delete_error(
        self,
        mock_sha256: MagicMock,
        _mock_read_bytes: MagicMock,
        _mock_exists: MagicMock,
        mock_unlink: MagicMock,
        mock_print: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test uninstallation when file deletion fails."""
        mock_load.return_value = {
            "test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash123",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }
        mock_sha256.return_value.hexdigest.return_value = "hash123"

        uninstall_fonts(["owner/test-repo"], force=False)

        # Should try to delete
        mock_unlink.assert_called_once()

        # Should not save (font still in data)
        mock_save.assert_called_once()
        saved_data = mock_save.call_args[0][0]
        assert "test-repo" in saved_data

        # Should print error
        mock_print.assert_any_call(
            "[red]Could not delete font1.ttf: Delete error[/red]"
        )

    @patch("fontpm.uninstaller.save_installed_data")
    @patch("fontpm.uninstaller.load_installed_data")
    @patch("fontpm.uninstaller.console.print")
    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.exists", return_value=True)
    @patch("pathlib.Path.read_bytes", return_value=b"font data")
    @patch("fontpm.uninstaller.hashlib.sha256")
    def test_uninstall_fonts_modified_no_force(
        self,
        mock_sha256: MagicMock,
        _mock_read_bytes: MagicMock,
        _mock_exists: MagicMock,
        mock_unlink: MagicMock,
        mock_print: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test uninstallation when font is modified and force is not used."""
        mock_load.return_value = {
            "test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash123",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }
        mock_sha256.return_value.hexdigest.return_value = "modified_hash"

        uninstall_fonts(["owner/test-repo"], force=False)

        # Should not delete
        mock_unlink.assert_not_called()

        # Should not save (font still in data)
        mock_save.assert_called_once()
        saved_data = mock_save.call_args[0][0]
        assert "test-repo" in saved_data

        # Should print warning
        mock_print.assert_any_call(
            "[yellow]Font font1.ttf has been modified. Use --force to delete.[/yellow]"
        )
