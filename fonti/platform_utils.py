import logging
import platform
import subprocess
from typing import TYPE_CHECKING, List

from rich.console import Console

if TYPE_CHECKING:
    from pathlib import Path

console = Console()
logger = logging.getLogger(__name__)


def register_fonts(font_paths: List[Path]) -> None:
    """Register installed fonts with the system."""
    system = platform.system()
    logger.info(f"Registering {len(font_paths)} fonts on {system}")

    if system == "Windows":
        _register_fonts_windows(font_paths)
    elif system == "Linux":
        _register_fonts_linux()
    else:  # macOS and others
        _register_fonts_macos()


def unregister_fonts(font_paths: List[Path]) -> None:
    """Unregister fonts from the system."""
    system = platform.system()
    logger.info(f"Unregistering {len(font_paths)} fonts on {system}")

    if system == "Windows":
        _unregister_fonts_windows(font_paths)
    elif system == "Linux":
        _register_fonts_linux()  # Same as register on Linux
    else:  # macOS and others
        _register_fonts_macos()  # Nothing needed


def _register_fonts_windows(font_paths: List[Path]) -> None:
    """Register fonts on Windows using Win32 APIs and registry."""
    try:
        import ctypes
        import winreg

        import win32api  # type: ignore
        import win32con  # type: ignore
    except ImportError as e:
        console.print(
            f"[yellow]Warning: Windows font registration requires additional packages: {e}. "
            "Fonts installed but may not be available until restart.[/yellow]"
        )
        return

    for font_path in font_paths:
        try:
            # AddFontResourceW to make available in current session
            gdi32 = ctypes.WinDLL("gdi32")  # type: ignore
            gdi32.AddFontResourceW.argtypes = (ctypes.c_wchar_p,)  # type: ignore
            result = gdi32.AddFontResourceW(ctypes.c_wchar_p(str(font_path)))  # type: ignore
            if result == 0:
                logger.warning(f"Failed to add font resource: {font_path}")

            # Update registry for persistence
            # Note: This requires admin rights, may fail
            try:
                reg_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Fonts"
                reg_value_name = font_path.stem  # Use filename as key
                reg_value = str(font_path)
                with winreg.OpenKey(  # type: ignore
                    winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE  # type: ignore
                ) as key:  # type: ignore
                    winreg.SetValueEx(key, reg_value_name, 0, winreg.REG_SZ, reg_value)  # type: ignore
                logger.debug(f"Updated registry for {font_path}")
            except Exception as e:
                logger.warning(
                    f"Failed to update registry for {font_path}: {e}. Font may not persist after restart."
                )

        except Exception as e:
            logger.error(f"Error registering font {font_path}: {e}")

    # Broadcast font change message
    try:
        win32api.PostMessage(win32con.HWND_BROADCAST, win32con.WM_FONTCHANGE, 0, 0)  # type: ignore
        logger.info("Broadcasted font change message")
    except Exception as e:
        logger.warning(f"Failed to broadcast font change: {e}")


def _unregister_fonts_windows(font_paths: List[Path]) -> None:
    """Unregister fonts on Windows using Win32 APIs and registry."""
    try:
        import ctypes
        import winreg

        import win32api  # type: ignore
        import win32con  # type: ignore
    except ImportError as e:
        console.print(
            f"[yellow]Warning: Windows font unregistration requires additional packages: {e}. "
            "Fonts removed but system may not update until restart.[/yellow]"
        )
        return

    for font_path in font_paths:
        try:
            # RemoveFontResourceW to remove from current session
            gdi32 = ctypes.WinDLL("gdi32")  # type: ignore
            gdi32.RemoveFontResourceW.argtypes = (ctypes.c_wchar_p,)  # type: ignore
            result = gdi32.RemoveFontResourceW(ctypes.c_wchar_p(str(font_path)))  # type: ignore
            if result == 0:
                logger.warning(f"Failed to remove font resource: {font_path}")

            # Remove from registry for persistence
            try:
                reg_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Fonts"
                reg_value_name = font_path.stem  # Use filename as key
                with winreg.OpenKey(  # type: ignore
                    winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_SET_VALUE  # type: ignore
                ) as key:  # type: ignore
                    try:
                        winreg.DeleteValue(key, reg_value_name)  # type: ignore
                        logger.debug(f"Removed registry entry for {font_path}")
                    except FileNotFoundError:
                        logger.debug(f"Registry entry not found for {font_path}")
            except Exception as e:
                logger.warning(f"Failed to remove registry entry for {font_path}: {e}")

        except Exception as e:
            logger.error(f"Error unregistering font {font_path}: {e}")

    # Broadcast font change message
    try:
        win32api.PostMessage(win32con.HWND_BROADCAST, win32con.WM_FONTCHANGE, 0, 0)  # type: ignore
        logger.info("Broadcasted font change message")
    except Exception as e:
        logger.warning(f"Failed to broadcast font change: {e}")


def _register_fonts_linux() -> None:
    """Register fonts on Linux by running fc-cache."""
    try:
        subprocess.run(["fc-cache", "-f"], capture_output=True, text=True, check=True)
        logger.info("Ran fc-cache successfully")
    except subprocess.CalledProcessError as e:
        console.print(f"[yellow]Warning: Failed to update font cache: {e}[/yellow]")
        logger.error(f"fc-cache failed: {e}")
    except FileNotFoundError:
        console.print(
            "[yellow]Warning: fc-cache not found. Install fontconfig to update font cache.[/yellow]"
        )


def _register_fonts_macos() -> None:
    """Register fonts on macOS. Usually automatic, but can run atsutil if needed."""
    # On macOS, fonts are usually registered automatically when placed in ~/Library/Fonts
    # If needed, could run: atsutil databases -removeUser
    # But for now, do nothing
    logger.info("macOS font registration: automatic")
