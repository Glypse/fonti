import hashlib
import json
import shutil
import tarfile
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple, TypedDict

import httpx
import typer
from fontTools.ttLib import TTFont  # type: ignore
from rich.console import Console

app = typer.Typer()
console = Console()


class Asset(TypedDict):
    name: str
    size: int
    browser_download_url: str


class FontEntry(TypedDict):
    filename: str
    hash: str
    type: str
    version: str


class ExportedFontEntry(TypedDict):
    filename: str
    type: str
    version: str


def get_base_and_ext(name: str) -> tuple[str, str]:
    archive_extensions = [".zip", ".tar.xz", ".tar.gz", ".tgz"]
    for ext in archive_extensions:
        if name.endswith(ext):
            return name[: -len(ext)], ext
    return name, ""


# Load default format from config file
default_priorities = ["variable-ttf", "otf", "static-ttf"]
default_path = Path.home() / "Library" / "Fonts"
config_file = Path.home() / ".fontpm" / "config"

if config_file.exists():
    try:
        with open(config_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("format="):
                    value = line.split("=", 1)[1].strip()
                    if value == "auto":
                        continue
                    priorities = [p.strip() for p in value.split(",")]
                    if all(
                        p in ["variable-ttf", "otf", "static-ttf"] for p in priorities
                    ):
                        default_priorities = priorities
                elif line.startswith("path="):
                    value = line.split("=", 1)[1].strip()
                    if value:
                        default_path = Path(value)
    except Exception:
        pass  # Ignore config errors


def is_variable_font(font_path: str) -> bool:
    """
    Check if a font file is a variable font.
    """
    font = TTFont(font_path)
    return "fvar" in font


def install_single_repo(
    owner: str,
    repo_name: str,
    release: str,
    priorities: list[str],
    dest_dir: Path,
    local: bool,
    force: bool,
    keep_multiple: bool,
) -> None:
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

    if not local:
        installed_file = Path.home() / ".fontpm" / "installed.json"
        if installed_file.exists():
            try:
                with open(installed_file) as f:
                    temp_data = json.load(f)
                if repo_arg in temp_data and temp_data[repo_arg]:
                    if not force:
                        console.print(
                            f"[yellow]Already installed from {repo_arg}. "
                            "Use --force to reinstall or change version.[/yellow]"
                        )
                        return
            except Exception:
                pass

    with console.status("[bold green]Fetching release info..."):
        if release == "latest":
            url = f"https://api.github.com/repos/{owner}/{repo_name}/releases/latest"
            response = httpx.get(url)
            response.raise_for_status()
        else:
            release_tag = release
            if not release.startswith("v"):
                release_tag = f"v{release}"
            url = f"https://api.github.com/repos/{owner}/{repo_name}/releases/tags/{release_tag}"
            try:
                response = httpx.get(url)
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404 and not release.startswith("v"):
                    # Try without 'v'
                    url = f"https://api.github.com/repos/{owner}/{repo_name}/releases/tags/{release}"
                    response = httpx.get(url)
                    response.raise_for_status()
                else:
                    raise

        release_data: Dict[str, Any] = response.json()
        version = release_data["tag_name"]

    assets: List[Asset] = release_data.get("assets", [])
    archive_extensions = [".zip", ".tar.xz", ".tar.gz", ".tgz"]
    archives = [
        a for a in assets if any(a["name"].endswith(ext) for ext in archive_extensions)
    ]
    if not archives:
        console.print(
            f"[red]No archive asset found in the release for {repo_arg}.[/red]"
        )
        return

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
            # Sort by size ascending, then by priority ascending
            sorted_items = sorted(
                items, key=lambda x: (x[0]["size"], get_priority(x[1]))
            )
            best_assets.append(sorted_items[0][0])

    # If multiple groups, choose the overall best
    if len(best_assets) > 1:
        best_assets.sort(
            key=lambda a: (a["size"], get_priority(get_base_and_ext(a["name"])[1]))
        )

    chosen_asset = best_assets[0]
    archive_url: str = chosen_asset["browser_download_url"]
    archive_name: str = chosen_asset["name"]
    _, archive_ext = get_base_and_ext(archive_name)

    console.print(f"Found archive: {archive_name}")

    if not local:
        installed_file = Path.home() / ".fontpm" / "installed.json"
        if installed_file.exists():
            try:
                with open(installed_file) as f:
                    temp_data = json.load(f)
                installed_types = [
                    entry.get("type")
                    for entry in temp_data.get(repo_arg, {}).values()
                    if "type" in entry
                ]
                if installed_types and not keep_multiple and not force:
                    console.print(
                        f"[yellow]Already installed other types from {repo_arg}. "
                        "Use --keep-multiple to install additional types or --force to overwrite.[/yellow]"
                    )
                    return
            except Exception:
                pass

    with tempfile.TemporaryDirectory() as temp_dir:
        extract_dir = Path(temp_dir)

        with tempfile.NamedTemporaryFile(
            dir=temp_dir, suffix=".archive", delete=False
        ) as tmp_file:
            tmp_path = Path(tmp_file.name)

            with console.status("[bold green]Downloading archive..."):
                with httpx.stream(
                    "GET", archive_url, follow_redirects=True
                ) as response:
                    response.raise_for_status()
                    with open(tmp_path, "wb") as f:
                        for chunk in response.iter_bytes():
                            f.write(chunk)

            console.print("Download complete.")

            with console.status("[bold green]Extracting..."):
                if archive_ext == ".zip":
                    with zipfile.ZipFile(tmp_path, "r") as archive_ref:
                        archive_ref.extractall(extract_dir)
                else:
                    # For tar archives
                    mode = "r:xz" if archive_ext == ".tar.xz" else "r:gz"
                    with tarfile.open(tmp_path, mode) as archive_ref:
                        archive_ref.extractall(extract_dir)

        # Find all font files
        ttf_files = list(extract_dir.rglob("*.ttf"))
        otf_files = list(extract_dir.rglob("*.otf"))
        woff_files = list(extract_dir.rglob("*.woff"))
        woff2_files = list(extract_dir.rglob("*.woff2"))

        variable_ttfs: list[Path] = []
        static_ttfs: list[Path] = []
        for ttf in ttf_files:
            try:
                if is_variable_font(str(ttf)):
                    variable_ttfs.append(ttf)
                else:
                    static_ttfs.append(ttf)
            except Exception:
                # If can't check, treat as static
                static_ttfs.append(ttf)

        variable_woffs: list[Path] = []
        static_woffs: list[Path] = []
        for woff in woff_files:
            try:
                if is_variable_font(str(woff)):
                    variable_woffs.append(woff)
                else:
                    static_woffs.append(woff)
            except Exception:
                static_woffs.append(woff)

        variable_woff2s: list[Path] = []
        static_woff2s: list[Path] = []
        for woff2 in woff2_files:
            try:
                if is_variable_font(str(woff2)):
                    variable_woff2s.append(woff2)
                else:
                    static_woff2s.append(woff2)
            except Exception:
                static_woff2s.append(woff2)

        # Select fonts in order of preference
        selected_fonts: list[Path] = []
        selected_pri = None
        for pri in priorities:
            if pri == "variable-woff2" and variable_woff2s:
                selected_fonts = variable_woff2s
                selected_pri = pri
                break
            elif pri == "static-woff2" and static_woff2s:
                selected_fonts = static_woff2s
                selected_pri = pri
                break
            elif pri == "variable-woff" and variable_woffs:
                selected_fonts = variable_woffs
                selected_pri = pri
                break
            elif pri == "static-woff" and static_woffs:
                selected_fonts = static_woffs
                selected_pri = pri
                break
            elif pri == "variable-ttf" and variable_ttfs:
                selected_fonts = variable_ttfs
                selected_pri = pri
                break
            elif pri == "otf" and otf_files:
                selected_fonts = otf_files
                selected_pri = pri
                break
            elif pri == "static-ttf" and static_ttfs:
                selected_fonts = static_ttfs
                selected_pri = pri
                break

        installed_data: Dict[str, Dict[str, FontEntry]] = {}

        if selected_fonts and not local:
            installed_file = Path.home() / ".fontpm" / "installed.json"
            if installed_file.exists():
                try:
                    with open(installed_file) as f:
                        temp_data = json.load(f)
                    installed_types = [
                        entry.get("type")
                        for entry in temp_data.get(repo_arg, {}).values()
                        if "type" in entry
                    ]
                    should_skip = False
                    if selected_pri in installed_types:
                        if not force:
                            console.print(
                                f"[yellow]Already installed {selected_pri} from {repo_arg}. "
                                "Use --force to reinstall.[/yellow]"
                            )
                            should_skip = True
                    if should_skip:
                        return
                except Exception:
                    pass

        # Track installed fonts for global installs
        if selected_fonts and not local:
            installed_file = Path.home() / ".fontpm" / "installed.json"
            installed_file.parent.mkdir(exist_ok=True)
            installed_data: Dict[str, Dict[str, FontEntry]] = {}
            if installed_file.exists():
                try:
                    with open(installed_file) as f:
                        installed_data = json.load(f)
                except Exception:
                    pass  # Ignore load errors

            repo_key = repo_arg
            if repo_key not in installed_data or force:
                installed_data[repo_key] = {}
            for font_file in selected_fonts:
                try:
                    file_hash = hashlib.sha256(font_file.read_bytes()).hexdigest()
                    assert selected_pri is not None
                    entry: FontEntry = {
                        "filename": font_file.name,
                        "hash": file_hash,
                        "type": selected_pri,
                        "version": version,
                    }
                    installed_data[repo_key][font_file.name] = entry
                except Exception as e:
                    console.print(
                        f"[yellow]Warning: Could not hash {font_file.name}: {e}[/yellow]"
                    )

            try:
                with open(installed_file, "w") as f:
                    json.dump(installed_data, f, indent=2)
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Could not save install data: {e}[/yellow]"
                )

        if selected_fonts:
            with console.status("[bold green]Moving fonts..."):
                for font_file in selected_fonts:
                    shutil.move(str(font_file), str(dest_dir / font_file.name))
            if not local and repo_arg in installed_data:
                number_installed_fonts = len(installed_data[repo_arg])
            else:
                number_installed_fonts = len(selected_fonts)
            console.print(
                f"[green]Moved {number_installed_fonts} font{'' if number_installed_fonts == 1 else 's'} from "
                f"{repo_arg} to: {dest_dir}[/green]"
            )
        else:
            msg = f"[yellow]No font files found in the archive for {repo_arg}.[/yellow]"
            console.print(msg)


@app.command()
def install(
    repo: List[str] = typer.Argument(  # noqa: B008
        ..., help="GitHub repository in format owner/repo"
    ),
    release: str = typer.Option("latest", "--release", "-r", help="Release tag"),
    format: str = typer.Option(
        ",".join(default_priorities),
        "--format",
        "-f",
        help="Comma-separated list of font formats to prefer in order",
    ),
    local: bool = typer.Option(
        False,
        "--local",
        "-l",
        help="Install fonts to current directory instead of default",
    ),
    force: bool = typer.Option(
        False, "--force", help="Force reinstall even if already installed"
    ),
    keep_multiple: bool = typer.Option(
        False,
        "--keep-multiple",
        "-km",
        help="Allow installing multiple font types from the same repo",
    ),
):
    """
    Install fonts from a GitHub release.
    """
    priorities = [p.strip() for p in format.split(",")]
    valid_formats = [
        "variable-ttf",
        "otf",
        "static-ttf",
        "variable-woff2",
        "variable-woff",
        "static-woff2",
        "static-woff",
    ]
    if not priorities or not all(p in valid_formats for p in priorities):
        console.print(
            "[red]Invalid --format value. Must be comma-separated list of: "
            f"{', '.join(valid_formats)}[/red]"
        )
        raise typer.Exit(1)

    dest_dir = Path.cwd() if local else default_path
    dest_dir.mkdir(exist_ok=True)

    for repo_arg in repo:
        try:
            owner, repo_name = repo_arg.split("/")
        except ValueError:
            console.print(f"[red]Invalid repo format: {repo_arg}. Use owner/repo[/red]")
            continue
        install_single_repo(
            owner,
            repo_name,
            release,
            priorities,
            Path.cwd() if local else default_path,
            local,
            force,
            keep_multiple,
        )


@app.command()
def config(
    key: str = typer.Argument(..., help="Configuration key"),
    value: str = typer.Argument(
        ..., help="Configuration value (comma-separated for format)"
    ),
):
    """
    Set configuration options.
    """
    # Load existing config
    current_config: Dict[str, str] = {}
    if config_file.exists():
        try:
            with open(config_file) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line:
                        k, v = line.split("=", 1)
                        current_config[k] = v
        except Exception:
            pass  # Ignore read errors

    if key == "format":
        priorities = [p.strip() for p in value.split(",")]
        valid = [
            "variable-ttf",
            "otf",
            "static-ttf",
            "variable-woff2",
            "variable-woff",
            "static-woff2",
            "static-woff",
        ]
        if not all(p in valid for p in priorities):
            console.print(f"[red]Invalid format values: {value}[/red]")
            raise typer.Exit(1)
        current_config["format"] = value
        console.print(f"[green]Set default format to: {value}[/green]")
    elif key == "path":
        current_config["path"] = value
        console.print(f"[green]Set default path to: {value}[/green]")
    else:
        console.print(f"[red]Unknown config key: {key}[/red]")
        raise typer.Exit(1)

    # Write back all config
    try:
        with open(config_file, "w") as f:
            for k, v in current_config.items():
                f.write(f"{k}={v}\n")
    except Exception as e:
        console.print(f"[red]Error writing config: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def uninstall(
    repo: List[str] = typer.Argument(  # noqa: B008
        ..., help="GitHub repository in format owner/repo"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Force deletion even if hashes don't match"
    ),
):
    """
    Uninstall fonts from a GitHub repository.
    """
    installed_file = Path.home() / ".fontpm" / "installed.json"
    if not installed_file.exists():
        console.print("[yellow]No installed fonts data found.[/yellow]")
        return

    try:
        with open(installed_file) as f:
            installed_data: Dict[str, Dict[str, FontEntry]] = json.load(f)
    except Exception as e:
        console.print(f"[red]Error loading installed data: {e}[/red]")
        raise typer.Exit(1) from e

    dest_dir = default_path
    deleted_count = 0

    for repo_arg in repo:
        if repo_arg not in installed_data:
            console.print(f"[yellow]No fonts installed from {repo_arg}.[/yellow]")
            continue

        fonts = installed_data[repo_arg]
        remaining: Dict[str, FontEntry] = {}
        for filename, entry in fonts.items():
            font_path = dest_dir / filename

            if not font_path.exists():
                console.print(
                    f"[yellow]Font {filename} not found in {dest_dir}.[/yellow]"
                )
                remaining[filename] = entry
                continue

            try:
                current_hash = hashlib.sha256(font_path.read_bytes()).hexdigest()
            except Exception as e:
                console.print(f"[yellow]Could not hash {filename}: {e}[/yellow]")
                remaining[filename] = entry
                continue

            if current_hash == entry["hash"] or force:
                try:
                    font_path.unlink()
                    console.print(f"[green]Deleted {filename} from {repo_arg}.[/green]")
                    deleted_count += 1
                except Exception as e:
                    console.print(f"[red]Could not delete {filename}: {e}[/red]")
                    remaining[filename] = entry
            else:
                console.print(
                    f"[yellow]Font {filename} has been modified. Use --force to delete.[/yellow]"
                )
                remaining[filename] = entry

        if remaining:
            installed_data[repo_arg] = remaining
        else:
            del installed_data[repo_arg]

    try:
        with open(installed_file, "w") as f:
            json.dump(installed_data, f, indent=2)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not update installed data: {e}[/yellow]")

    console.print(
        f"[green]Uninstalled {deleted_count} font{'' if deleted_count == 1 else 's'}.[/green]"
    )


@app.command()
def is_variable(
    font_path: str = typer.Argument(..., help="Path to the font file to check"),
):
    """
    Check if a font file is variable or static.
    """
    try:
        if is_variable_font(font_path):
            console.print("This is a variable font.")
        else:
            console.print("This is a static font.")
    except Exception as e:
        console.print(f"[red]Error checking font: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def update(
    repo: List[str] = typer.Argument(  # noqa: B008
        default_factory=list,
        help="GitHub repository in format owner/repo. If not specified, update all.",
    ),
):
    """
    Update installed fonts to the latest versions.
    """
    installed_file = Path.home() / ".fontpm" / "installed.json"
    if not installed_file.exists():
        console.print("[yellow]No installed fonts data found.[/yellow]")
        return

    try:
        with open(installed_file) as f:
            installed_data: Dict[str, Dict[str, FontEntry]] = json.load(f)
    except Exception as e:
        console.print(f"[red]Error loading installed data: {e}[/red]")
        raise typer.Exit(1) from e

    from packaging.version import Version

    updated_count = 0
    repos_to_update: List[Tuple[str, str, str, str, str, List[FontEntry]]] = []

    repos_to_check = list(installed_data.keys()) if not repo else repo

    # Warn for repos not installed
    for r in repo:
        if r not in installed_data:
            console.print(f"[yellow]No fonts installed from {r}.[/yellow]")

    for repo_arg in repos_to_check:
        if repo_arg not in installed_data:
            continue

        fonts = installed_data[repo_arg]
        if not fonts:
            continue

        # Assume all have same version
        installed_version = list(fonts.values())[0]["version"]

        try:
            owner, repo_name = repo_arg.split("/")
        except ValueError:
            console.print(f"[red]Invalid repo format in data: {repo_arg}[/red]")
            continue

        try:
            url = f"https://api.github.com/repos/{owner}/{repo_name}/releases/latest"
            response = httpx.get(url)
            response.raise_for_status()
            release_data = response.json()
            latest_version = release_data["tag_name"]
        except Exception as e:
            console.print(
                f"[yellow]Could not fetch latest for {repo_arg}: {e}[/yellow]"
            )
            continue

        # Strip 'v' if present
        def clean_version(v: str) -> str:
            return v.lstrip("v")

        try:
            if Version(clean_version(latest_version)) > Version(
                clean_version(installed_version)
            ):
                repos_to_update.append(
                    (
                        repo_arg,
                        installed_version,
                        latest_version,
                        owner,
                        repo_name,
                        list(fonts.values()),
                    )
                )
        except Exception as e:
            console.print(
                f"[yellow]Could not compare versions for {repo_arg}: {e}[/yellow]"
            )

    for (
        repo_arg,
        installed_version,
        latest_version,
        owner,
        repo_name,
        fonts,
    ) in repos_to_update:
        console.print(
            f"[bold]Updating {repo_arg} from {installed_version} to {latest_version}...[/bold]"
        )
        # Uninstall old
        dest_dir = default_path
        for font_info in fonts:
            filename = font_info["filename"]
            font_path = dest_dir / filename
            if font_path.exists():
                try:
                    font_path.unlink()
                except Exception as e:
                    console.print(f"[red]Could not delete {filename}: {e}[/red]")
        # Remove from data
        del installed_data[repo_arg]
        # Save
        try:
            with open(installed_file, "w") as f:
                json.dump(installed_data, f, indent=2)
        except Exception as e:
            console.print(
                f"[yellow]Warning: Could not update installed data: {e}[/yellow]"
            )
        # Install new
        install_single_repo(
            owner,
            repo_name,
            "latest",
            default_priorities,
            default_path,
            False,
            True,
            True,
        )
        updated_count += 1

    for repo_arg in repos_to_check:
        if repo_arg in installed_data and repo_arg not in [
            r[0] for r in repos_to_update
        ]:
            fonts = installed_data[repo_arg]
            if fonts:
                installed_version = list(fonts.values())[0]["version"]
                console.print(
                    f"[dim]{repo_arg} is up to date ({installed_version}).[/dim]"
                )


@app.command()
def export(
    output: str = typer.Option(
        "fontpm-fonts.json", "--output", "-o", help="Output file path"
    ),
    stdout: bool = typer.Option(
        False, "--stdout", help="Output to stdout instead of file"
    ),
):
    """
    Export the installed font library to a shareable file.
    """
    installed_file = Path.home() / ".fontpm" / "installed.json"
    if not installed_file.exists():
        console.print("[yellow]No installed fonts data found.[/yellow]")
        return

    try:
        with open(installed_file) as f:
            data: Dict[str, Dict[str, FontEntry]] = json.load(f)
    except Exception as e:
        console.print(f"[red]Error loading installed data: {e}[/red]")
        raise typer.Exit(1) from e

    exported: Dict[str, Dict[str, ExportedFontEntry]] = {}
    for repo, fonts in data.items():
        exported[repo] = {}
        for filename, entry in fonts.items():
            exported[repo][filename] = {
                "filename": entry["filename"],
                "type": entry["type"],
                "version": entry["version"],
            }

    if stdout:
        console.print(json.dumps(exported, indent=2))
    else:
        try:
            with open(output, "w") as f:
                json.dump(exported, f, indent=2)
            console.print(f"[green]Exported to {output}[/green]")
        except Exception as e:
            console.print(f"[red]Error writing to {output}: {e}[/red]")
            raise typer.Exit(1) from e


@app.command("import")
def import_fonts(
    file: str = typer.Option(
        "fontpm-fonts.json",
        "--input",
        "-i",
        help="Path to the exported font library file",
    ),
    force: bool = typer.Option(False, "--force", help="Force reinstall"),
    local: bool = typer.Option(
        False,
        "--local",
        "-l",
        help="Install fonts to current directory instead of default",
    ),
):
    """
    Import a font library from an exported file.
    """
    try:
        with open(file) as f:
            exported: Dict[str, Dict[str, ExportedFontEntry]] = json.load(f)
    except Exception as e:
        console.print(f"[red]Error loading {file}: {e}[/red]")
        raise typer.Exit(1) from e

    for repo, fonts in exported.items():
        if not fonts:
            continue

        # Get unique types
        types = list({entry["type"] for entry in fonts.values()})
        # Assume all have same version
        version = list(fonts.values())[0]["version"]
        # Set priorities to include all types
        priorities = types  # Order doesn't matter much, as we use keep_multiple

        keep_multiple = len(types) > 1

        try:
            owner, repo_name = repo.split("/")
        except ValueError:
            console.print(f"[red]Invalid repo format: {repo}[/red]")
            continue

        install_single_repo(
            owner,
            repo_name,
            version,
            priorities,
            Path.cwd() if local else default_path,
            local,
            force,
            keep_multiple,
        )


if __name__ == "__main__":
    app()
