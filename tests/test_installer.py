from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

from fontpm.installer import install_fonts, install_single_repo


class TestInstallFonts:
    @patch("fontpm.installer.save_installed_data")
    @patch("fontpm.installer.load_installed_data")
    @patch("fontpm.installer.shutil.move")
    @patch("fontpm.installer.console.print")
    def test_install_fonts_local(
        self,
        mock_print: MagicMock,
        mock_move: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test installing fonts locally (no installed data update)."""
        selected_fonts: List[Path] = [Path("font1.ttf"), Path("font2.otf")]
        dest_dir = Path("/tmp/fonts")
        repo_name = "test-repo"
        repo_key = "owner/test-repo"
        owner = "owner"
        version = "1.0.0"
        selected_pri = "static-ttf"
        local = True

        install_fonts(
            selected_fonts,
            dest_dir,
            repo_name,
            repo_key,
            owner,
            version,
            selected_pri,
            local,
        )

        # Should move fonts
        assert mock_move.call_count == 2
        mock_move.assert_any_call("font1.ttf", str(dest_dir / "font1.ttf"))
        mock_move.assert_any_call("font2.otf", str(dest_dir / "font2.otf"))

        # Should not load/save installed data
        mock_load.assert_not_called()
        mock_save.assert_not_called()

        # Should print success message
        mock_print.assert_called_once_with(
            "[green]Moved 2 fonts from owner/test-repo to: /tmp/fonts[/green]"
        )

    @patch("fontpm.installer.save_installed_data")
    @patch("fontpm.installer.load_installed_data")
    @patch("fontpm.installer.shutil.move")
    @patch("fontpm.installer.console.print")
    @patch("fontpm.installer.hashlib.sha256")
    @patch("pathlib.Path.read_bytes", return_value=b"font data")
    def test_install_fonts_global(
        self,
        _mock_read_bytes: MagicMock,
        mock_sha256: MagicMock,
        mock_print: MagicMock,
        mock_move: MagicMock,
        mock_load: MagicMock,
        mock_save: MagicMock,
    ) -> None:
        """Test installing fonts globally (with installed data update)."""
        selected_fonts: List[Path] = [Path("font1.ttf")]
        dest_dir = Path("/tmp/fonts")
        repo_name = "test-repo"
        repo_key = "owner/test-repo"
        owner = "owner"
        version = "1.0.0"
        selected_pri = "static-ttf"
        local = False

        mock_load.return_value = {}
        mock_sha256.return_value.hexdigest.return_value = "hash"

        install_fonts(
            selected_fonts,
            dest_dir,
            repo_name,
            repo_key,
            owner,
            version,
            selected_pri,
            local,
        )

        # Should move font
        mock_move.assert_called_once_with("font1.ttf", str(dest_dir / "font1.ttf"))

        # Should update installed data
        mock_load.assert_called_once()
        mock_save.assert_called_once()
        saved_data = mock_save.call_args[0][0]
        assert "owner/test-repo" in saved_data
        assert "font1.ttf" in saved_data["owner/test-repo"]
        entry = saved_data["owner/test-repo"]["font1.ttf"]
        assert entry["filename"] == "font1.ttf"
        assert entry["type"] == "static-ttf"
        assert entry["version"] == "1.0.0"
        assert entry["owner"] == "owner"
        assert entry["repo_name"] == "test-repo"

        # Should print success message
        mock_print.assert_called_once_with(
            "[green]Moved 1 font from owner/test-repo to: /tmp/fonts[/green]"
        )

    @patch("fontpm.installer.console.print")
    def test_install_fonts_empty(self, mock_print: MagicMock) -> None:
        """Test installing with no fonts."""
        selected_fonts = []
        dest_dir = Path("/tmp/fonts")
        repo_name = "test-repo"
        repo_key = "owner/test-repo"
        owner = "owner"
        version = "1.0.0"
        selected_pri = "static-ttf"
        local = True

        install_fonts(
            selected_fonts,  # pyright: ignore[reportUnknownArgumentType]
            dest_dir,
            repo_name,
            repo_key,
            owner,
            version,
            selected_pri,
            local,
        )

        # Should print warning
        mock_print.assert_called_once_with(
            "[yellow]No font files found in the archive for owner/test-repo.[/yellow]"
        )


class TestInstallSingleRepo:
    @patch("fontpm.installer.shutil.rmtree")
    @patch("fontpm.installer.install_fonts")
    @patch("fontpm.installer.select_fonts")
    @patch("fontpm.installer.categorize_fonts")
    @patch("fontpm.installer.get_or_download_and_extract_archive")
    @patch("fontpm.installer.select_archive_asset")
    @patch("fontpm.installer.fetch_release_info")
    @patch("fontpm.installer.console.print")
    @patch("fontpm.installer.console.status")
    def test_install_single_repo_latest_release(
        self,
        _mock_status: MagicMock,
        _mock_print: MagicMock,
        mock_fetch: MagicMock,
        mock_select_asset: MagicMock,
        mock_extract: MagicMock,
        mock_categorize: MagicMock,
        mock_select_fonts: MagicMock,
        mock_install: MagicMock,
        mock_rmtree: MagicMock,
    ) -> None:
        """Test installing from latest release."""
        # Mock fetch_release_info
        mock_fetch.return_value = (
            "1.0.0",
            [{"name": "archive.zip", "browser_download_url": "url", "size": 100}],
            "",
            "owner",
            "repo",
        )

        # Mock select_archive_asset
        mock_select_asset.return_value = {
            "name": "archive.zip",
            "browser_download_url": "url",
            "size": 100,
        }

        # Mock extract
        extract_dir = Path("/tmp/extract")
        mock_extract.return_value = extract_dir

        # Mock categorize and select
        mock_categorize.return_value = {"static-ttf": [Path("font.ttf")]}
        mock_select_fonts.return_value = ([Path("font.ttf")], "static-ttf")

        install_single_repo(
            owner="owner",
            repo_name="repo",
            repo_key="owner/repo",
            release="latest",
            priorities=["static-ttf"],
            dest_dir=Path("/tmp/fonts"),
            local=True,
            force=False,
            weights=[],
            styles=[],
        )

        # Should fetch release info
        mock_fetch.assert_called_once_with("owner", "repo", "latest")

        # Should select asset
        mock_select_asset.assert_called_once()

        # Should extract archive
        mock_extract.assert_called_once()

        # Should categorize and select fonts
        mock_categorize.assert_called_once()
        mock_select_fonts.assert_called_once_with(
            {"static-ttf": [Path("font.ttf")]}, ["static-ttf"], [], []
        )

        # Should install fonts
        mock_install.assert_called_once_with(
            [Path("font.ttf")],
            Path("/tmp/fonts"),
            "repo",
            "owner/repo",
            "owner",
            "1.0.0",
            "static-ttf",
            True,
        )

        # Should clean up
        mock_rmtree.assert_called_once_with(str(extract_dir))

    @patch("fontpm.installer.shutil.rmtree")
    @patch("fontpm.installer.install_fonts")
    @patch("fontpm.installer.select_fonts")
    @patch("fontpm.installer.categorize_fonts")
    @patch("fontpm.installer.download_fonts_dir")
    @patch("fontpm.installer.get_fonts_dir_version")
    @patch("fontpm.installer.fetch_release_info")
    @patch("fontpm.installer.console.print")
    @patch("fontpm.installer.console.status")
    @patch("fontpm.installer.CACHE")
    def test_install_single_repo_fallback_to_fonts_dir(
        self,
        mock_cache: MagicMock,
        _mock_status: MagicMock,
        _mock_print: MagicMock,
        mock_fetch: MagicMock,
        mock_get_version: MagicMock,
        mock_download: MagicMock,
        mock_categorize: MagicMock,
        mock_select_fonts: MagicMock,
        mock_install: MagicMock,
        mock_rmtree: MagicMock,
    ) -> None:
        """Test fallback to fonts directory when no releases found."""
        import httpx

        # Mock fetch_release_info to raise 404
        mock_fetch.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )

        # Mock fonts dir version and download
        mock_get_version.return_value = "latest"
        extract_dir = Path("/tmp/fonts_dir")
        mock_download.return_value = extract_dir
        mock_cache.__contains__.return_value = False

        # Mock categorize and select
        mock_categorize.return_value = {"static-ttf": [Path("font.ttf")]}
        mock_select_fonts.return_value = ([Path("font.ttf")], "static-ttf")

        install_single_repo(
            owner="owner",
            repo_name="repo",
            repo_key="owner/repo",
            release="latest",
            priorities=["static-ttf"],
            dest_dir=Path("/tmp/fonts"),
            local=True,
            force=False,
            weights=[],
            styles=[],
        )

        # Should try fetch_release_info
        mock_fetch.assert_called_once()

        # Should get fonts dir version and download
        mock_get_version.assert_called_once_with("owner", "repo")
        mock_download.assert_called_once_with("owner", "repo")

        # Should categorize and select fonts
        mock_categorize.assert_called_once()
        mock_select_fonts.assert_called_once()

        # Should install fonts
        mock_install.assert_called_once()

        # Should clean up
        mock_rmtree.assert_called_once_with(str(extract_dir))

    @patch("fontpm.installer.console.print")
    def test_install_single_repo_woff_global_warning(
        self, mock_print: MagicMock
    ) -> None:
        """Test warning for WOFF fonts in global install."""
        install_single_repo(
            owner="owner",
            repo_name="repo",
            repo_key="owner/repo",
            release="latest",
            priorities=["static-woff"],
            dest_dir=Path("/tmp/fonts"),
            local=False,
            force=False,
            weights=[],
            styles=[],
        )

        # Should print installing message and warning, then return
        assert mock_print.call_count == 2
        mock_print.assert_any_call("[bold]Installing from owner/repo...[/bold]")
        mock_print.assert_called_with(
            "[yellow]Installing WOFF/WOFF2 fonts globally is not recommended. "
            "Use --force to proceed.[/yellow]"
        )

    @patch("fontpm.installer.shutil.rmtree")
    @patch("fontpm.installer.install_fonts")
    @patch("fontpm.installer.select_fonts")
    @patch("fontpm.installer.categorize_fonts")
    @patch("fontpm.installer.get_subdirectory_version")
    @patch("fontpm.installer.console.print")
    @patch("fontpm.installer.console.status")
    def test_install_single_repo_subdirectory(
        self,
        _mock_status: MagicMock,
        _mock_print: MagicMock,
        mock_get_version: MagicMock,
        mock_categorize: MagicMock,
        mock_select_fonts: MagicMock,
        mock_install: MagicMock,
        mock_rmtree: MagicMock,
    ) -> None:
        """Test installing from subdirectory."""
        # Mock subdirectory version
        mock_get_version.return_value = "2023-01-01"

        # Mock categorize and select
        extract_dir = Path("/tmp/extract")
        mock_categorize.return_value = {"static-ttf": [Path("font.ttf")]}
        mock_select_fonts.return_value = ([Path("font.ttf")], "static-ttf")

        install_single_repo(
            owner="owner",
            repo_name="repo",
            repo_key="owner/repo",
            release="latest",
            priorities=["static-ttf"],
            dest_dir=Path("/tmp/fonts"),
            local=True,
            force=False,
            weights=[],
            styles=[],
            is_subdirectory=True,
            pre_extract_dir=extract_dir,
        )

        # Should get subdirectory version
        mock_get_version.assert_called_once_with("repo")

        # Should categorize and select fonts
        mock_categorize.assert_called_once()
        mock_select_fonts.assert_called_once()

        # Should install fonts
        mock_install.assert_called_once_with(
            [Path("font.ttf")],
            Path("/tmp/fonts"),
            "repo",
            "owner/repo",
            "owner",
            "2023-01-01",
            "static-ttf",
            True,
        )

        # Should clean up even for subdirectory
        mock_rmtree.assert_called_once_with(str(extract_dir))
