# Font Manager

A CLI tool to manage fonts by downloading and installing them from GitHub releases.

## Installation

Ensure you have UV installed, then:

```bash
uv sync
```

## Usage

After installation, you can run:

```bash
fontpm install owner/repo [release]
```

For example:

```bash
fontpm install adobe-fonts/source-sans-pro latest
```

This will download the latest release's zip file, extract it, and place the fonts on your Desktop.

## Requirements

-   Python 3.14+
-   UV for dependency management
