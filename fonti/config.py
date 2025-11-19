import base64
import json
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

import typer
from cryptography.fernet import Fernet
from diskcache import Cache  # pyright: ignore[reportMissingTypeStubs]
from platformdirs import user_cache_dir
from rich.console import Console

from .constants import (
    CONFIG_FILE,
    DEFAULT_CACHE_SIZE,
    DEFAULT_GOOGLE_FONTS_DIRECT,
    DEFAULT_PATH,
    DEFAULT_PRIORITIES,
    DEFAULT_REGISTRY_CHECK_INTERVAL,
    INSTALLED_FILE,
    KEY_FILE,
    VALID_FORMATS,
)

if TYPE_CHECKING:
    from .types import FontEntry

console = Console()


def get_encryption_key() -> bytes:
    """Get or generate the encryption key for secure config storage."""
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    else:
        key = Fernet.generate_key()
        KEY_FILE.parent.mkdir(exist_ok=True)
        KEY_FILE.write_bytes(key)
        return key


# Load default format from config file
def load_config() -> Tuple[List[str], Path, int, str, bool, int]:
    """Load configuration from config file."""
    priorities = DEFAULT_PRIORITIES.copy()
    path = DEFAULT_PATH
    cache_size = DEFAULT_CACHE_SIZE
    github_token = ""
    google_fonts_direct = DEFAULT_GOOGLE_FONTS_DIRECT
    registry_check_interval = DEFAULT_REGISTRY_CHECK_INTERVAL

    fernet = Fernet(get_encryption_key())

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
                        if all(p in DEFAULT_PRIORITIES for p in parsed_priorities):
                            priorities = parsed_priorities
                    elif line.startswith("path="):
                        value = line.split("=", 1)[1].strip()
                        if value:
                            path = Path(value)
                    elif line.startswith("cache-size="):
                        value = line.split("=", 1)[1].strip()
                        try:
                            cache_size = int(value)
                        except ValueError:
                            console.print(
                                "[yellow]Warning: Invalid cache-size, using default.[/yellow]"
                            )
                    elif line.startswith("github_token="):
                        encrypted_value = line.split("=", 1)[1].strip()
                        try:
                            github_token = fernet.decrypt(
                                base64.b64decode(encrypted_value)
                            ).decode()
                        except Exception:
                            console.print(
                                "[yellow]Warning: Could not decrypt GitHub token.[/yellow]"
                            )
                    elif line.startswith("registry_check_interval="):
                        value = line.split("=", 1)[1].strip()
                        try:
                            registry_check_interval = int(value)
                        except ValueError:
                            console.print(
                                "[yellow]Warning: Invalid registry_check_interval, using default.[/yellow]"
                            )
        except Exception:
            console.print("[yellow]Warning: Could not load config file.[/yellow]")

    return (
        priorities,
        path,
        cache_size,
        github_token,
        google_fonts_direct,
        registry_check_interval,
    )


(
    default_priorities,
    default_path,
    default_cache_size,
    default_github_token,
    default_google_fonts_direct,
    default_registry_check_interval,
) = load_config()

# Cache setup
CACHE_DIR = Path(user_cache_dir("fonti"))
cache: Optional[Cache] = None
if default_cache_size == 0:
    # Delete existing cache and disable caching
    if CACHE_DIR.exists():
        import shutil

        shutil.rmtree(CACHE_DIR)
        console.print("[green]Cache purged.[/green]")
    cache = None
else:
    cache = Cache(str(CACHE_DIR), size_limit=default_cache_size)


def set_config(key: str, value: str) -> None:
    """Set a configuration key-value pair."""
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
    elif key == "cache-size":
        try:
            int(value)
        except ValueError:
            console.print("[red]Invalid cache size: must be integer[/red]")
            raise typer.Exit(1) from None
    elif key == "github_token":
        fernet = Fernet(get_encryption_key())
        encrypted = base64.b64encode(fernet.encrypt(value.encode())).decode()
        value = encrypted
    elif key == "registry_check_interval":
        try:
            int(value)
        except ValueError:
            console.print("[red]Invalid registry_check_interval: must be integer[/red]")
            raise typer.Exit(1) from None

    current_config[key] = value
    console.print(
        f"[green]Set {key} to: {'***' if key == 'github_token' else value}[/green]"
    )

    try:
        with open(CONFIG_FILE, "w") as f:
            for k, v in current_config.items():
                f.write(f"{k}={v}\n")
    except Exception as e:
        console.print(f"[red]Error writing config: {e}[/red]")
        raise typer.Exit(1) from e


def load_installed_data() -> Dict[str, Dict[str, FontEntry]]:
    """Load installed fonts data from file."""
    if not INSTALLED_FILE.exists():
        return {}
    try:
        with open(INSTALLED_FILE) as f:
            data = json.load(f)
        # Normalize keys to lower case for case-insensitive matching
        normalized = {k.lower(): v for k, v in data.items()}
        return normalized
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
