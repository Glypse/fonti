from typing import TYPE_CHECKING, List, Tuple

from fontTools.ttLib import TTFont  # pyright: ignore[reportMissingTypeStubs]
from rich.console import Console

if TYPE_CHECKING:
    from pathlib import Path

console = Console()


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
