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
    repo: str = typer.Argument(..., help="GitHub repository in format owner/repo"),
    release: str = typer.Argument("latest", help="Release tag"),
    format: str = typer.Option(
        "auto",
        help="Font format to prefer: auto (default priority), "
        "variable-ttf, otf, static-ttf",
    ),
):
    """
    Install fonts from a GitHub release.
    """
    try:
        owner, repo_name = repo.split("/")
    except ValueError as err:
        console.print("[red]Invalid repo format. Use owner/repo[/red]")
        raise typer.Exit(1) from err

    with console.status("[bold green]Fetching release info..."):
        if release == "latest":
            url = f"https://api.github.com/repos/{owner}/{repo_name}/releases/latest"
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
        a for a in assets if any(a["name"].endswith(ext) for ext in archive_extensions)
    ]
    if not archives:
        console.print("[red]No archive asset found in the release.[/red]")
        raise typer.Exit(1)

    # Function to get priority for extensions (lower is better)
    def get_priority(ext: str) -> int:
        priorities = {".tar.xz": 1, ".tar.gz": 2, ".tgz": 2, ".zip": 3}
        return priorities.get(ext, 4)

    # Function to get base name and extension
    def get_base_and_ext(name: str) -> tuple[str, str]:
        for ext in archive_extensions:
            if name.endswith(ext):
                return name[: -len(ext)], ext
        return name, ""

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

    dest_dir = Path.home() / "Desktop"
    dest_dir.mkdir(exist_ok=True)

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
        if format == "variable-ttf":
            selected_fonts = variable_ttfs
        elif format == "otf":
            selected_fonts = otf_files
        elif format == "static-ttf":
            selected_fonts = static_ttfs
        else:  # auto
            if variable_ttfs:
                selected_fonts = variable_ttfs
            elif otf_files:
                selected_fonts = otf_files
            elif static_ttfs:
                selected_fonts = static_ttfs

        if selected_fonts:
            with console.status("[bold green]Moving fonts..."):
                for font_file in selected_fonts:
                    shutil.move(str(font_file), str(dest_dir / font_file.name))
            console.print(
                f"[green]Moved {len(selected_fonts)} font(s) to: {dest_dir}[/green]"
            )
        else:
            console.print("[yellow]No font files found in the archive.[/yellow]")


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
