from pathlib import Path

from fontpm.constants import (
    ARCHIVE_EXTENSIONS,
    CONFIG_FILE,
    DEFAULT_CACHE_SIZE,
    DEFAULT_PATH,
    DEFAULT_PRIORITIES,
    INSTALLED_FILE,
    KEY_FILE,
    VALID_FORMATS,
)


class TestConstants:
    def test_archive_extensions(self) -> None:
        expected = [".zip", ".tar.xz", ".tar.gz", ".tgz"]
        assert ARCHIVE_EXTENSIONS == expected

    def test_valid_formats(self) -> None:
        expected = [
            "variable-ttf",
            "otf",
            "static-ttf",
            "variable-woff2",
            "variable-woff",
            "static-woff2",
            "static-woff",
        ]
        assert VALID_FORMATS == expected

    def test_default_priorities(self) -> None:
        expected = ["variable-ttf", "otf", "static-ttf"]
        assert DEFAULT_PRIORITIES == expected

    def test_default_path(self) -> None:
        expected = Path.home() / "Library" / "Fonts"
        assert DEFAULT_PATH == expected

    def test_default_cache_size(self) -> None:
        expected = 200 * 1024 * 1024  # 200MB
        assert DEFAULT_CACHE_SIZE == expected

    def test_config_file(self) -> None:
        expected = Path.home() / ".fontpm" / "config"
        assert CONFIG_FILE == expected

    def test_key_file(self) -> None:
        expected = Path.home() / ".fontpm" / "key"
        assert KEY_FILE == expected

    def test_installed_file(self) -> None:
        expected = Path.home() / ".fontpm" / "installed.json"
        assert INSTALLED_FILE == expected
