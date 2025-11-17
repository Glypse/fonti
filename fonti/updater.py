from typing import TYPE_CHECKING, List, Tuple

from packaging.version import Version
from rich.console import Console

from .config import (
    default_path,
    default_priorities,
    load_installed_data,
    save_installed_data,
)
from .downloader import fetch_release_info, get_fonts_dir_version
from .installer import install_single_repo

if TYPE_CHECKING:
    from .types import FontEntry

console = Console()


def update_fonts(repo: List[str], changelog: bool) -> None:
    """
    Update installed fonts to the latest versions.
    """
    installed_data = load_installed_data()
    if not installed_data:
        console.print("[yellow]No installed fonts data found.[/yellow]")
        return

    updated_count = 0
    repos_to_update: List[Tuple[str, str, str, str, str, List[FontEntry], str]] = []

    repos_to_check: List[str] = []
    if not repo:
        repos_to_check = list(installed_data.keys())
    else:
        for r in repo:
            if "/" in r:
                try:
                    owner_input, name_input = r.split("/")
                    found = False
                    for key in installed_data:
                        fonts = installed_data[key]
                        if fonts:
                            entry = list(fonts.values())[0]
                            if (
                                entry["owner"] == owner_input
                                and entry["repo_name"] == name_input
                            ):
                                repos_to_check.append(key)
                                found = True
                                break
                    if not found:
                        console.print(f"[yellow]No fonts installed from {r}.[/yellow]")
                except ValueError:
                    console.print(f"[red]Invalid repo format: {r}[/red]")
            else:
                name_input = r.lower()
                if name_input in installed_data:
                    repos_to_check.append(name_input)
                else:
                    console.print(f"[yellow]No fonts installed from {r}.[/yellow]")

    for repo_name in repos_to_check:
        if repo_name not in installed_data:
            continue

        fonts = installed_data[repo_name]
        if not fonts:
            continue

        # Assume all have same version
        installed_version = list(fonts.values())[0]["version"]
        owner = list(fonts.values())[0]["owner"]
        repo_name_actual = list(fonts.values())[0]["repo_name"]

        try:
            latest_version, _, body, final_owner, final_repo_name = fetch_release_info(
                owner, repo_name_actual, "latest"
            )
        except Exception as e:
            if owner == "thegooglefontsrepo":
                console.print(
                    f"[yellow]Could not fetch latest for {owner}/{repo_name}: {e}[/yellow]"
                )
                continue
            else:
                # Try fonts dir
                try:
                    latest_version = get_fonts_dir_version(owner, repo_name_actual)
                    final_owner = owner
                    final_repo_name = repo_name_actual
                    body = ""
                except Exception:
                    console.print(
                        f"[yellow]Could not fetch latest for {owner}/{repo_name}: {e}[/yellow]"
                    )
                    continue

        # Strip 'v' if present
        def clean_version(v: str) -> str:
            return v.lstrip("v")

        try:
            v_latest = Version(clean_version(latest_version))
            v_installed = Version(clean_version(installed_version))
            if v_latest > v_installed:
                repos_to_update.append(
                    (
                        repo_name,
                        installed_version,
                        latest_version,
                        final_owner,
                        final_repo_name,
                        list(fonts.values()),
                        body,
                    )
                )
        except Exception:
            # Fallback to string comparison for dates
            if clean_version(latest_version) > clean_version(installed_version):
                repos_to_update.append(
                    (
                        repo_name,
                        installed_version,
                        latest_version,
                        final_owner,
                        final_repo_name,
                        list(fonts.values()),
                        body,
                    )
                )

    for (
        repo_name,
        installed_version,
        latest_version,
        owner,
        _repo_name,
        fonts,
        body,
    ) in repos_to_update:
        console.print(
            f"[bold]Updating {owner}/{_repo_name} from {installed_version} to {latest_version}...[/bold]"
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
        del installed_data[repo_name]
        # Save
        save_installed_data(installed_data)
        # Install new
        install_single_repo(
            owner,
            _repo_name,
            repo_name,
            "latest",
            default_priorities,
            default_path,
            False,
            True,
            [],
            ["roman", "italic"],
        )
        if changelog and body:
            console.print(
                f"[bold]Changelog for {owner}/{repo_name} {latest_version}:[/bold]"
            )
            console.print(body)
        updated_count += 1

    for repo_name in repos_to_check:
        if repo_name in installed_data and repo_name not in [
            r[0] for r in repos_to_update
        ]:
            fonts = installed_data[repo_name]
            if fonts:
                installed_version = list(fonts.values())[0]["version"]
                owner = list(fonts.values())[0]["owner"]
                repo_name_actual = list(fonts.values())[0]["repo_name"]
                console.print(
                    f"[dim]{owner}/{repo_name_actual} is up to date ({installed_version}).[/dim]"
                )
