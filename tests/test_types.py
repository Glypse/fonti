from fontpm.types import Asset, ExportedFontEntry, FontEntry


class TestTypes:
    def test_asset_creation(self) -> None:
        asset = Asset(
            name="font.zip",
            size=12345,
            browser_download_url="https://example.com/font.zip",
        )
        assert asset["name"] == "font.zip"
        assert asset["size"] == 12345
        assert asset["browser_download_url"] == "https://example.com/font.zip"

    def test_font_entry_creation(self) -> None:
        entry = FontEntry(
            filename="font.ttf",
            hash="abc123",
            type="ttf",
            version="1.0",
            owner="owner",
            repo_name="repo",
        )
        assert entry["filename"] == "font.ttf"
        assert entry["hash"] == "abc123"
        assert entry["type"] == "ttf"
        assert entry["version"] == "1.0"
        assert entry["owner"] == "owner"
        assert entry["repo_name"] == "repo"

    def test_exported_font_entry_creation(self) -> None:
        # total=False, so can have partial
        entry = ExportedFontEntry(filename="font.ttf", type="ttf")
        assert entry.get("filename") == "font.ttf"
        assert entry.get("type") == "ttf"
        # Can check that missing keys are not required
        entry2 = ExportedFontEntry()
        assert isinstance(entry2, dict)
