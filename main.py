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


# Constants
ARCHIVE_EXTENSIONS = [".zip", ".tar.xz", ".tar.gz", ".tgz"]
VALID_FORMATS = [
    "variable-ttf",
    "otf",
    "static-ttf",
    "variable-woff2",
    "variable-woff",
    "static-woff2",
    "static-woff",
]
DEFAULT_PRIORITIES = ["variable-ttf", "otf", "static-ttf"]
DEFAULT_PATH = Path.home() / "Library" / "Fonts"
CONFIG_FILE = Path.home() / ".fontpm" / "config"
INSTALLED_FILE = Path.home() / ".fontpm" / "installed.json"


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
    for ext in ARCHIVE_EXTENSIONS:
        if name.endswith(ext):
            return name[: -len(ext)], ext
    return name, ""


# Load default format from config file
def load_config() -> Tuple[List[str], Path]:
    """Load configuration from config file."""
    priorities = DEFAULT_PRIORITIES.copy()
    path = DEFAULT_PATH

    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("format="):
                        value = line.split("=", 1)[1].strip()
                        if value == "auto":
                            continue
                        parsed_priorities = [p.strip() for p in value.split(",")]
                        if all(
                            p in ["variable-ttf", "otf", "static-ttf"]
                            for p in parsed_priorities
                        ):
                            priorities = parsed_priorities
                    elif line.startswith("path="):
                        value = line.split("=", 1)[1].strip()
                        if value:
                            path = Path(value)
        except Exception:
            console.print("[yellow]Warning: Could not load config file.[/yellow]")

    return priorities, path


default_priorities, default_path = load_config()


def load_installed_data() -> Dict[str, Dict[str, FontEntry]]:
    """Load installed fonts data from file."""
    if not INSTALLED_FILE.exists():
        return {}
    try:
        with open(INSTALLED_FILE) as f:
            return json.load(f)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load installed data: {e}[/yellow]")
        return {}


def save_installed_data(data: Dict[str, Dict[str, FontEntry]]) -> None:
    """Save installed fonts data to file."""
    INSTALLED_FILE.parent.mkdir(exist_ok=True)
    try:
        with open(INSTALLED_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not save installed data: {e}[/yellow]")


def parse_repo(repo_arg: str) -> Tuple[str, str]:
    """Parse owner/repo string into owner and repo_name."""
    try:
        owner, repo_name = repo_arg.split("/")
        return owner, repo_name
    except ValueError as e:
        raise ValueError(f"Invalid repo format: {repo_arg}. Use owner/repo") from e


def categorize_fonts(
    font_files: List[Path],
) -> Tuple[
    List[Path], List[Path], List[Path], List[Path], List[Path], List[Path], List[Path]
]:
    """Categorize font files into variable/static and by type."""
    ttf_files = [f for f in font_files if f.suffix.lower() == ".ttf"]
    otf_files = [f for f in font_files if f.suffix.lower() == ".otf"]
    woff_files = [f for f in font_files if f.suffix.lower() == ".woff"]
    woff2_files = [f for f in font_files if f.suffix.lower() == ".woff2"]

    variable_ttfs: List[Path] = []
    static_ttfs: List[Path] = []
    for ttf in ttf_files:
        try:
            if is_variable_font(str(ttf)):
                variable_ttfs.append(ttf)
            else:
                static_ttfs.append(ttf)
        except Exception:
            static_ttfs.append(ttf)

    variable_woffs: List[Path] = []
    static_woffs: List[Path] = []
    for woff in woff_files:
        try:
            if is_variable_font(str(woff)):
                variable_woffs.append(woff)
            else:
                static_woffs.append(woff)
        except Exception:
            static_woffs.append(woff)

    variable_woff2s: List[Path] = []
    static_woff2s: List[Path] = []
    for woff2 in woff2_files:
        try:
            if is_variable_font(str(woff2)):
                variable_woff2s.append(woff2)
            else:
                static_woff2s.append(woff2)
        except Exception:
            static_woff2s.append(woff2)

    return (
        variable_ttfs,
        static_ttfs,
        otf_files,
        variable_woffs,
        static_woffs,
        variable_woff2s,
        static_woff2s,
    )


def fetch_release_info(
    owner: str, repo_name: str, release: str
) -> Tuple[str, List[Asset]]:
    """Fetch release information from GitHub API."""
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
        return version, assets


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


def download_and_extract_archive(archive_url: str, archive_ext: str) -> Path:
    """Download and extract the archive to a temporary directory."""
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

    with console.status("[bold green]Extracting..."):
        if archive_ext == ".zip":
            with zipfile.ZipFile(tmp_path, "r") as archive_ref:
                archive_ref.extractall(extract_dir)
        else:
            # For tar archives
            mode = "r:xz" if archive_ext == ".tar.xz" else "r:gz"
            with tarfile.open(tmp_path, mode) as archive_ref:
                archive_ref.extractall(extract_dir)

    return extract_dir


def select_fonts(
    categorized_fonts: Tuple[List[Path], ...],
    priorities: List[str],
    weights: List[int],
    styles: List[str],
) -> Tuple[List[Path], str]:
    """Select fonts based on priorities and weights."""
    (
        variable_ttfs,
        static_ttfs,
        otf_files,
        variable_woffs,
        static_woffs,
        variable_woff2s,
        static_woff2s,
    ) = categorized_fonts

    selected_fonts: List[Path] = []
    selected_pri = ""
    for pri in priorities:
        if pri == "variable-woff2" and variable_woff2s:
            if weights or styles != ["roman", "italic"]:
                console.print(
                    "[yellow]Warning: Weights and styles are ignored for variable fonts.[/yellow]"
                )
            selected_fonts = variable_woff2s
            selected_pri = pri
            break
        elif pri == "static-woff2" and static_woff2s:
            candidates = static_woff2s
            if weights:
                candidates = [
                    f for f in candidates if get_font_weight(str(f)) in weights
                ]
            if styles != ["roman", "italic"]:
                candidates = [
                    f
                    for f in candidates
                    if (get_font_italic(str(f)) and "italic" in styles)
                    or (not get_font_italic(str(f)) and "roman" in styles)
                ]
            if candidates:
                selected_fonts = candidates
                selected_pri = pri
                break
        elif pri == "variable-woff" and variable_woffs:
            if weights or styles != ["roman", "italic"]:
                console.print(
                    "[yellow]Warning: Weights and styles are ignored for variable fonts.[/yellow]"
                )
            selected_fonts = variable_woffs
            selected_pri = pri
            break
        elif pri == "static-woff" and static_woffs:
            candidates = static_woffs
            if weights:
                candidates = [
                    f for f in candidates if get_font_weight(str(f)) in weights
                ]
            if styles != ["roman", "italic"]:
                candidates = [
                    f
                    for f in candidates
                    if (get_font_italic(str(f)) and "italic" in styles)
                    or (not get_font_italic(str(f)) and "roman" in styles)
                ]
            if candidates:
                selected_fonts = candidates
                selected_pri = pri
                break
        elif pri == "variable-ttf" and variable_ttfs:
            if weights or styles != ["roman", "italic"]:
                console.print(
                    "[yellow]Warning: Weights and styles are ignored for variable fonts.[/yellow]"
                )
            selected_fonts = variable_ttfs
            selected_pri = pri
            break
        elif pri == "otf" and otf_files:
            # OTF are static, filter by weights and styles
            candidates = otf_files
            if weights:
                candidates = [
                    f for f in candidates if get_font_weight(str(f)) in weights
                ]
            if styles != ["roman", "italic"]:
                candidates = [
                    f
                    for f in candidates
                    if (get_font_italic(str(f)) and "italic" in styles)
                    or (not get_font_italic(str(f)) and "roman" in styles)
                ]
            if candidates:
                selected_fonts = candidates
                selected_pri = pri
                break
        elif pri == "static-ttf" and static_ttfs:
            candidates = static_ttfs
            if weights:
                candidates = [
                    f for f in candidates if get_font_weight(str(f)) in weights
                ]
            if styles != ["roman", "italic"]:
                candidates = [
                    f
                    for f in candidates
                    if (get_font_italic(str(f)) and "italic" in styles)
                    or (not get_font_italic(str(f)) and "roman" in styles)
                ]
            if candidates:
                selected_fonts = candidates
                selected_pri = pri
                break

    return selected_fonts, selected_pri


def install_fonts(
    selected_fonts: List[Path],
    dest_dir: Path,
    repo_arg: str,
    version: str,
    selected_pri: str,
    local: bool,
) -> None:
    """Install selected fonts to destination directory and update installed data."""
    if not selected_fonts:
        console.print(
            f"[yellow]No font files found in the archive for {repo_arg}.[/yellow]"
        )
        return

    with console.status("[bold green]Moving fonts..."):
        for font_file in selected_fonts:
            shutil.move(str(font_file), str(dest_dir / font_file.name))

    if not local:
        installed_data = load_installed_data()
        repo_key = repo_arg
        if repo_key not in installed_data:
            installed_data[repo_key] = {}
        for font_file in selected_fonts:
            try:
                file_hash = hashlib.sha256(
                    (dest_dir / font_file.name).read_bytes()
                ).hexdigest()
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
        save_installed_data(installed_data)

    number_installed_fonts = len(selected_fonts)
    console.print(
        f"[green]Moved {number_installed_fonts} font{'' if number_installed_fonts == 1 else 's'} from "
        f"{repo_arg} to: {dest_dir}[/green]"
    )


def is_variable_font(font_path: str) -> bool:
    """
    Check if a font file is a variable font.
    """
    font = TTFont(font_path)
    return "fvar" in font


def get_font_weight(font_path: str) -> int:
    """
    Get the weight class of a font file.
    """
    try:
        font = TTFont(font_path)
        os2_table = font["OS/2"]  # type: ignore
        return os2_table.usWeightClass  # type: ignore
    except Exception:
        return 400  # default to regular


def get_font_italic(font_path: str) -> bool:
    """
    Check if a font file is italic.
    """
    try:
        font = TTFont(font_path)
        os2_table = font["OS/2"]  # type: ignore
        return (os2_table.fsSelection & 0x01) != 0  # type: ignore
    except Exception:
        return False


def install_single_repo(
    owner: str,
    repo_name: str,
    release: str,
    priorities: list[str],
    dest_dir: Path,
    local: bool,
    force: bool,
    keep_multiple: bool,
    weights: List[int],
    styles: List[str],
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

    # Check if already installed
    if not local:
        installed_data = load_installed_data()
        if repo_arg in installed_data and installed_data[repo_arg] and not force:
            console.print(
                f"[yellow]Already installed from {repo_arg}. "
                "Use --force to reinstall or change version.[/yellow]"
            )
            return

        installed_types = [
            entry.get("type")
            for entry in installed_data.get(repo_arg, {}).values()
            if "type" in entry
        ]
        if installed_types and not keep_multiple and not force:
            console.print(
                f"[yellow]Already installed other types from {repo_arg}. "
                "Use --keep-multiple to install additional types or --force to overwrite.[/yellow]"
            )
            return

    extract_dir = None
    try:
        version, assets = fetch_release_info(owner, repo_name, release)
        chosen_asset = select_archive_asset(assets)
        archive_url = chosen_asset["browser_download_url"]
        archive_name = chosen_asset["name"]
        _, archive_ext = get_base_and_ext(archive_name)

        console.print(f"Found archive: {archive_name}")

        extract_dir = download_and_extract_archive(archive_url, archive_ext)

        # Find all font files
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

        # Check for type conflict
        if selected_fonts and not local:
            installed_data = load_installed_data()
            installed_types = [
                entry.get("type")
                for entry in installed_data.get(repo_arg, {}).values()
                if "type" in entry
            ]
            if selected_pri in installed_types and not force:
                console.print(
                    f"[yellow]Already installed {selected_pri} from {repo_arg}. "
                    "Use --force to reinstall.[/yellow]"
                )
                return

        install_fonts(selected_fonts, dest_dir, repo_arg, version, selected_pri, local)

    except Exception as e:
        console.print(f"[red]Error installing from {repo_arg}: {e}[/red]")
        raise
    finally:
        if extract_dir:
            shutil.rmtree(str(extract_dir))


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
    Install fonts from a GitHub release.
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

    dest_dir = Path.cwd() if local else default_path
    dest_dir.mkdir(exist_ok=True)

    for repo_arg in repo:
        try:
            owner, repo_name = parse_repo(repo_arg)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            continue
        install_single_repo(
            owner,
            repo_name,
            release,
            priorities,
            dest_dir,
            local,
            force,
            keep_multiple,
            parsed_weights,
            parsed_styles,
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
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line:
                        k, v = line.split("=", 1)
                        current_config[k] = v
        except Exception:
            console.print("[yellow]Warning: Could not load existing config.[/yellow]")

    if key == "format":
        priorities = [p.strip() for p in value.split(",")]
        if not all(p in VALID_FORMATS for p in priorities):
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
        with open(CONFIG_FILE, "w") as f:
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
    installed_data = load_installed_data()
    if not installed_data:
        console.print("[yellow]No installed fonts data found.[/yellow]")
        return

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

    save_installed_data(installed_data)

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
    installed_data = load_installed_data()
    if not installed_data:
        console.print("[yellow]No installed fonts data found.[/yellow]")
        return

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
            owner, repo_name = parse_repo(repo_arg)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
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
        save_installed_data(installed_data)
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
            [],
            ["roman", "italic"],
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
    data = load_installed_data()
    if not data:
        console.print("[yellow]No installed fonts data found.[/yellow]")
        return

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
            [],
            ["roman", "italic"],
        )


if __name__ == "__main__":
    app()
