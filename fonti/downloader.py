import shutil
import tarfile
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Tuple, Union, cast, overload

import httpx
from rich.console import Console

from .config import CACHE_DIR, cache, default_github_token
from .constants import ARCHIVE_EXTENSIONS

if TYPE_CHECKING:
    from .types import Asset

console = Console()


def _is_safe_archive_path(path: str, extract_dir: Path) -> bool:
    """
    Check if an archive member path is safe to extract.

    Prevents path traversal attacks by ensuring the path:
    - Doesn't contain '..' components
    - Doesn't start with '/' (absolute path)
    - Results in a file within the extraction directory
    - Doesn't create overly deep directory structures (>15 levels)
    """
    if not path:
        return False

    # Reject absolute paths
    if path.startswith("/"):
        return False

    # Reject paths with '..' components
    if ".." in path.split("/"):
        return False

    # Check depth (prevent deep directory structures >15 levels)
    parts = Path(path).parts
    if len(parts) > 15:
        return False

    # The path should not escape the extract directory when resolved
    # We do this by checking if the resolved path starts with the resolved extract dir
    try:
        resolved_extract_dir = extract_dir.resolve()
        resolved_full_path = (extract_dir / path).resolve()
        return str(resolved_full_path).startswith(str(resolved_extract_dir))
    except (ValueError, OSError):
        return False


@overload
def _get_safe_members(
    archive: zipfile.ZipFile, archive_type: str, extract_dir: Path
) -> List[str]: ...


@overload
def _get_safe_members(
    archive: tarfile.TarFile, archive_type: str, extract_dir: Path
) -> List[tarfile.TarInfo]: ...


def _get_safe_members(
    archive: Union[zipfile.ZipFile, tarfile.TarFile],
    archive_type: str,
    extract_dir: Path,
) -> Union[List[str], List[tarfile.TarInfo]]:
    """Get archive members that are safe to extract."""
    if archive_type == "zip":
        members = cast("List[str]", archive.namelist())  # type: ignore[attr-defined]
    else:  # tar
        members = cast("List[str]", archive.getnames())  # type: ignore[attr-defined]

    safe_members: Any = []
    for member in members:
        if _is_safe_archive_path(member, extract_dir):
            if archive_type == "zip":
                safe_members.append(member)
            else:  # tar
                safe_members.append(archive.getmember(member))  # type: ignore[attr-defined]
        else:
            console.print(f"[yellow]Skipping unsafe archive member: {member}[/yellow]")

    if archive_type == "zip":
        return cast("List[str]", safe_members)
    else:
        return cast("List[tarfile.TarInfo]", safe_members)


def get_base_and_ext(name: str) -> tuple[str, str]:
    for ext in ARCHIVE_EXTENSIONS:
        if name.endswith(ext):
            return name[: -len(ext)], ext
    return name, ""


def get_subdirectory_version(dir_font_name: str) -> str:
    """Get the last commit date for a Google Fonts subdirectory."""
    headers: Dict[str, str] = {}
    if default_github_token:
        headers["Authorization"] = f"Bearer {default_github_token}"

    if "/" in dir_font_name:
        dir_part, font_name = dir_font_name.split("/", 1)
    else:
        raise ValueError(
            f"Invalid dir_font_name format: {dir_font_name}. Expected dir/font_name"
        )

    path = f"{dir_part}/{font_name}"
    try:
        url = f"https://api.github.com/repos/google/fonts/commits?path={path}"
        response = httpx.get(url, headers=headers)
        response.raise_for_status()
        commits = response.json()
        if commits:
            last_commit = commits[0]
            date = last_commit["commit"]["committer"]["date"]
            return date
    except Exception:
        pass
    return "latest"


def get_fonts_dir_version(owner: str, repo_name: str) -> str:
    """Get the last commit date for a fonts directory in a repo."""
    headers: Dict[str, str] = {}
    if default_github_token:
        headers["Authorization"] = f"Bearer {default_github_token}"

    url = f"https://api.github.com/repos/{owner}/{repo_name}/commits?path=fonts"
    response = httpx.get(url, headers=headers)
    response.raise_for_status()
    commits = response.json()
    if commits:
        date = commits[0]["commit"]["committer"]["date"]
        return date
    return "latest"


def download_fonts_dir(owner: str, repo_name: str) -> Path:
    """Download font files from the fonts directory recursively."""
    headers: Dict[str, str] = {}
    if default_github_token:
        headers["Authorization"] = f"Bearer {default_github_token}"

    def collect_font_files(path: str) -> List[Dict[str, Any]]:
        """Recursively collect font files from the path."""
        api_url = f"https://api.github.com/repos/{owner}/{repo_name}/contents/{path}"
        response = httpx.get(api_url, headers=headers)
        response.raise_for_status()
        contents = response.json()
        font_files: List[Dict[str, Any]] = []
        for item in contents:
            if item["type"] == "file" and item["name"].endswith(
                (".ttf", ".otf", ".woff", ".woff2")
            ):
                font_files.append(item)
            elif item["type"] == "dir":
                # Recurse
                font_files.extend(collect_font_files(item["path"]))
        return font_files

    font_files = collect_font_files("fonts")
    if not font_files:
        raise ValueError("No font files in fonts directory")
    temp_dir = Path(tempfile.mkdtemp())
    for item in font_files:
        file_url = item["download_url"]
        file_response = httpx.get(file_url, headers=headers)
        file_response.raise_for_status()
        # Keep the relative path
        rel_path = Path(item["path"]).relative_to("fonts")
        file_path = temp_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(file_response.content)
    console.print(f"Downloaded {len(font_files)} font files from fonts directory.")
    return temp_dir


def fetch_release_info(
    owner: str, repo_name: str, release: str
) -> Tuple[str, List[Asset], str, str, str]:
    """Fetch release information from GitHub API."""
    headers: Dict[str, str] = {}
    if default_github_token:
        headers["Authorization"] = f"Bearer {default_github_token}"

    with console.status("[bold green]Fetching release info..."):
        if release == "latest":
            url = f"https://api.github.com/repos/{owner}/{repo_name}/releases/latest"
            try:
                response = httpx.get(url, headers=headers, follow_redirects=True)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404 and owner == "thegooglefontsrepo":
                    # For subdirectory fonts, get commit date
                    version = get_subdirectory_version(repo_name)
                    return version, [], "", owner, repo_name
                else:
                    raise
        else:
            release_tag = release
            if not release.startswith("v"):
                release_tag = f"v{release}"
            url = f"https://api.github.com/repos/{owner}/{repo_name}/releases/tags/{release_tag}"
            try:
                response = httpx.get(url, headers=headers, follow_redirects=True)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404 and not release.startswith("v"):
                    # Try without 'v'
                    url = f"https://api.github.com/repos/{owner}/{repo_name}/releases/tags/{release}"
                    response = httpx.get(url, headers=headers, follow_redirects=True)
                    response.raise_for_status()
                else:
                    raise

        release_data: Dict[str, Any] = response.json()
        version = release_data["tag_name"]
        assets: List[Asset] = release_data.get("assets", [])
        body = release_data.get("body", "")
        # Get final owner/repo from the release data URL
        release_url = release_data["url"]
        url_parts = release_url.split("/repos/")[1].split("/")
        final_owner = url_parts[0]
        final_repo_name = url_parts[1]
        return version, assets, body, final_owner, final_repo_name


def select_archive_asset(assets: List[Asset]) -> Asset:
    """Select the best archive asset from the list."""
    archives = [
        a for a in assets if any(a["name"].endswith(ext) for ext in ARCHIVE_EXTENSIONS)
    ]
    if not archives:
        raise ValueError("No archive asset found in the release.")

    # Function to get priority for extensions (lower is better)
    def get_priority(ext: str) -> int:
        priorities_dict = {".tar.xz": 1, ".tar.gz": 2, ".tgz": 2, ".zip": 3}
        return priorities_dict.get(ext, 4)

    # Group archives by base name
    groups: defaultdict[str, list[tuple[Asset, str]]] = defaultdict(list)
    for a in archives:
        base, ext = get_base_and_ext(a["name"])
        groups[base].append((a, ext))

    # Choose the best asset from each group
    best_assets: list[Asset] = []
    for items in groups.values():
        if len(items) == 1:
            best_assets.append(items[0][0])
        else:
            # Sort by priority ascending, then by size ascending
            sorted_items = sorted(
                items, key=lambda x: (get_priority(x[1]), x[0]["size"])
            )
            best_assets.append(sorted_items[0][0])

    # If multiple groups, choose the overall best
    if len(best_assets) > 1:
        best_assets.sort(
            key=lambda a: (a["size"], get_priority(get_base_and_ext(a["name"])[1]))
        )

    return best_assets[0]


def get_or_download_and_extract_archive(
    owner: str,
    repo_name: str,
    version: str,
    archive_url: str,
    archive_ext: str,
    archive_name: str,
    is_google_fonts: bool = False,
) -> Path:
    """Get archive from cache or download and extract to a temporary directory."""
    key = (
        f"{repo_name}-{version}{archive_ext}"
        if is_google_fonts
        else f"{owner}-{repo_name}-{version}{archive_ext}"
    )

    if cache is not None and key in cache:
        console.print(f"Using cached archive: {key}")
        cached_archive_path = str(cache[key])  # type: ignore
        temp_dir = tempfile.mkdtemp()
        extract_dir = Path(temp_dir)

        with console.status("[bold green]Extracting from cache..."):
            if archive_ext == ".zip":
                with zipfile.ZipFile(cached_archive_path, "r") as archive_ref:
                    safe_members = _get_safe_members(archive_ref, "zip", extract_dir)
                    archive_ref.extractall(extract_dir, members=safe_members)
            else:
                mode = "r:xz" if archive_ext == ".tar.xz" else "r:gz"
                with tarfile.open(cached_archive_path, mode) as archive_ref:
                    safe_members = _get_safe_members(archive_ref, "tar", extract_dir)
                    archive_ref.extractall(extract_dir, members=safe_members)

        return extract_dir
    else:
        console.print(f"Downloading archive: {archive_name}")
        temp_dir = tempfile.mkdtemp()
        extract_dir = Path(temp_dir)

        tmp_file = tempfile.NamedTemporaryFile(
            dir=temp_dir, suffix=".archive", delete=False
        )
        tmp_path = Path(tmp_file.name)
        tmp_file.close()

        with console.status("[bold green]Downloading archive..."):
            with httpx.stream("GET", archive_url, follow_redirects=True) as response:
                response.raise_for_status()
                with open(tmp_path, "wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)

        console.print("Download complete.")

        # Copy to cache (diskcache will evict old entries if necessary)
        if cache is not None:
            cache_path = CACHE_DIR / f"{key}"
            shutil.copy(tmp_path, cache_path)
            cache[key] = str(cache_path)
            console.print("Archive cached.")

        with console.status("[bold green]Extracting..."):
            if archive_ext == ".zip":
                with zipfile.ZipFile(tmp_path, "r") as archive_ref:
                    safe_members = _get_safe_members(archive_ref, "zip", extract_dir)
                    archive_ref.extractall(extract_dir, members=safe_members)
            else:
                mode = "r:xz" if archive_ext == ".tar.xz" else "r:gz"
                with tarfile.open(tmp_path, mode) as archive_ref:
                    safe_members = _get_safe_members(archive_ref, "tar", extract_dir)
                    archive_ref.extractall(extract_dir, members=safe_members)

        return extract_dir
