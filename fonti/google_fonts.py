import base64
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import httpx
import typer
from bs4 import BeautifulSoup
from rich.console import Console

from .config import CACHE_DIR, cache, default_github_token, default_google_fonts_direct
from .downloader import fetch_release_info, get_subdirectory_version
from .registry import get_repo_from_registry

console = Console()


def parse_repo(repo_arg: str) -> Tuple[str, str]:
    """Parse owner/repo string into owner and repo_name."""
    try:
        owner, repo_name = repo_arg.split("/")
        return owner, repo_name
    except ValueError as e:
        raise ValueError(f"Invalid repo format: {repo_arg}. Use owner/repo") from e


def download_subdirectory(font_name: str) -> Tuple[str, str, Path, bool]:
    """Download the subdirectory from Google Fonts."""
    headers: Dict[str, str] = {}
    if default_github_token:
        headers["Authorization"] = f"Bearer {default_github_token}"

    font_name_lower = font_name.lower()

    console.print(
        f"[yellow]Attempting to download subdirectory for {font_name}...[/yellow]"
    )

    dirs = ["ofl", "ufl", "apache"]
    for dir in dirs:
        try:
            api_url = f"https://api.github.com/repos/google/fonts/contents/{dir}/{font_name_lower}"
            response = httpx.get(api_url, headers=headers)
            response.raise_for_status()
            contents = response.json()
            font_items = [
                item
                for item in contents
                if item["type"] == "file"
                and item["name"].endswith((".ttf", ".otf", ".woff", ".woff2"))
            ]
            if not font_items:
                continue
            temp_dir = Path(tempfile.mkdtemp())
            for item in font_items:
                blob_url = item["url"]
                headers_blob = headers.copy()
                headers_blob["Accept"] = "application/vnd.github.raw"
                blob_response = httpx.get(blob_url, headers=headers_blob)
                blob_response.raise_for_status()
                content = blob_response.content
                if content.startswith(b"{"):
                    blob_data = blob_response.json()
                    content = base64.b64decode(blob_data["content"])
                file_path = temp_dir / item["name"]
                file_path.write_bytes(content)
            console.print(
                f"[green]Downloaded {len(font_items)} font files for {font_name} from {dir}.[/green]"
            )
            dir_font_name = f"{dir}/{font_name}"
            version = get_subdirectory_version(dir_font_name)
            cache_key = f"{dir_font_name}-{version.replace(':', '-')}.zip"
            try:
                zip_path = CACHE_DIR / cache_key
                zip_path.parent.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(zip_path, "w") as zip_ref:
                    for file_path in temp_dir.rglob("*"):
                        if file_path.is_file():
                            zip_ref.write(file_path, file_path.relative_to(temp_dir))
                if cache is not None:
                    cache[cache_key] = str(zip_path)
                    console.print("Subdirectory cached.")
            except Exception as e:
                console.print(
                    f"[yellow]Warning: Failed to cache subdirectory: {e}[/yellow]"
                )
            return "thegooglefontsrepo", dir_font_name, temp_dir, True
        except Exception:
            continue
    console.print(
        f"[red]Failed to fetch subdirectory for {font_name}: not found in any directory[/red]"
    )
    raise ValueError(f"Font '{font_name}' not found in Google Fonts.")


def fetch_google_fonts_repo(font_name: str) -> Tuple[str, str, Path | None, bool]:
    """Fetch the GitHub repo for a Google Font by parsing HTML files, or download subdirectory."""
    headers: Dict[str, str] = {}
    if default_github_token:
        headers["Authorization"] = f"Bearer {default_github_token}"

    # First, check registry
    repo_info = get_repo_from_registry(font_name)
    if repo_info:
        owner, repo = repo_info
        # Check if the repo has releases
        try:
            fetch_release_info(owner, repo, "latest")
            return owner, repo, None, False
        except Exception:
            # Check if the repo has font files in fonts/ directory (recursive)
            try:

                def has_font_files(
                    path: str, owner: str = owner, repo: str = repo
                ) -> bool:
                    api_url = (
                        f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
                    )
                    response = httpx.get(api_url, headers=headers)
                    response.raise_for_status()
                    contents = response.json()
                    for item in contents:
                        if item["type"] == "file" and item["name"].endswith(
                            (".ttf", ".otf", ".woff", ".woff2")
                        ):
                            return True
                        elif item["type"] == "dir":
                            if has_font_files(item["path"], owner, repo):
                                return True
                    return False

                if has_font_files("fonts"):
                    console.print(
                        f"[yellow]Repo {owner}/{repo} has no releases but has fonts/ "
                        "directory, using fonts/ download.[/yellow]"
                    )
                    return owner, repo, None, False
            except Exception:
                pass
            console.print(
                f"[yellow]Repo {owner}/{repo} from registry has no releases or fonts/ "
                "directory, falling back to subdirectory...[/yellow]"
            )
            return download_subdirectory(font_name)

    if default_google_fonts_direct:
        return download_subdirectory(font_name)

    headers: Dict[str, str] = {}
    if default_github_token:
        headers["Authorization"] = f"Bearer {default_github_token}"

    font_name_lower = font_name.lower()

    urls = [
        f"https://raw.githubusercontent.com/google/fonts/main/ofl/{font_name_lower}/article/ARTICLE.en_us.html",
        f"https://raw.githubusercontent.com/google/fonts/main/ofl/{font_name_lower}/DESCRIPTION.en_us.html",
        f"https://raw.githubusercontent.com/google/fonts/main/apache/{font_name_lower}/DESCRIPTION.en_us.html",
        f"https://raw.githubusercontent.com/google/fonts/main/ufl/{font_name_lower}/DESCRIPTION.en_us.html",
    ]

    for url in urls:
        try:
            response = httpx.get(url, headers=headers, follow_redirects=True)
            response.raise_for_status()
            html_content = response.text
            soup = BeautifulSoup(html_content, "html.parser")
            links = soup.find_all("a", href=True)
            github_links = [
                link["href"] for link in links if "github.com" in link["href"]
            ]
            if github_links:
                if len(github_links) > 1:
                    console.print(
                        f"[yellow]Multiple GitHub links found for {font_name}:[/yellow]"
                    )
                    for i, link in enumerate(github_links):
                        console.print(f"  {i+1}: {link}")
                    choice = typer.prompt("Choose which one to use (number)", type=int)
                    if 1 <= choice <= len(github_links):
                        selected_link = str(github_links[choice - 1])  # type: ignore
                    else:
                        console.print("[red]Invalid choice.[/red]")
                        raise typer.Exit(1)
                else:
                    selected_link = str(github_links[0])
                # Parse owner/repo from link
                if "github.com/" in selected_link:
                    parts: List[str] = selected_link.split("github.com/")[1].split("/")
                    if len(parts) >= 2:
                        owner: str
                        repo: str
                        owner, repo = parts[0], parts[1]
                        # Check if the repo has releases
                        try:
                            fetch_release_info(owner, repo, "latest")
                            return owner, repo, None, False
                        except Exception:
                            # Check if the repo has font files in fonts/ directory (recursive)
                            try:

                                def has_font_files(
                                    path: str, owner: str = owner, repo: str = repo
                                ) -> bool:
                                    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
                                    response = httpx.get(api_url, headers=headers)
                                    response.raise_for_status()
                                    contents = response.json()
                                    for item in contents:
                                        if item["type"] == "file" and item[
                                            "name"
                                        ].endswith((".ttf", ".otf", ".woff", ".woff2")):
                                            return True
                                        elif item["type"] == "dir":
                                            if has_font_files(
                                                item["path"], owner, repo
                                            ):
                                                return True
                                    return False

                                if has_font_files("fonts"):
                                    console.print(
                                        f"[yellow]Repo {owner}/{repo} has no releases but has fonts/ "
                                        "directory, using fonts/ download.[/yellow]"
                                    )
                                    return owner, repo, None, False
                            except Exception:
                                pass
                            console.print(
                                f"[yellow]Repo {owner}/{repo} has no releases or fonts/ directory, "
                                "falling back to subdirectory...[/yellow]"
                            )
                            return download_subdirectory(font_name)
        except httpx.HTTPStatusError:
            continue  # Try next URL
        except Exception as e:
            console.print(f"[yellow]Error fetching {url}: {e}[/yellow]")
            continue

    # If no HTML found, try to download the subdirectory
    return download_subdirectory(font_name)
