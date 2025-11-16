# V1.0

-   [x] User preferences: prefer .otf, .ttf static or .ttf variable
-   Auto-detect variable fonts through `fontTools`
-   [x] Install GitHub fonts through the `install user/repo version` syntax
-   [x] Remove fonts installed **via fontpm only** through the `uninstall user/repo` syntax
-   [x] Updates fonts installed **via fontpm only** through the `update` syntax
-   [x] Support for non-global installations (example use case: woff2 install insisde of a web app repo)
-   [x] Enable importing/exporting `fontpm-fonts.json`
-   [x] Specify selected weight(s)
-   [x] Caching
    -   [ ] --info flag for the font before install
    -   [x] When local install/import, check if the font files aren't already cached or installed on the system; use those by preference
-   [x] GitHub auth
-   [x] `fix` command to repair broken `installed.json` files (duplicates, etc)
-   [x] Allow to see changelog
-   [x] Auto-detect common fonts such as those from Google fonts, allowing the `install font version` syntax, for QoL
-   [x] Install from repos without releases with the `fonts` folder
-   [ ] If can't find font files in releases, in `fonts` folder, look for a font file in the repo without downloading the repo

## V?.?

-   [ ] Support for more than GitHub; ideally any Git remote with tagged commits as "releases"
    -   [ ] Support for GitLab
-   [ ] Auto-detect from more common font sources such as open-source foundries (collectttivo, bye bye binary, etc)
-   [ ] Come up with a system for paid fonts, where the repo shouldn't be publicly accessible, such as an access key/password of sorts

# V2.0

-   [ ] GUI, installation via a setup wizard/executable, for non terminal users

## Ideally (might not be technically possible)

-   [ ] List of changed glyphs depending on version
    -   [ ] Changed glyphs preview
