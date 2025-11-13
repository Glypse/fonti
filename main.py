import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List

import httpx
import typer
from fontTools.ttLib import TTFont
from rich.console import Console

app = typer.Typer()
console = Console()


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

    assets: List[Dict[str, Any]] = release_data.get("assets", [])
    zip_assets = [a for a in assets if a["name"].endswith(".zip")]
    if not zip_assets:
        console.print("[red]No .zip asset found in the release.[/red]")
        raise typer.Exit(1)

    zip_asset = zip_assets[0]  # Take the first one
    zip_url: str = zip_asset["browser_download_url"]
    zip_name: str = zip_asset["name"]

    console.print(f"Found zip: {zip_name}")

    extract_dir = Path.home() / "Desktop"
    extract_dir.mkdir(exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)

        with console.status("[bold green]Downloading zip..."):
            with httpx.stream("GET", zip_url, follow_redirects=True) as response:
                response.raise_for_status()
                with open(tmp_path, "wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)

        console.print("Download complete.")

        with console.status("[bold green]Extracting..."):
            with zipfile.ZipFile(tmp_path, "r") as zip_ref:
                zip_ref.extractall(extract_dir)

        tmp_path.unlink()  # Clean up temp file

    console.print(f"[green]Fonts extracted to: {extract_dir}[/green]")


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
