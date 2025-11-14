import hashlib
import json
import shutil
import tarfile
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, TypedDict

import httpx
import typer
from fontTools.ttLib import TTFont  # type: ignore
from rich.console import Console

app = typer.Typer()
console = Console()


# Load default format from config file
default_priorities = ["variable-ttf", "otf", "static-ttf"]
default_path = Path.home() / "Desktop"
config_file = Path.home() / ".fontpm" / "config"
old_config_file = Path.home() / ".fontpm"
if old_config_file.exists() and old_config_file.is_file():
    # Migrate old config
    config_file.parent.mkdir(exist_ok=True)
    import shutil

    shutil.move(str(old_config_file), str(config_file))
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


class Asset(TypedDict):
    name: str
    size: int
    browser_download_url: str


def is_variable_font(font_path: str) -> bool:
    """
    Check if a font file is a variable font.
    """
    font = TTFont(font_path)
    return "fvar" in font


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
):
    """
    Install fonts from a GitHub release.
    """
    priorities = [p.strip() for p in format.split(",")]
    valid_formats = ["variable-ttf", "otf", "static-ttf"]
    if not priorities or not all(p in valid_formats for p in priorities):
        console.print(
            "[red]Invalid --format value. Must be comma-separated list of: "
            f"{', '.join(valid_formats)}[/red]"
        )
        raise typer.Exit(1)

    dest_dir = Path.cwd() if local else default_path
    dest_dir.mkdir(exist_ok=True)

    # Function to get base name and extension
    def get_base_and_ext(name: str) -> tuple[str, str]:
        for ext in archive_extensions:
            if name.endswith(ext):
                return name[: -len(ext)], ext
        return name, ""

    for repo_arg in repo:
        console.print(f"[bold]Installing from {repo_arg}...[/bold]")
        try:
            owner, repo_name = repo_arg.split("/")
        except ValueError:
            console.print(f"[red]Invalid repo format: {repo_arg}. Use owner/repo[/red]")
            continue

        with console.status("[bold green]Fetching release info..."):
            if release == "latest":
                url = (
                    f"https://api.github.com/repos/{owner}/{repo_name}/releases/latest"
                )
            else:
                # Ensure release tag has 'v' prefix if not present
                if not release.startswith("v"):
                    release = f"v{release}"
                url = f"https://api.github.com/repos/{owner}/{repo_name}/releases/tags/{release}"

            response = httpx.get(url)
            response.raise_for_status()
            release_data: Dict[str, Any] = response.json()

        assets: List[Asset] = release_data.get("assets", [])
        archive_extensions = [".zip", ".tar.xz", ".tar.gz", ".tgz"]
        archives = [
            a
            for a in assets
            if any(a["name"].endswith(ext) for ext in archive_extensions)
        ]
        if not archives:
            console.print(
                f"[red]No archive asset found in the release for {repo_arg}.[/red]"
            )
            continue

        # Function to get priority for extensions (lower is better)
        def get_priority(ext: str) -> int:
            priorities = {".tar.xz": 1, ".tar.gz": 2, ".tgz": 2, ".zip": 3}
            return priorities.get(ext, 4)

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

            # Select fonts in order of preference
            selected_fonts: list[Path] = []
            for pri in priorities:
                if pri == "variable-ttf" and variable_ttfs:
                    selected_fonts = variable_ttfs
                    break
                elif pri == "otf" and otf_files:
                    selected_fonts = otf_files
                    break
                elif pri == "static-ttf" and static_ttfs:
                    selected_fonts = static_ttfs
                    break

            # Track installed fonts for global installs
            if selected_fonts and not local:
                installed_file = Path.home() / ".fontpm" / "installed.json"
                installed_file.parent.mkdir(exist_ok=True)
                installed_data: Dict[str, List[Dict[str, str]]] = {}
                if installed_file.exists():
                    try:
                        with open(installed_file) as f:
                            installed_data = json.load(f)
                    except Exception:
                        pass  # Ignore load errors

                repo_key = repo_arg
                if repo_key not in installed_data:
                    installed_data[repo_key] = []
                for font_file in selected_fonts:
                    try:
                        file_hash = hashlib.sha256(font_file.read_bytes()).hexdigest()
                        installed_data[repo_key].append(
                            {"filename": font_file.name, "hash": file_hash}
                        )
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
                number_selected_fonts = len(selected_fonts)
                console.print(
                    f"[green]Moved {number_selected_fonts} font{'' if number_selected_fonts == 1 else 's'} from "
                    f"{repo_arg} to: {dest_dir}[/green]"
                )
            else:
                msg = f"[yellow]No font files found in the archive for {repo_arg}.[/yellow]"
                console.print(msg)


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
        if not all(p in ["variable-ttf", "otf", "static-ttf"] for p in priorities):
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
            installed_data: Dict[str, List[Dict[str, str]]] = json.load(f)
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
        remaining_fonts: List[Dict[str, str]] = []
        for font_info in fonts:
            filename = font_info["filename"]
            expected_hash = font_info["hash"]
            font_path = dest_dir / filename

            if not font_path.exists():
                console.print(
                    f"[yellow]Font {filename} not found in {dest_dir}.[/yellow]"
                )
                continue

            try:
                current_hash = hashlib.sha256(font_path.read_bytes()).hexdigest()
            except Exception as e:
                console.print(f"[yellow]Could not hash {filename}: {e}[/yellow]")
                continue

            if current_hash == expected_hash or force:
                try:
                    font_path.unlink()
                    console.print(f"[green]Deleted {filename} from {repo_arg}.[/green]")
                    deleted_count += 1
                except Exception as e:
                    console.print(f"[red]Could not delete {filename}: {e}[/red]")
            else:
                console.print(
                    f"[yellow]Font {filename} has been modified. Use --force to delete.[/yellow]"
                )
                remaining_fonts.append(font_info)

        if remaining_fonts:
            installed_data[repo_arg] = remaining_fonts
        else:
            del installed_data[repo_arg]

    try:
        with open(installed_file, "w") as f:
            json.dump(installed_data, f, indent=2)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not update installed data: {e}[/yellow]")

    console.print(f"[green]Uninstalled {deleted_count} font(s).[/green]")


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


if __name__ == "__main__":
    app()
