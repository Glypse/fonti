from pathlib import Path
from unittest.mock import MagicMock, patch

import fontpm.config as config
from fontpm.updater import update_fonts


class TestUpdateFonts:
    @patch("fontpm.updater.install_single_repo")
    @patch("fontpm.updater.save_installed_data")
    @patch("fontpm.updater.load_installed_data")
    @patch("fontpm.updater.fetch_release_info")
    @patch("fontpm.updater.console.print")
    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.exists", return_value=True)
    def test_update_fonts_single_repo_newer_version(
        self,
        _mock_exists: MagicMock,
        mock_unlink: MagicMock,
        mock_print: MagicMock,
        mock_fetch: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
        mock_install: MagicMock,
    ) -> None:
        """Test updating a single repo with a newer version available."""
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
        mock_fetch.return_value = ("2.0.0", "", "Changelog here", "owner", "test-repo")

        update_fonts(["owner/test-repo"], changelog=True)

        # Should fetch release info
        mock_fetch.assert_called_once_with("owner", "test-repo", "latest")

        # Should uninstall old font
        mock_unlink.assert_called_once()

        # Should save empty data temporarily
        mock_save.assert_called_once_with({})

        # Should install new version
        mock_install.assert_called_once_with(
            "owner",
            "test-repo",
            "test-repo",
            "latest",
            config.default_priorities,
            Path("/Users/sacha/Library/Fonts"),
            False,
            True,
            [],
            ["roman", "italic"],
        )

        # Should print update message and changelog
        mock_print.assert_any_call(
            "[bold]Updating owner/test-repo from 1.0.0 to 2.0.0...[/bold]"
        )
        mock_print.assert_any_call("[bold]Changelog for owner/test-repo 2.0.0:[/bold]")
        mock_print.assert_any_call("Changelog here")

    @patch("fontpm.updater.install_single_repo")
    @patch("fontpm.updater.save_installed_data")
    @patch("fontpm.updater.load_installed_data")
    @patch("fontpm.updater.fetch_release_info")
    @patch("fontpm.updater.console.print")
    def test_update_fonts_all_repos_no_updates(
        self,
        mock_print: MagicMock,
        mock_fetch: MagicMock,
        mock_load: MagicMock,
        _mock_save: MagicMock,
        mock_install: MagicMock,
    ) -> None:
        """Test updating all repos when no updates are available."""
        mock_load.return_value = {
            "test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash123",
                    "type": "static-ttf",
                    "version": "2.0.0",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }
        mock_fetch.return_value = ("2.0.0", "", "", "owner", "test-repo")

        update_fonts([], changelog=False)

        # Should fetch release info
        mock_fetch.assert_called_once_with("owner", "test-repo", "latest")

        # Should not install anything
        mock_install.assert_not_called()

        # Should print up to date message
        mock_print.assert_called_with(
            "[dim]owner/test-repo is up to date (2.0.0).[/dim]"
        )

    @patch("fontpm.updater.install_single_repo")
    @patch("fontpm.updater.save_installed_data")
    @patch("fontpm.updater.load_installed_data")
    @patch("fontpm.updater.get_fonts_dir_version")
    @patch("fontpm.updater.fetch_release_info")
    @patch("fontpm.updater.console.print")
    def test_update_fonts_fallback_to_fonts_dir(
        self,
        _mock_print: MagicMock,
        mock_fetch: MagicMock,
        mock_get_version: MagicMock,
        mock_load: MagicMock,
        _mock_save: MagicMock,
        mock_install: MagicMock,
    ) -> None:
        """Test updating with fallback to fonts directory when releases fail."""
        import httpx

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
        mock_fetch.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        mock_get_version.return_value = "2.0.0"

        update_fonts(["owner/test-repo"], changelog=False)

        # Should try fetch_release_info
        mock_fetch.assert_called_once_with("owner", "test-repo", "latest")

        # Should fallback to get_fonts_dir_version
        mock_get_version.assert_called_once_with("owner", "test-repo")

        # Should install new version
        mock_install.assert_called_once()

    @patch("fontpm.updater.install_single_repo")
    @patch("fontpm.updater.save_installed_data")
    @patch("fontpm.updater.load_installed_data")
    @patch("fontpm.updater.fetch_release_info")
    @patch("fontpm.updater.console.print")
    def test_update_fonts_google_fonts_repo(
        self,
        mock_print: MagicMock,
        mock_fetch: MagicMock,
        mock_load: MagicMock,
        _mock_save: MagicMock,
        mock_install: MagicMock,
    ) -> None:
        """Test updating Google Fonts repo (should skip on fetch error)."""
        mock_load.return_value = {
            "test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash123",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "thegooglefontsrepo",
                    "repo_name": "test-repo",
                }
            }
        }
        import httpx

        mock_fetch.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )

        update_fonts(["thegooglefontsrepo/test-repo"], changelog=False)

        # Should try fetch_release_info
        mock_fetch.assert_called_once_with("thegooglefontsrepo", "test-repo", "latest")

        # Should not try fonts dir fallback
        # Should not install
        mock_install.assert_not_called()

        # Should print warning and up to date (since fetch failed but repo is still checked)
        from unittest.mock import call

        mock_print.assert_has_calls(
            [
                call(
                    "[yellow]Could not fetch latest for thegooglefontsrepo/test-repo: 404[/yellow]"
                ),
                call("[dim]thegooglefontsrepo/test-repo is up to date (1.0.0).[/dim]"),
            ]
        )

    @patch("fontpm.updater.install_single_repo")
    @patch("fontpm.updater.save_installed_data")
    @patch("fontpm.updater.load_installed_data")
    @patch("fontpm.updater.fetch_release_info")
    @patch("fontpm.updater.console.print")
    def test_update_fonts_no_installed_data(
        self,
        mock_print: MagicMock,
        mock_fetch: MagicMock,
        mock_load: MagicMock,
        _mock_save: MagicMock,
        mock_install: MagicMock,
    ) -> None:
        """Test updating when no installed data exists."""
        mock_load.return_value = {}

        update_fonts([], changelog=False)

        # Should not fetch anything
        mock_fetch.assert_not_called()

        # Should not install
        mock_install.assert_not_called()

        # Should print warning
        mock_print.assert_called_with("[yellow]No installed fonts data found.[/yellow]")

    @patch("fontpm.updater.install_single_repo")
    @patch("fontpm.updater.save_installed_data")
    @patch("fontpm.updater.load_installed_data")
    @patch("fontpm.updater.fetch_release_info")
    @patch("fontpm.updater.console.print")
    def test_update_fonts_repo_not_found(
        self,
        mock_print: MagicMock,
        mock_fetch: MagicMock,
        mock_load: MagicMock,
        _mock_save: MagicMock,
        mock_install: MagicMock,
    ) -> None:
        """Test updating a repo that is not installed."""
        mock_load.return_value = {
            "other-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash123",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "other-repo",
                }
            }
        }

        update_fonts(["owner/not-installed"], changelog=False)

        # Should not fetch
        mock_fetch.assert_not_called()

        # Should not install
        mock_install.assert_not_called()

        # Should print warning
        mock_print.assert_called_with(
            "[yellow]No fonts installed from owner/not-installed.[/yellow]"
        )

    @patch("fontpm.updater.install_single_repo")
    @patch("fontpm.updater.save_installed_data")
    @patch("fontpm.updater.load_installed_data")
    @patch("fontpm.updater.fetch_release_info")
    @patch("fontpm.updater.console.print")
    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.exists", return_value=True)
    def test_update_fonts_date_version_comparison(
        self,
        _mock_exists: MagicMock,
        _mock_unlink: MagicMock,
        mock_print: MagicMock,
        mock_fetch: MagicMock,
        mock_load: MagicMock,
        _mock_save: MagicMock,
        mock_install: MagicMock,
    ) -> None:
        """Test updating with date-based version comparison (fallback)."""
        mock_load.return_value = {
            "test-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash123",
                    "type": "static-ttf",
                    "version": "2023-01-01",
                    "owner": "owner",
                    "repo_name": "test-repo",
                }
            }
        }
        mock_fetch.return_value = ("2023-12-01", "", "", "owner", "test-repo")

        update_fonts(["owner/test-repo"], changelog=False)

        # Should install new version (date comparison)
        mock_install.assert_called_once()

        # Should print update message
        mock_print.assert_any_call(
            "[bold]Updating owner/test-repo from 2023-01-01 to 2023-12-01...[/bold]"
        )

    @patch("fontpm.updater.install_single_repo")
    @patch("fontpm.updater.save_installed_data")
    @patch("fontpm.updater.load_installed_data")
    @patch("fontpm.updater.fetch_release_info")
    @patch("fontpm.updater.console.print")
    def test_update_fonts_invalid_repo_format(
        self,
        mock_print: MagicMock,
        mock_fetch: MagicMock,
        mock_load: MagicMock,
        _mock_save: MagicMock,
        mock_install: MagicMock,
    ) -> None:
        """Test updating a repo with invalid format."""
        mock_load.return_value = {
            "other-repo": {
                "font1.ttf": {
                    "filename": "font1.ttf",
                    "hash": "hash123",
                    "type": "static-ttf",
                    "version": "1.0.0",
                    "owner": "owner",
                    "repo_name": "other-repo",
                }
            }
        }

        update_fonts(["invalid-format"], changelog=False)

        # Should not fetch
        mock_fetch.assert_not_called()

        # Should not install
        mock_install.assert_not_called()

        # Should print error
        mock_print.assert_called_with(
            "[yellow]No fonts installed from invalid-format.[/yellow]"
        )
