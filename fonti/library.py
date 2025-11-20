import hashlib
import json
import logging
import shutil
from collections import defaultdict
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Tuple

import typer
from fontTools.ttLib import TTFont  # pyright: ignore[reportMissingTypeStubs]
from rich.console import Console

from .config import (
    INSTALLED_FILE,
    default_path,
    default_priorities,
    load_installed_data,
    save_installed_data,
)
from .fonts import is_variable_font
from .google_fonts import parse_repo
from .installer import install_single_repo

if TYPE_CHECKING:
    from .types import ExportedFontEntry

console = Console()
logger = logging.getLogger(__name__)


def export_fonts(output: str, stdout: bool) -> None:
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
            exported_entry: ExportedFontEntry = {
                "type": entry["type"],
                "version": entry["version"],
            }
            if "owner" in entry:
                exported_entry["owner"] = entry["owner"]
            if "repo_name" in entry:
                exported_entry["repo_name"] = entry["repo_name"]
            exported[repo][filename] = exported_entry

    if stdout:
        console.print(json.dumps(exported, indent=2))
    else:
        try:
            logger.debug(f"Writing exported data to {output}")
            with open(output, "w") as f:
                json.dump(exported, f, indent=2)
            console.print(f"[green]Exported to {output}[/green]")
        except Exception as e:
            console.print(f"[red]Error writing to {output}: {e}[/red]")
            raise typer.Exit(1) from e


def import_fonts(file: str, force: bool, local: bool) -> None:
    """
    Import a font library from an exported file.
    """
    try:
        logger.debug(f"Loading exported data from {file}")
        with open(file) as f:
            exported: Dict[str, Dict[str, ExportedFontEntry]] = json.load(f)
    except Exception as e:
        console.print(f"[red]Error loading {file}: {e}[/red]")
        raise typer.Exit(1) from e

    for repo, fonts in exported.items():
        if not fonts:
            continue

        # Get unique types
        types = list({entry.get("type", "static-ttf") for entry in fonts.values()})
        # Assume all have same version
        version = list(fonts.values())[0].get("version", "latest")
        first_entry = list(fonts.values())[0]
        if "owner" in first_entry:
            owner = first_entry["owner"]
            repo_name = repo
        else:
            # Old format, repo is owner/name
            try:
                owner, repo_name = repo.split("/")
            except ValueError:
                console.print(f"[red]Invalid repo format in import: {repo}[/red]")
                continue
        # Set priorities to the first type
        priorities = [types[0]] if types else []

        install_single_repo(
            owner,
            repo_name,
            repo,
            version,
            priorities,
            Path.cwd() if local else default_path,
            local,
            force,
            [],
            ["roman", "italic"],
        )


def fix_fonts(backup: bool, granular: bool) -> None:
    """
    Fix the installed.json file by removing duplicates and other issues.
    """
    installed_data = load_installed_data()
    if not installed_data:
        console.print("[yellow]No installed fonts data found.[/yellow]")
        return

    if backup:
        backup_file = INSTALLED_FILE.with_suffix(".json.backup")
        try:
            logger.debug(f"Creating backup from {INSTALLED_FILE} to {backup_file}")
            shutil.copy(INSTALLED_FILE, backup_file)
            console.print(f"[green]Backup created: {backup_file}[/green]")
        except Exception as e:
            console.print(f"[red]Failed to create backup: {e}[/red]")
            raise typer.Exit(1) from e

    def del_repo(repo: str) -> int:
        font_count = len(installed_data[repo])
        del installed_data[repo]
        return font_count

    def del_entry(repo: str, filename: str) -> int:
        if repo in installed_data and filename in installed_data[repo]:
            del installed_data[repo][filename]
            # If repo now empty, remove it
            if not installed_data[repo]:
                del installed_data[repo]
                console.print(f"[green]Removed empty repo {repo}[/green]")
            return 1
        return 0

    def del_duplicate(repo: str, filename: str) -> int:
        if repo in installed_data and filename in installed_data[repo]:
            del installed_data[repo][filename]
            # If repo now empty, remove it
            if not installed_data[repo]:
                del installed_data[repo]
                console.print(f"[green]Removed empty repo {repo}[/green]")
            return 1
        return 0

    def update_hash(repo: str, filename: str, new_hash: str) -> int:
        if repo in installed_data and filename in installed_data[repo]:
            installed_data[repo][filename]["hash"] = new_hash
            return 1
        return 0

    def reinstall_repo(repo: str) -> int:
        try:
            first_entry = list(installed_data[repo].values())[0]
            owner = first_entry["owner"]
            repo_name = first_entry["repo_name"]
            install_single_repo(
                owner,
                repo_name,
                repo,
                "latest",
                default_priorities,
                default_path,
                False,
                True,
                [],
                ["roman", "italic"],
            )
            return 1
        except Exception as e:
            console.print(f"[red]Failed to reinstall {repo}: {e}[/red]")
            return 0

    actions: List[Tuple[str, Callable[[], int]]] = []
    invalid_repos: List[str] = []
    invalid_entries: List[Tuple[str, str]] = []
    repos_to_reinstall: Dict[str, str] = {}

    # Detect invalid repos
    invalid_repos = []
    for repo in installed_data.keys():
        if "/" in repo:
            try:
                parse_repo(repo)
            except ValueError:
                invalid_repos.append(repo)
                actions.append(
                    (f"Remove invalid repo: {repo}", partial(del_repo, repo))
                )

    # Detect type/extension mismatches
    type_to_ext = {
        "variable-ttf": ".ttf",
        "static-ttf": ".ttf",
        "otf": ".otf",
        "variable-woff": ".woff",
        "static-woff": ".woff",
        "variable-woff2": ".woff2",
        "static-woff2": ".woff2",
    }
    invalid_entries = []
    for repo, fonts in installed_data.items():
        if repo in invalid_repos:
            continue  # Will be removed anyway
        for filename, entry in fonts.items():
            expected_ext = type_to_ext.get(entry["type"])
            if expected_ext and not filename.endswith(expected_ext):
                invalid_entries.append((repo, filename))
                actions.append(
                    (
                        f"Remove invalid entry: {repo}/{filename} (type/extension mismatch)",
                        partial(del_entry, repo, filename),
                    )
                )

    # Detect duplicates: filename -> list of repos
    filename_to_repos: Dict[str, List[str]] = defaultdict(list)
    for repo, fonts in installed_data.items():
        if repo in invalid_repos:
            continue
        for filename in fonts.keys():
            if (repo, filename) not in invalid_entries:
                filename_to_repos[filename].append(repo)

    duplicates = {
        filename: repos
        for filename, repos in filename_to_repos.items()
        if len(repos) > 1
    }

    # Collect actions for duplicates
    for filename, repos in duplicates.items():
        for repo in repos[1:]:
            actions.append(
                (
                    f"Remove duplicate {filename} from {repo}",
                    partial(del_duplicate, repo, filename),
                )
            )

    # Detect file issues
    for repo, fonts in installed_data.items():
        if repo in invalid_repos:
            continue
        for filename, entry in fonts.items():
            if (repo, filename) in invalid_entries:
                continue
            # Check if it's a duplicate to be removed
            is_duplicate_to_remove = any(
                repo == r and filename == f
                for f, repos in duplicates.items()
                for r in repos[1:]
            )
            if is_duplicate_to_remove:
                continue
            file_path = default_path / filename
            if not file_path.exists():
                repos_to_reinstall[repo] = "missing file(s)"
            else:
                # Validate font
                try:
                    TTFont(str(file_path))
                    is_var = is_variable_font(str(file_path))
                    expected_var = entry["type"].startswith("variable-")
                    if expected_var != is_var:
                        repos_to_reinstall[repo] = "variable/static mismatch"
                        continue
                except Exception:
                    repos_to_reinstall[repo] = "invalid font file(s)"
                    continue
                # If valid, check hash
                try:
                    current_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()
                    if current_hash != entry["hash"]:
                        actions.append(
                            (
                                f"Update hash for modified file: {repo}/{filename}",
                                partial(update_hash, repo, filename, current_hash),
                            )
                        )
                except Exception:
                    repos_to_reinstall[repo] = "unreadable file(s)"

    for repo, reason in sorted(repos_to_reinstall.items()):
        actions.append(
            (f"Reinstall repo ({reason}): {repo}", partial(reinstall_repo, repo))
        )

    if not actions:
        console.print("[green]No issues found.[/green]")
        return

    fixed_count = 0

    if granular:
        for message, action in actions:
            console.print(f"[yellow]{message}[/yellow]")
            if typer.confirm("Fix this?", default=True):
                fixed_count += action()
                replaced_message = (
                    message.replace("Remove", "Removed")
                    .replace("Update", "Updated")
                    .replace("Reinstall", "Reinstalled")
                )
                console.print(f"[green]{replaced_message}[/green]")
    else:
        console.print(f"[yellow]Found {len(actions)} issue(s):[/yellow]")
        for message, _ in actions:
            console.print(f"  {message}")

        if not typer.confirm("Proceed with fixes?", default=True):
            console.print("[blue]Aborted.[/blue]")
            return

        for message, action in actions:
            fixed_count += action()
            replaced_message = (
                message.replace("Remove", "Removed")
                .replace("Update", "Updated")
                .replace("Reinstall", "Reinstalled")
            )
            console.print(f"[green]{replaced_message}[/green]")

    logger.debug("Saving fixed installed data")
    save_installed_data(installed_data)
    console.print(f"[green]Fixed {fixed_count} issue(s).[/green]")
