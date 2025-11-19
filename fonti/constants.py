from pathlib import Path

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
DEFAULT_CACHE_SIZE = 20 * 1024 * 1024  # 20MB
DEFAULT_GOOGLE_FONTS_DIRECT = False
DEFAULT_REGISTRY_CHECK_INTERVAL = 24 * 60 * 60  # 24 hours in seconds
CONFIG_FILE = Path.home() / ".fonti" / "config"
KEY_FILE = CONFIG_FILE.parent / "key"
INSTALLED_FILE = Path.home() / ".fonti" / "installed.json"

FORMAT_HELP = f"Comma-separated list of font formats to prefer[dim] (options: {', '.join(VALID_FORMATS)})[/dim]"
