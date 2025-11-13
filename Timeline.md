# V1.0

0. User preferences: prefer .otf, .ttf static or .ttf variable
    - Auto-detect variable fonts through `fontTools`
1. Install GitHub fonts through the `install user/repo version` syntax
2. Remove fonts installed **via fontpm only** through the `to be determined` syntax\*
3. Updates fonts installed **via fontpm only** through the `to be determined` syntax\*
    - Changelog preview

2 and 3 mean that we have to keep a list of all installed fonts; figure out the best architecture for that. Ideas:

-   Hash the installed file, keep track of its path (and name) as well as hash for identification of the exact file

# V1.1

1. Auto-detect common fonts such as those from Google fonts, allowing the `install font version` syntax, for QoL

# V1.2

1. Support for more than GitHub; ideally any Git remote with tagged commits as "releases"
    - Support for GitLab
2. Support for non-global installations (example use case: woff2 install insisde of a web app repo)

# V1.3

1. Auto-detect from more common font sources such as open-source foundries (collectttivo, bye bye binary, etc)

# V1.4

1. Come up with a system for paid fonts, where the repo shouldn't be publicly accessible, such as an access key/password of sorts

# V2.0

1. GUI, installation via a setup wizard/executable, for non terminal users

## Ideally (might not be technically possible)

-   List of changed glyphs depending on version
    -   Changed glyphs preview
