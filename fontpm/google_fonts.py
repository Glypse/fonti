import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

import httpx
import typer
from bs4 import BeautifulSoup
from rich.console import Console

from .config import CACHE, CACHE_DIR, default_github_token
from .downloader import fetch_release_info

console = Console()


def parse_repo(repo_arg: str) -> Tuple[str, str]:
    """Parse owner/repo string into owner and repo_name."""
    try:
        owner, repo_name = repo_arg.split("/")
        return owner, repo_name
    except ValueError as e:
        raise ValueError(f"Invalid repo format: {repo_arg}. Use owner/repo") from e


def fetch_google_fonts_repo(font_name: str) -> Tuple[str, str, Path | None, bool]:
    """Fetch the GitHub repo for a Google Font by parsing HTML files, or download subdirectory."""
    headers: Dict[str, str] = {}
    if default_github_token:
        headers["Authorization"] = f"Bearer {default_github_token}"

    font_name_lower = font_name.lower()

    def download_subdirectory() -> Tuple[str, str, Path, bool]:
        """Download the subdirectory from Google Fonts."""
        console.print(
            f"[yellow]Attempting to download subdirectory for {font_name}...[/yellow]"
        )

        # Check cache first
        from .downloader import get_subdirectory_version

        version = get_subdirectory_version(font_name)
        cache_key = f"{font_name}-{version.replace(':', '-')}.zip"
        if cache_key in CACHE:
            console.print(f"Using cached subdirectory: {cache_key}")
            cached_zip = str(CACHE[cache_key])  # type: ignore
            temp_dir = Path(tempfile.mkdtemp())
            with zipfile.ZipFile(cached_zip, "r") as zip_ref:
                zip_ref.extractall(temp_dir)
            return "thegooglefontsrepo", font_name, temp_dir, True

        # Download and cache
        try:
            # Use GitHub API to get contents of ofl/font_name
            api_url = f"https://api.github.com/repos/google/fonts/contents/ofl/{font_name_lower}"
            response = httpx.get(api_url, headers=headers)
            if response.status_code == 404:
                # Try ufl
                api_url = f"https://api.github.com/repos/google/fonts/contents/ufl/{font_name_lower}"
                response = httpx.get(api_url, headers=headers)
                response.raise_for_status()
            else:
                response.raise_for_status()
            contents = response.json()
            # Filter for font files
            font_files = [
                item
                for item in contents
                if item["name"].endswith((".ttf", ".otf", ".woff", ".woff2"))
                and item["type"] == "file"
            ]
            if not font_files:
                raise ValueError(f"No font files found in subdirectory for {font_name}")
            # Download them to temp dir
            temp_dir = Path(tempfile.mkdtemp())
            for item in font_files:
                file_url = item["download_url"]
                file_response = httpx.get(file_url, headers=headers)
                file_response.raise_for_status()
                file_path = temp_dir / item["name"]
                file_path.write_bytes(file_response.content)
            console.print(
                f"[green]Downloaded {len(font_files)} font files for {font_name}.[/green]"
            )
            # Create zip and cache
            zip_path = CACHE_DIR / cache_key
            with zipfile.ZipFile(zip_path, "w") as zip_ref:
                for file_path in temp_dir.rglob("*"):
                    if file_path.is_file():
                        zip_ref.write(file_path, file_path.relative_to(temp_dir))
            CACHE[cache_key] = str(zip_path)
            console.print("Subdirectory cached.")
            return "thegooglefontsrepo", font_name, temp_dir, True
        except Exception as e:
            console.print(
                f"[red]Failed to fetch subdirectory for {font_name}: {e}[/red]"
            )
            raise ValueError(f"Font '{font_name}' not found in Google Fonts.") from e

    urls = [
        f"https://raw.githubusercontent.com/google/fonts/main/ofl/{font_name_lower}/article/ARTICLE.en_us.html",
        f"https://raw.githubusercontent.com/google/fonts/main/ofl/{font_name_lower}/DESCRIPTION.en_us.html",
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
                            return download_subdirectory()
        except httpx.HTTPStatusError:
            continue  # Try next URL
        except Exception as e:
            console.print(f"[yellow]Error fetching {url}: {e}[/yellow]")
            continue

    # If no HTML found, try to download the subdirectory
    return download_subdirectory()
