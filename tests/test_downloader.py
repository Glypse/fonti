from pathlib import Path
from typing import TYPE_CHECKING, List, cast
from unittest.mock import MagicMock, mock_open, patch

import pytest

if TYPE_CHECKING:
    from fontpm.types import Asset

from fontpm.downloader import (
    _get_safe_members,  # type: ignore
    _is_safe_archive_path,  # type: ignore
    download_fonts_dir,
    fetch_release_info,
    get_base_and_ext,
    get_fonts_dir_version,
    get_or_download_and_extract_archive,
    get_subdirectory_version,
    select_archive_asset,
)


class TestIsSafeArchivePath:
    def test_safe_relative_path(self, tmp_path: Path) -> None:
        assert _is_safe_archive_path("safe/file.txt", tmp_path) is True

    def test_absolute_path(self, tmp_path: Path) -> None:
        assert _is_safe_archive_path("/absolute/path", tmp_path) is False

    def test_path_with_dots(self, tmp_path: Path) -> None:
        assert _is_safe_archive_path("../escape", tmp_path) is False
        assert _is_safe_archive_path("dir/../escape", tmp_path) is False

    def test_empty_path(self, tmp_path: Path) -> None:
        assert _is_safe_archive_path("", tmp_path) is False

    def test_deep_path(self, tmp_path: Path) -> None:
        deep_path = "/".join([f"level{i}" for i in range(20)])
        assert _is_safe_archive_path(deep_path, tmp_path) is False

    def test_normal_depth(self, tmp_path: Path) -> None:
        normal_path = "/".join([f"level{i}" for i in range(10)])
        assert _is_safe_archive_path(normal_path, tmp_path) is True

    def test_path_escaping_directory(self, tmp_path: Path) -> None:
        # This would try to go outside, but since we resolve and check prefix, it should fail
        # But in test, tmp_path is /tmp/something, and ".." would go to /tmp, which might start with /tmp
        # Actually, the function checks if resolved_full_path starts with resolved_extract_dir
        # For tmp_path = /tmp/test123, and path = "../../../etc/passwd"
        # resolved_full_path = /tmp/test123/../../../etc/passwd = /etc/passwd
        # which does not start with /tmp/test123, so False
        assert _is_safe_archive_path("../../../etc/passwd", tmp_path) is False


class TestGetSafeMembers:
    def test_zip_safe_members(self, tmp_path: Path) -> None:
        mock_zip = MagicMock()
        mock_zip.namelist.return_value = [
            "safe.txt",
            "../unsafe.txt",
            "subdir/safe.txt",
        ]

        with patch("fontpm.downloader._is_safe_archive_path") as mock_safe:
            mock_safe.side_effect = lambda path, _: not path.startswith("../")  # type: ignore

            result = _get_safe_members(mock_zip, "zip", tmp_path)
            assert result == ["safe.txt", "subdir/safe.txt"]
            mock_zip.getmember.assert_not_called()

    def test_tar_safe_members(self, tmp_path: Path) -> None:
        mock_tar = MagicMock()
        mock_tar.getnames.return_value = [
            "safe.txt",
            "../unsafe.txt",
            "subdir/safe.txt",
        ]
        mock_member = MagicMock()
        mock_tar.getmember.return_value = mock_member

        with patch("fontpm.downloader._is_safe_archive_path") as mock_safe:
            mock_safe.side_effect = lambda path, _: not path.startswith("../")  # type: ignore

            result = _get_safe_members(mock_tar, "tar", tmp_path)
            assert result == [mock_member, mock_member]
            assert mock_tar.getmember.call_count == 2


class TestGetBaseAndExt:
    def test_zip_extension(self) -> None:
        base, ext = get_base_and_ext("archive.zip")
        assert base == "archive"
        assert ext == ".zip"

    def test_tar_gz_extension(self) -> None:
        base, ext = get_base_and_ext("archive.tar.gz")
        assert base == "archive"
        assert ext == ".tar.gz"

    def test_tar_xz_extension(self) -> None:
        base, ext = get_base_and_ext("archive.tar.xz")
        assert base == "archive"
        assert ext == ".tar.xz"

    def test_tgz_extension(self) -> None:
        base, ext = get_base_and_ext("archive.tgz")
        assert base == "archive"
        assert ext == ".tgz"

    def test_no_extension(self) -> None:
        base, ext = get_base_and_ext("archive")
        assert base == "archive"
        assert ext == ""

    def test_unknown_extension(self) -> None:
        base, ext = get_base_and_ext("archive.rar")
        assert base == "archive.rar"
        assert ext == ""


class TestGetSubdirectoryVersion:
    @patch("fontpm.downloader.httpx.get")
    @patch("fontpm.downloader.default_github_token", "token")
    def test_success_ofl(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"commit": {"committer": {"date": "2023-01-01T00:00:00Z"}}}
        ]
        mock_get.return_value = mock_response

        result = get_subdirectory_version("font-name")
        assert result == "2023-01-01T00:00:00Z"
        mock_get.assert_called_once()

    @patch("fontpm.downloader.httpx.get")
    def test_fallback_ufl(self, mock_get: MagicMock) -> None:
        import httpx

        mock_response1 = MagicMock()
        mock_response1.status_code = 404
        mock_response1.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=mock_response1
        )
        mock_response2 = MagicMock()
        mock_response2.status_code = 200
        mock_response2.json.return_value = [
            {"commit": {"committer": {"date": "2023-01-02T00:00:00Z"}}}
        ]

        mock_get.side_effect = [mock_response1, mock_response2]

        result = get_subdirectory_version("font-name")
        assert result == "2023-01-02T00:00:00Z"

    @patch("fontpm.downloader.httpx.get")
    def test_no_commits(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        result = get_subdirectory_version("font-name")
        assert result == "latest"


class TestGetFontsDirVersion:
    @patch("fontpm.downloader.httpx.get")
    @patch("fontpm.downloader.default_github_token", "token")
    def test_success(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"commit": {"committer": {"date": "2023-01-01T00:00:00Z"}}}
        ]
        mock_get.return_value = mock_response

        result = get_fonts_dir_version("owner", "repo")
        assert result == "2023-01-01T00:00:00Z"

    @patch("fontpm.downloader.httpx.get")
    def test_no_commits(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        result = get_fonts_dir_version("owner", "repo")
        assert result == "latest"


class TestDownloadFontsDir:
    @patch("fontpm.downloader.httpx.get")
    @patch("fontpm.downloader.tempfile.mkdtemp")
    @patch("fontpm.downloader.default_github_token", "token")
    def test_success(self, mock_mkdtemp: MagicMock, mock_get: MagicMock) -> None:
        mock_mkdtemp.return_value = "/tmp/test"

        # Mock contents response
        contents_response = MagicMock()
        contents_response.status_code = 200
        contents_response.json.return_value = [
            {
                "type": "file",
                "name": "font.ttf",
                "path": "fonts/font.ttf",
                "download_url": "https://example.com/font.ttf",
            }
        ]
        mock_get.return_value = contents_response

        # Mock file download
        file_response = MagicMock()
        file_response.status_code = 200
        file_response.content = b"font data"
        mock_get.side_effect = [contents_response, file_response]

        with patch("fontpm.downloader.console.print"):
            result = download_fonts_dir("owner", "repo")
            assert result == Path("/tmp/test")

    @patch("fontpm.downloader.httpx.get")
    def test_no_fonts(self, mock_get: MagicMock) -> None:
        contents_response = MagicMock()
        contents_response.status_code = 200
        contents_response.json.return_value = []
        mock_get.return_value = contents_response

        with pytest.raises(ValueError, match="No font files in fonts directory"):
            download_fonts_dir("owner", "repo")


class TestFetchReleaseInfo:
    @patch("fontpm.downloader.httpx.get")
    @patch("fontpm.downloader.default_github_token", "token")
    def test_latest_release(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tag_name": "v1.0.0",
            "assets": [
                {"name": "archive.zip", "size": 100, "browser_download_url": "url"}
            ],
            "body": "Release notes",
            "url": "https://api.github.com/repos/owner/repo/releases/1",
        }
        mock_get.return_value = mock_response

        with patch("fontpm.downloader.console.status"):
            version, assets, body, owner, repo = fetch_release_info(
                "owner", "repo", "latest"
            )
            assert version == "v1.0.0"
            assert len(assets) == 1
            assert body == "Release notes"
            assert owner == "owner"
            assert repo == "repo"

    @patch("fontpm.downloader.httpx.get")
    def test_specific_release(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "tag_name": "v1.0.0",
            "assets": [],
            "body": "",
            "url": "https://api.github.com/repos/owner/repo/releases/tags/v1.0.0",
        }
        mock_get.return_value = mock_response

        with patch("fontpm.downloader.console.status"):
            version, assets, body, owner, repo = fetch_release_info(
                "owner", "repo", "1.0.0"
            )
            assert version == "v1.0.0"
            assert assets == []
            assert body == ""
            assert owner == "owner"
            assert repo == "repo"

    @patch("fontpm.downloader.get_subdirectory_version")
    @patch("fontpm.downloader.httpx.get")
    def test_google_fonts_subdirectory(
        self, mock_get: MagicMock, mock_subdir: MagicMock
    ) -> None:
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404", request=MagicMock(), response=mock_response
        )
        mock_get.return_value = mock_response
        mock_subdir.return_value = "2023-01-01"

        with patch("fontpm.downloader.console.status"):
            version, assets, _, owner, repo = fetch_release_info(
                "thegooglefontsrepo", "font", "latest"
            )
            assert version == "2023-01-01"
            assert assets == []
            assert owner == "thegooglefontsrepo"
            assert repo == "font"


class TestSelectArchiveAsset:
    def test_single_archive(self) -> None:
        assets = cast(
            "List[Asset]",
            [
                {"name": "archive.zip", "size": 100, "browser_download_url": "url1"},
                {"name": "other.txt", "size": 50, "browser_download_url": "url2"},
            ],
        )
        result = select_archive_asset(assets)
        assert result["name"] == "archive.zip"

    def test_multiple_groups_priority(self) -> None:
        assets = cast(
            "List[Asset]",
            [
                {"name": "archive.tar.gz", "size": 100, "browser_download_url": "url1"},
                {"name": "archive.zip", "size": 80, "browser_download_url": "url2"},
            ],
        )
        result = select_archive_asset(assets)
        assert result["name"] == "archive.tar.gz"  # tar.gz has higher priority

    def test_size_tiebreaker(self) -> None:
        assets = cast(
            "List[Asset]",
            [
                {"name": "archive.tar.gz", "size": 100, "browser_download_url": "url1"},
                {"name": "archive.tar.xz", "size": 80, "browser_download_url": "url2"},
            ],
        )
        result = select_archive_asset(assets)
        assert result["name"] == "archive.tar.xz"  # smaller size wins

    def test_no_archive(self) -> None:
        assets = cast(
            "List[Asset]",
            [{"name": "other.txt", "size": 50, "browser_download_url": "url"}],
        )
        with pytest.raises(ValueError, match="No archive asset found"):
            select_archive_asset(assets)


class TestGetOrDownloadAndExtractArchive:
    @patch("fontpm.downloader.CACHE")
    @patch("fontpm.downloader.tempfile.mkdtemp")
    @patch("fontpm.downloader.zipfile.ZipFile")
    def test_cache_hit_zip(
        self, mock_zip: MagicMock, mock_mkdtemp: MagicMock, mock_cache: MagicMock
    ) -> None:
        mock_cache.__contains__.return_value = True
        mock_cache.__getitem__.return_value = "/cache/archive.zip"
        mock_mkdtemp.return_value = "/tmp/extract"
        mock_archive = MagicMock()
        mock_zip.return_value.__enter__.return_value = mock_archive
        mock_archive.extractall = MagicMock()

        with patch("fontpm.downloader._get_safe_members", return_value=["file.txt"]):
            with patch("fontpm.downloader.console.print"):
                result = get_or_download_and_extract_archive(
                    "owner", "repo", "v1.0", "url", ".zip", "archive.zip"
                )
                assert result == Path("/tmp/extract")
                mock_archive.extractall.assert_called_once()

    @patch("fontpm.downloader.CACHE")
    @patch("fontpm.downloader.CACHE_DIR")
    @patch("fontpm.downloader.tempfile.mkdtemp")
    @patch("fontpm.downloader.tempfile.NamedTemporaryFile")
    @patch("fontpm.downloader.httpx.stream")
    @patch("fontpm.downloader.zipfile.ZipFile")
    @patch("fontpm.downloader.shutil.copy")
    def test_cache_miss_zip(
        self,
        mock_copy: MagicMock,
        mock_zip: MagicMock,
        mock_stream: MagicMock,
        mock_named: MagicMock,
        mock_mkdtemp: MagicMock,
        mock_cache_dir: MagicMock,
        mock_cache: MagicMock,
    ) -> None:
        mock_cache.__contains__.return_value = False
        mock_mkdtemp.return_value = "/tmp/extract"
        mock_named.return_value.__enter__.return_value = MagicMock()
        mock_named.return_value.__enter__.return_value.name = "/tmp/archive.zip"
        mock_named.return_value.__exit__ = MagicMock()

        mock_response = MagicMock()
        mock_response.__enter__.return_value = mock_response
        mock_response.raise_for_status = MagicMock()
        mock_response.iter_bytes.return_value = [b"data"]
        mock_stream.return_value.__enter__.return_value = mock_response

        mock_archive = MagicMock()
        mock_zip.return_value.__enter__.return_value = mock_archive
        mock_archive.extractall = MagicMock()

        mock_cache_dir.__truediv__.return_value = Path("/cache/archive.zip")

        with patch("fontpm.downloader._get_safe_members", return_value=["file.txt"]):
            with patch("fontpm.downloader.console.print"):
                with patch("builtins.open", mock_open()):
                    result = get_or_download_and_extract_archive(
                        "owner", "repo", "v1.0", "url", ".zip", "archive.zip"
                    )
                    assert result == Path("/tmp/extract")
                    mock_copy.assert_called_once()
                    mock_cache.__setitem__.assert_called_once()
