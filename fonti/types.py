from typing import TypedDict


class Asset(TypedDict):
    name: str
    size: int
    browser_download_url: str


class FontEntry(TypedDict):
    hash: str
    type: str
    version: str
    owner: str
    repo_name: str


class ExportedFontEntry(TypedDict, total=False):
    type: str
    version: str
    owner: str
    repo_name: str
