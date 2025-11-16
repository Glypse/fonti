from pathlib import Path
from typing import List, Tuple
from unittest.mock import MagicMock, patch

import pytest

from fontpm.fonts import (
    categorize_fonts,
    get_font_italic,
    get_font_weight,
    is_variable_font,
    select_fonts,
)


class TestIsVariableFont:
    @patch("fontpm.fonts.TTFont")
    def test_is_variable_font_true(self, mock_ttfont: MagicMock) -> None:
        mock_font = MagicMock()
        mock_font.__contains__ = MagicMock(return_value=True)  # 'fvar' in font
        mock_ttfont.return_value = mock_font

        result = is_variable_font("dummy.ttf")
        assert result is True
        mock_ttfont.assert_called_once_with("dummy.ttf")

    @patch("fontpm.fonts.TTFont")
    def test_is_variable_font_false(self, mock_ttfont: MagicMock) -> None:
        mock_font = MagicMock()
        mock_font.__contains__ = MagicMock(return_value=False)  # 'fvar' not in font
        mock_ttfont.return_value = mock_font

        result = is_variable_font("dummy.ttf")
        assert result is False

    @patch("fontpm.fonts.TTFont")
    def test_is_variable_font_exception(self, mock_ttfont: MagicMock) -> None:
        mock_ttfont.side_effect = Exception("Font error")

        with pytest.raises(Exception, match="Font error"):
            is_variable_font("dummy.ttf")


class TestGetFontWeight:
    @patch("fontpm.fonts.TTFont")
    def test_get_font_weight_success(self, mock_ttfont: MagicMock) -> None:
        mock_font = MagicMock()
        mock_os2 = MagicMock()
        mock_os2.usWeightClass = 700
        mock_font.__getitem__ = MagicMock(return_value=mock_os2)
        mock_ttfont.return_value = mock_font

        result = get_font_weight("dummy.ttf")
        assert result == 700

    @patch("fontpm.fonts.TTFont")
    def test_get_font_weight_exception(self, mock_ttfont: MagicMock) -> None:
        mock_ttfont.side_effect = Exception("Font error")

        result = get_font_weight("dummy.ttf")
        assert result == 400  # default


class TestGetFontItalic:
    @patch("fontpm.fonts.TTFont")
    def test_get_font_italic_true(self, mock_ttfont: MagicMock) -> None:
        mock_font = MagicMock()
        mock_os2 = MagicMock()
        mock_os2.fsSelection = 0x01  # italic bit set
        mock_font.__getitem__ = MagicMock(return_value=mock_os2)
        mock_ttfont.return_value = mock_font

        result = get_font_italic("dummy.ttf")
        assert result is True

    @patch("fontpm.fonts.TTFont")
    def test_get_font_italic_false(self, mock_ttfont: MagicMock) -> None:
        mock_font = MagicMock()
        mock_os2 = MagicMock()
        mock_os2.fsSelection = 0x00  # italic bit not set
        mock_font.__getitem__ = MagicMock(return_value=mock_os2)
        mock_ttfont.return_value = mock_font

        result = get_font_italic("dummy.ttf")
        assert result is False

    @patch("fontpm.fonts.TTFont")
    def test_get_font_italic_exception(self, mock_ttfont: MagicMock) -> None:
        mock_ttfont.side_effect = Exception("Font error")

        result = get_font_italic("dummy.ttf")
        assert result is False


class TestCategorizeFonts:
    @patch("fontpm.fonts.is_variable_font")
    def test_categorize_fonts_mixed(self, mock_is_var: MagicMock) -> None:
        # Mock is_variable_font to return True for some, False for others
        def mock_is_var_func(p: Path) -> bool:
            return "var" in str(p)

        mock_is_var.side_effect = mock_is_var_func

        font_files = [
            Path("var1.ttf"),
            Path("static1.ttf"),
            Path("var2.otf"),
            Path("static2.woff"),
            Path("static3.woff2"),
            Path("static4.woff"),
            Path("static5.woff2"),
        ]

        result = categorize_fonts(font_files)

        assert len(result) == 7
        (
            variable_ttfs,
            static_ttfs,
            otfs,
            variable_woffs,
            static_woffs,
            variable_woff2s,
            static_woff2s,
        ) = result

        assert variable_ttfs == [Path("var1.ttf")]
        assert static_ttfs == [Path("static1.ttf")]
        assert otfs == [Path("var2.otf")]  # otf is always static
        assert variable_woffs == []
        # Let's check the side_effect: [True, False, True, False, False, False, False]
        # var1.ttf: True -> variable_ttfs
        # static1.ttf: False -> static_ttfs
        # var2.otf: True but otf is not checked for variable, it's in otfs
        # static2.woff: False -> static_woffs
        # static3.woff2: False -> static_woff2s
        # static4.woff: False -> static_woffs
        # static5.woff2: False -> static_woff2s

        # But in code, for otf, it's not checked, just added to otfs
        # For woff, checked, if variable -> variable_woffs, else static_woffs
        # Same for woff2

        # So variable_woffs should be empty since static2.woff is False
        # static2.woff: False -> static_woffs
        # static4.woff: False -> static_woffs

        # variable_woff2s empty
        # static_woff2s: static3.woff2, static5.woff2

        # otfs: var2.otf (since .otf)

        assert variable_ttfs == [Path("var1.ttf")]
        assert static_ttfs == [Path("static1.ttf")]
        assert otfs == [Path("var2.otf")]
        assert variable_woffs == []
        assert static_woffs == [Path("static2.woff"), Path("static4.woff")]
        assert variable_woff2s == []
        assert static_woff2s == [Path("static3.woff2"), Path("static5.woff2")]

    @patch("fontpm.fonts.is_variable_font")
    def test_categorize_fonts_exception_handling(self, mock_is_var: MagicMock) -> None:
        mock_is_var.side_effect = Exception("Error")

        font_files = [Path("font.ttf")]

        result = categorize_fonts(font_files)

        # Should treat as static
        (
            variable_ttfs,
            static_ttfs,
            otfs,
            variable_woffs,
            static_woffs,
            variable_woff2s,
            static_woff2s,
        ) = result
        assert static_ttfs == [Path("font.ttf")]
        assert all(
            len(lst) == 0
            for lst in [
                variable_ttfs,
                otfs,
                variable_woffs,
                static_woffs,
                variable_woff2s,
                static_woff2s,
            ]
        )


class TestSelectFonts:
    def test_select_fonts_variable_ttf_priority(self) -> None:
        categorized: Tuple[
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
        ] = (
            [Path("var.ttf")],  # variable_ttfs
            [Path("static.ttf")],  # static_ttfs
            [],  # otfs
            [],  # variable_woffs
            [],  # static_woffs
            [],  # variable_woff2s
            [],  # static_woff2s
        )

        selected, pri = select_fonts(
            categorized, ["variable-ttf", "static-ttf"], [], ["roman", "italic"]
        )
        assert selected == [Path("var.ttf")]
        assert pri == "variable-ttf"

    def test_select_fonts_fallback_to_static(self) -> None:
        categorized: Tuple[
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
        ] = (
            [],  # variable_ttfs
            [Path("static.ttf")],  # static_ttfs
            [],  # otfs
            [],  # variable_woffs
            [],  # static_woffs
            [],  # variable_woff2s
            [],  # static_woff2s
        )

        selected, pri = select_fonts(
            categorized, ["variable-ttf", "static-ttf"], [], ["roman", "italic"]
        )
        assert selected == [Path("static.ttf")]
        assert pri == "static-ttf"

    def test_select_fonts_with_weights(self) -> None:
        categorized: Tuple[
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
        ] = (
            [],  # variable_ttfs
            [Path("font1.ttf"), Path("font2.ttf")],  # static_ttfs
            [],  # otfs
            [],  # variable_woffs
            [],  # static_woffs
            [],  # variable_woff2s
            [],  # static_woff2s
        )

        with patch("fontpm.fonts.get_font_weight") as mock_weight:
            mock_weight.side_effect = [400, 700]  # font1: 400, font2: 700

            selected, pri = select_fonts(
                categorized, ["static-ttf"], [700], ["roman", "italic"]
            )
            assert selected == [Path("font2.ttf")]
            assert pri == "static-ttf"

    def test_select_fonts_with_styles(self) -> None:
        categorized: Tuple[
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
        ] = (
            [],  # variable_ttfs
            [Path("font1.ttf"), Path("font2.ttf")],  # static_ttfs
            [],  # otfs
            [],  # variable_woffs
            [],  # static_woffs
            [],  # variable_woff2s
            [],  # static_woff2s
        )

        with patch("fontpm.fonts.get_font_italic") as mock_italic:

            def mock_italic_func(p: Path) -> bool:
                return "font2" in str(p)

            mock_italic.side_effect = mock_italic_func

            selected, pri = select_fonts(categorized, ["static-ttf"], [], ["italic"])
            assert selected == [Path("font2.ttf")]
            assert pri == "static-ttf"

    def test_select_fonts_no_match(self) -> None:
        categorized: Tuple[
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
        ] = (
            [],  # variable_ttfs
            [],  # static_ttfs
            [],  # otfs
            [],  # variable_woffs
            [],  # static_woffs
            [],  # variable_woff2s
            [],  # static_woff2s
        )

        selected, pri = select_fonts(
            categorized, ["variable-ttf"], [], ["roman", "italic"]
        )
        assert selected == []
        assert pri == ""

    @patch("fontpm.fonts.console.print")
    def test_select_fonts_variable_warning(self, mock_print: MagicMock) -> None:
        categorized: Tuple[
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
            List[Path],
        ] = (
            [Path("var.ttf")],  # variable_ttfs
            [],  # static_ttfs
            [],  # otfs
            [],  # variable_woffs
            [],  # static_woffs
            [],  # variable_woff2s
            [],  # static_woff2s
        )

        selected, pri = select_fonts(
            categorized, ["variable-ttf"], [700], ["roman", "italic"]
        )
        assert selected == [Path("var.ttf")]
        assert pri == "variable-ttf"
        mock_print.assert_called_once_with(
            "[yellow]Warning: Weights and styles are ignored for variable fonts.[/yellow]"
        )
