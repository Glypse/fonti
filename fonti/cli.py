from pathlib import Path
from typing import Dict, List

import httpx
import typer
from rich.console import Console

from .config import (
    cache,
    default_github_token,
    default_path,
    default_priorities,
    set_config,
)
from .constants import DEFAULT_CACHE_SIZE, FORMAT_HELP, VALID_FORMATS
from .google_fonts import fetch_google_fonts_repo, parse_repo
from .installer import install_single_repo

app = typer.Typer(rich_markup_mode="rich")
console = Console()

cache_app = typer.Typer(rich_markup_mode="rich")
app.add_typer(cache_app, name="cache")

config_app = typer.Typer(rich_markup_mode="rich")
app.add_typer(config_app, name="config")


@app.command()
def install(
    repo: List[str] = typer.Argument(  # noqa: B008
        ..., help="GitHub repository in format owner/repo or Google Font name"
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
    weights: str = typer.Option(
        "",
        "--weights",
        "-w",
        help="Comma-separated list of font weights to install (e.g., 400,700 or Regular,Bold)",
    ),
    style: str = typer.Option(
        "both",
        "--style",
        help="Font style to install: roman, italic, or both",
    ),
):
    """
    Install fonts from a GitHub release or Google Fonts.
    """
    priorities = [p.strip() for p in format.split(",")]
    if not priorities or not all(p in VALID_FORMATS for p in priorities):
        console.print(
            "[red]Invalid --format value. Must be comma-separated list of: "
            f"{', '.join(VALID_FORMATS)}[/red]"
        )
        raise typer.Exit(1)

    weight_map = {
        "thin": 100,
        "extralight": 200,
        "light": 300,
        "regular": 400,
        "medium": 500,
        "semibold": 600,
        "bold": 700,
        "extrabold": 800,
        "black": 900,
    }
    parsed_weights: List[int] = []
    if weights:
        for w in weights.split(","):
            w = w.strip()
            if w.isdigit():
                parsed_weights.append(int(w))
            else:
                w_lower = w.lower()
                if w_lower in weight_map:
                    parsed_weights.append(weight_map[w_lower])
                else:
                    console.print(f"[red]Unknown weight: {w}[/red]")
                    raise typer.Exit(1)

    if style not in ["roman", "italic", "both"]:
        console.print(
            "[red]Invalid --style value. Must be roman, italic, or both[/red]"
        )
        raise typer.Exit(1)

    parsed_styles = ["roman", "italic"] if style == "both" else [style]

    # Update registry if needed
    from .registry import update_registry

    update_registry()

    dest_dir = Path.cwd() if local else default_path
    dest_dir.mkdir(exist_ok=True)

    for repo_arg in repo:
        try:
            if "/" in repo_arg:
                owner, repo_name = parse_repo(repo_arg)
                repo_key = repo_name.lower()
                is_google_fonts = False
                extract_dir = None
                is_subdirectory = False
            else:
                # Google Fonts
                font_name = repo_arg
                owner, repo_name, extract_dir, is_subdirectory = (
                    fetch_google_fonts_repo(font_name)
                )
                repo_key = font_name.lower()
                is_google_fonts = True
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            continue
        install_single_repo(
            owner,
            repo_name,
            repo_key,
            release,
            priorities,
            dest_dir,
            local,
            force,
            parsed_weights,
            parsed_styles,
            is_google_fonts,
            pre_extract_dir=extract_dir,
            is_subdirectory=is_subdirectory,
        )


@config_app.command("format")
def config_format(value: str = typer.Argument(..., help=FORMAT_HELP)):
    """
    Set the default font format priorities.
    """
    set_config("format", value)


@config_app.command("path")
def config_path(
    value: str = typer.Argument(..., help="Path to the font installation directory")
):
    """
    Set the default font installation path.
    """
    set_config("path", value)


@config_app.command("cache-size")
def config_cache_size(
    value: str = typer.Argument(
        ..., help="Cache size in bytes (0 to disable caching, 'default' to reset)"
    )
):
    """
    Set the download cache size. Set to 0 to disable caching entirely, or 'default' to reset to the default size.
    """
    if value.lower() == "default":
        from .config import CONFIG_FILE

        current_config: Dict[str, str] = {}
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("cache-size="):
                        continue  # remove it
                    if "=" in line:
                        k, v = line.split("=", 1)
                        current_config[k] = v
        with open(CONFIG_FILE, "w") as f:
            for k, v in current_config.items():
                f.write(f"{k}={v}\n")
        console.print(
            f"[green]Reset cache-size to default: {DEFAULT_CACHE_SIZE}[/green]"
        )
    else:
        set_config("cache-size", value)


@config_app.command("github-token")
def config_github_token(
    value: str = typer.Argument(..., help="GitHub personal access token")
):
    """
    Set the GitHub personal access token for authenticated API requests.
    [dim]Optional: will help if you're encountering rate limits. To create your token, follow this link: https://github.com/settings/tokens/new?description=fonti&scopes=read:packages&default_expires_at=none[/dim]
    """
    set_config("github_token", value)


@config_app.command("google-fonts-direct")
def config_google_fonts_direct(
    value: str = typer.Argument(
        ...,
        help="Set to 'true' or 'false' to enable/disable direct Google Fonts download",
    )
):
    """
    Set whether to always download Google Fonts directly from the Google Fonts repo subdirectory instead of searching for original repos.
    """  # noqa: E501
    set_config("google_fonts_direct", value)


@config_app.command("registry-check-interval")
def config_registry_check_interval(
    value: str = typer.Argument(
        ..., help="Registry check interval in seconds (default: 86400 for 24 hours)"
    )
):
    """
    Set the interval for checking registry updates in seconds.
    """
    set_config("registry_check_interval", value)


@config_app.command("update-registry")
def config_update_registry():
    """
    Manually update the Google Fonts registry.
    """
    from .registry import update_registry

    update_registry(force=True)
    """
    Test GitHub authentication by checking the token validity.
    """
    if not default_github_token:
        console.print(
            "[red]No GitHub token set. Use 'fonti config github-token <token>' to set one.[/red]"
        )
        return

    try:
        headers: Dict[str, str] = {"Authorization": f"Bearer {default_github_token}"}
        response = httpx.get("https://api.github.com/user", headers=headers)
        if response.status_code == 200:
            user_data = response.json()
            console.print(
                f"[green]Authentication successful! Logged in as: {user_data['login']}[/green]"
            )
        elif response.status_code == 401:
            console.print("[red]Authentication failed: Invalid token.[/red]")
        else:
            console.print(
                f"[red]Authentication failed: HTTP {response.status_code}[/red]"
            )
    except Exception as e:
        console.print(f"[red]Error testing authentication: {e}[/red]")


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
    from .uninstaller import uninstall_fonts

    uninstall_fonts(repo, force)


@app.command()
def update(
    repo: str = typer.Argument(
        None, help="Specific repos to update (leave empty for all)"
    ),
    changelog: bool = typer.Option(False, "--changelog", help="Show changelog"),
):
    """
    Update installed fonts to the latest versions.
    """
    repos = [repo] if repo else []
    from .registry import update_registry
    from .updater import update_fonts

    update_registry()
    update_fonts(repos, changelog)


@app.command()
def export(
    output: str = typer.Option(
        "fonti-fonts.json", "--output", "-o", help="Output file path"
    ),
    stdout: bool = typer.Option(
        False, "--stdout", help="Output to stdout instead of file"
    ),
):
    """
    Export the installed font library to a shareable file.
    """
    from .library import export_fonts

    export_fonts(output, stdout)


@app.command("import")
def import_fonts(
    file: str = typer.Option(
        "fonti-fonts.json",
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
    from .library import import_fonts as import_fonts_func

    import_fonts_func(file, force, local)


@app.command()
def fix(
    backup: bool = typer.Option(
        False, "--backup", "-b", help="Create a backup of installed.json before fixing"
    ),
    granular: bool = typer.Option(
        False, "--granular", "-g", help="Ask for confirmation for each fix individually"
    ),
):
    """
    Fix the installed.json file by removing duplicates and other issues.
    """
    from .library import fix_fonts

    fix_fonts(backup, granular)


@cache_app.command("purge")
def purge():
    """
    Purge the download cache.
    """
    if cache is None:
        console.print("[yellow]Caching is disabled.[/yellow]")
    else:
        cache.clear()
        console.print("[green]Cache purged.[/green]")
