import hashlib
from typing import TYPE_CHECKING, Dict, List

from rich.console import Console

from .config import default_path, load_installed_data, save_installed_data

if TYPE_CHECKING:
    from .types import FontEntry

console = Console()


def uninstall_fonts(repo: List[str], force: bool) -> None:
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
        if "/" in repo_arg:
            try:
                owner, name = repo_arg.split("/")
            except ValueError:
                console.print(f"[red]Invalid repo format: {repo_arg}[/red]")
                continue
            repo_key = name.lower()
            if repo_key not in installed_data:
                console.print(f"[yellow]No fonts installed from {repo_arg}.[/yellow]")
                continue
            fonts = installed_data[repo_key]
            if not fonts or list(fonts.values())[0]["owner"].lower() != owner.lower():
                console.print(f"[yellow]No fonts installed from {repo_arg}.[/yellow]")
                continue
        else:
            repo_key = repo_arg.lower()
            if repo_key not in installed_data:
                console.print(f"[yellow]No fonts installed from {repo_arg}.[/yellow]")
                continue
            fonts = installed_data[repo_key]

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
            installed_data[repo_key] = remaining
        else:
            del installed_data[repo_key]

    save_installed_data(installed_data)

    if deleted_count > 0:
        console.print(
            f"[green]Uninstalled {deleted_count} font{'' if deleted_count == 1 else 's'}.[/green]"
        )
