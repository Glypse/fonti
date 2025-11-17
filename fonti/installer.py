import hashlib
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, List

import httpx
from fontTools.ttLib import TTFont  # pyright: ignore[reportMissingTypeStubs]
from rich.console import Console

from .config import CACHE_DIR, cache, load_installed_data, save_installed_data
from .constants import VALID_FORMATS
from .downloader import (
    download_fonts_dir,
    fetch_release_info,
    get_base_and_ext,
    get_fonts_dir_version,
    get_or_download_and_extract_archive,
    get_subdirectory_version,
    select_archive_asset,
)
from .fonts import categorize_fonts, select_fonts

if TYPE_CHECKING:
    from .types import FontEntry

console = Console()


def install_fonts(
    selected_fonts: List[Path],
    dest_dir: Path,
    repo_name: str,
    repo_key: str,
    owner: str,
    version: str,
    selected_pri: str,
    local: bool,
) -> None:
    """Install selected fonts to destination directory and update installed data."""
    if not selected_fonts:
        console.print(
            f"[yellow]No font files found in the archive for {owner}/{repo_name}.[/yellow]"
        )
        return

    with console.status("[bold green]Moving fonts..."):
        valid_fonts: List[Path] = []
        for font_file in selected_fonts:
            try:
                TTFont(font_file)
                valid_fonts.append(font_file)
            except Exception as e:
                if not font_file.name.startswith("._"):
                    console.print(
                        f"[yellow]Skipping invalid font file {font_file.name}: {e}[/yellow]"
                    )
                continue

    for font_file in valid_fonts:
        shutil.move(str(font_file), str(dest_dir / font_file.name))

    number_installed_fonts = len(valid_fonts)

    if not local:
        installed_data = load_installed_data()
        if repo_key not in installed_data:
            installed_data[repo_key] = {}
        previous_count = len(installed_data[repo_key])
        for font_file in valid_fonts:
            try:
                file_hash = hashlib.sha256(
                    (dest_dir / font_file.name).read_bytes()
                ).hexdigest()
                entry: FontEntry = {
                    "filename": font_file.name,
                    "hash": file_hash,
                    "type": selected_pri,
                    "version": version,
                    "owner": owner,
                    "repo_name": repo_name,
                }
                installed_data[repo_key][font_file.name] = entry
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Could not hash {font_file.name}: {e}[/yellow]"
                )
        save_installed_data(installed_data)
        number_installed_fonts = len(installed_data[repo_key]) - previous_count

    console.print(
        f"[green]Moved {number_installed_fonts} font{'' if number_installed_fonts == 1 else 's'} from "
        f"{owner}/{repo_name} to: {dest_dir}[/green]"
    )


def install_single_repo(
    owner: str,
    repo_name: str,
    repo_key: str,
    release: str,
    priorities: list[str],
    dest_dir: Path,
    local: bool,
    force: bool,
    weights: List[int],
    styles: List[str],
    is_google_fonts: bool = False,
    pre_extract_dir: Path | None = None,
    is_subdirectory: bool = False,
) -> None:
    """
    Install fonts from a single GitHub repository.

    Args:
        owner: Repository owner
        repo_name: Repository name
        release: Release tag or 'latest'
        priorities: List of font format priorities
        dest_dir: Destination directory for fonts
        local: Whether to install locally (not globally)
        force: Whether to force reinstall
        keep_multiple: Whether to allow multiple font types
    """
    repo_arg = f"{owner}/{repo_name}"
    console.print(f"[bold]Installing from {repo_arg}...[/bold]")

    # Warn for WOFF/WOFF2 global install
    if (
        any(
            p in ["static-woff", "static-woff2", "variable-woff", "variable-woff2"]
            for p in priorities
        )
        and not local
        and not force
    ):
        console.print(
            "[yellow]Installing WOFF/WOFF2 fonts globally is not recommended. "
            "Use --force to proceed.[/yellow]"
        )
        return

    extract_dir = None
    try:
        if is_subdirectory:
            # For subdirectory, extract_dir is already provided
            extract_dir = pre_extract_dir
            version = get_subdirectory_version(repo_name)
        elif release == "latest":
            try:
                version, assets, _, final_owner, final_repo_name = fetch_release_info(
                    owner, repo_name, release
                )
                owner = final_owner
                repo_name = final_repo_name
                chosen_asset = select_archive_asset(assets)
                archive_url = chosen_asset["browser_download_url"]
                archive_name = chosen_asset["name"]
                _, archive_ext = get_base_and_ext(archive_name)

                extract_dir = get_or_download_and_extract_archive(
                    owner,
                    repo_name,
                    version,
                    archive_url,
                    archive_ext,
                    archive_name,
                    is_google_fonts,
                )
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404 and owner != "thegooglefontsrepo":
                    # Fallback to fonts directory
                    try:
                        version = get_fonts_dir_version(owner, repo_name)
                        cache_key = (
                            f"{owner}-{repo_name}-fonts-{version.replace(':', '-')}.zip"
                        )
                        if cache is not None and cache_key in cache:
                            console.print(f"Using cached fonts directory: {cache_key}")
                            cached_zip = str(cache[cache_key])  # type: ignore
                            extract_dir = Path(tempfile.mkdtemp())
                            with zipfile.ZipFile(cached_zip, "r") as zip_ref:
                                zip_ref.extractall(extract_dir)
                        else:
                            extract_dir = download_fonts_dir(owner, repo_name)
                            # Cache
                            if cache is not None:
                                zip_path = CACHE_DIR / cache_key
                                with zipfile.ZipFile(zip_path, "w") as zip_ref:
                                    for file_path in extract_dir.rglob("*"):
                                        if file_path.is_file():
                                            zip_ref.write(
                                                file_path,
                                                file_path.relative_to(extract_dir),
                                            )
                                cache[cache_key] = str(zip_path)
                                console.print("Fonts directory cached.")
                        is_subdirectory = True
                        final_owner = owner
                        final_repo_name = repo_name
                    except Exception as ex:
                        console.print(
                            f"[red]No releases or fonts directory found for {owner}/{repo_name}: {ex}[/red]"
                        )
                        raise
                else:
                    raise
        else:
            version = release
            cached_key = None
            archive_ext = None
            for ext in VALID_FORMATS:  # Wait, no, ARCHIVE_EXTENSIONS
                from .constants import ARCHIVE_EXTENSIONS

                for ext in ARCHIVE_EXTENSIONS:
                    key = f"{owner}-{repo_name}-{version}{ext}"
                    if cache is not None and key in cache:
                        cached_key = key
                        archive_ext = ext
                        break
            if cached_key:
                console.print(f"Using cached archive: {cached_key}")
                cached_archive_path = str(cache[cached_key])  # type: ignore
                temp_dir = tempfile.mkdtemp()
                extract_dir = Path(temp_dir)

                with console.status("[bold green]Extracting from cache..."):
                    if archive_ext == ".zip":
                        with zipfile.ZipFile(cached_archive_path, "r") as archive_ref:
                            archive_ref.extractall(extract_dir)
                    else:
                        mode = "r:xz" if archive_ext == ".tar.xz" else "r:gz"
                        with tarfile.open(cached_archive_path, mode) as archive_ref:
                            archive_ref.extractall(extract_dir)
            else:
                _, assets, _, final_owner, final_repo_name = fetch_release_info(
                    owner, repo_name, release
                )
                owner = final_owner
                repo_name = final_repo_name
                chosen_asset = select_archive_asset(assets)
                archive_url = chosen_asset["browser_download_url"]
                archive_name = chosen_asset["name"]
                _, archive_ext = get_base_and_ext(archive_name)

                extract_dir = get_or_download_and_extract_archive(
                    owner,
                    repo_name,
                    version,
                    archive_url,
                    archive_ext,
                    archive_name,
                    is_google_fonts,
                )

        # Find all font files
        assert extract_dir is not None
        font_files = (
            list(extract_dir.rglob("*.ttf"))
            + list(extract_dir.rglob("*.otf"))
            + list(extract_dir.rglob("*.woff"))
            + list(extract_dir.rglob("*.woff2"))
        )

        categorized_fonts = categorize_fonts(font_files)
        selected_fonts, selected_pri = select_fonts(
            categorized_fonts, priorities, weights, styles
        )

        if not local:
            installed_data = load_installed_data()
            if repo_key in installed_data:
                current_versions = {
                    f["version"] for f in installed_data[repo_key].values()
                }
                if len(current_versions) == 1 and list(current_versions)[0] == version:
                    if not force:
                        console.print(
                            f"[yellow]{repo_key} version {version} is already installed. "
                            "Use --force to reinstall.[/yellow]"
                        )
                        return
                    else:
                        console.print(
                            f"[yellow]Forcing reinstall of {repo_key} version {version}...[/yellow]"
                        )
                # Remove old fonts
                for font_info in installed_data[repo_key].values():
                    filename = font_info["filename"]
                    font_path = dest_dir / filename
                    if font_path.exists():
                        try:
                            font_path.unlink()
                        except Exception as e:
                            console.print(
                                f"[red]Could not delete {filename}: {e}[/red]"
                            )
                del installed_data[repo_key]
                save_installed_data(installed_data)

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

    except Exception as e:
        console.print(f"[red]Error installing from {repo_arg}: {e}[/red]")
        raise
    finally:
        if extract_dir:
            shutil.rmtree(str(extract_dir))
