import json
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

from git import Repo
from rich.console import Console

from .config import cache, default_registry_check_interval

console = Console()

REGISTRY_REPO_URL = "https://github.com/Glypse/fonti-registry.git"
REGISTRY_DIR = Path.home() / ".fonti" / "registry"
REGISTRY_FILE = REGISTRY_DIR / "fonti_registry.json"
METADATA_FILE = REGISTRY_DIR / ".registry_metadata"
REGISTRY_CHECK_INTERVAL = default_registry_check_interval


def get_metadata() -> Dict[str, float | str]:
    """Get metadata from file."""
    if not METADATA_FILE.exists():
        return {"last_check": 0.0, "last_commit": ""}
    try:
        with open(METADATA_FILE) as f:
            data = json.load(f)
        return {
            "last_check": float(data.get("last_check", 0)),
            "last_commit": str(data.get("last_commit", "")),
        }
    except Exception:
        return {"last_check": 0.0, "last_commit": ""}


def save_metadata(data: Dict[str, float | str]) -> None:
    """Save metadata to file."""
    METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(METADATA_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def get_registry_data() -> Dict[str, Dict[str, str]]:
    """Load the registry data from the local file."""
    if not REGISTRY_FILE.exists():
        return {}
    try:
        with open(REGISTRY_FILE) as f:
            return json.load(f)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load registry: {e}[/yellow]")
        return {}


def clone_registry() -> None:
    """Clone the registry repository with sparse checkout for only the JSON file."""
    console.print("[yellow]Cloning registry repository...[/yellow]")
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    repo = Repo.clone_from(REGISTRY_REPO_URL, REGISTRY_DIR, depth=1, no_checkout=True)
    repo.git.sparse_checkout("init")
    repo.git.sparse_checkout("set", "fonti_registry.json")
    repo.git.checkout()
    console.print("[green]Registry cloned.[/green]")


def update_registry(force: bool = False) -> None:
    """Update the registry if it's been more than 24 hours or if commit changed."""
    if not REGISTRY_DIR.exists():
        clone_registry()
        return

    repo = Repo(REGISTRY_DIR)
    current_commit = repo.head.commit.hexsha

    # Check if we need to update
    now = time.time()
    last_check = 0.0
    last_commit = ""
    if cache:
        val = cache.get("registry_last_check")  # type: ignore
        last_check = float(val) if val is not None else 0.0  # type: ignore
        val2 = cache.get("registry_last_commit")  # type: ignore
        last_commit = str(val2) if val2 is not None else ""  # type: ignore
    else:
        metadata = get_metadata()
        last_check = float(metadata["last_check"])
        last_commit = str(metadata["last_commit"])

    if (
        not force
        and now - last_check < REGISTRY_CHECK_INTERVAL
        and current_commit == last_commit
    ):
        return  # No need to update

    console.print("[yellow]Updating registry...[/yellow]")
    # Fetch latest
    repo.remotes.origin.fetch(depth=1)
    repo.git.reset("--hard", "origin/main")

    new_commit = repo.head.commit.hexsha
    if cache:
        cache["registry_last_check"] = now
        cache["registry_last_commit"] = new_commit
    else:
        save_metadata({"last_check": now, "last_commit": new_commit})

    if new_commit != current_commit:
        console.print("[green]Registry updated.[/green]")
    else:
        console.print("[green]Registry is up to date.[/green]")


def search_registry(font_name: str) -> Optional[Dict[str, str]]:
    """Search for a font in the registry."""
    registry = get_registry_data()
    normalized = font_name.lower().replace(" ", "-")

    # Check direct key match
    if normalized in registry:
        return registry[normalized]

    # Check name and display_name
    for entry in registry.values():
        if entry.get("name", "").lower().replace(" ", "-") == normalized:
            return entry
        if entry.get("display_name", "").lower().replace(" ", "-") == normalized:
            return entry

    return None


def get_repo_from_registry(font_name: str) -> Optional[Tuple[str, str]]:
    """Get owner/repo from registry if available."""
    entry = search_registry(font_name)
    if entry and entry.get("link"):
        link = entry["link"]
        if "github.com/" in link:
            parts = link.split("github.com/")[1].split("/")
            if len(parts) >= 2:
                return parts[0], parts[1].split(".")[0]  # remove .git if present
    return None
