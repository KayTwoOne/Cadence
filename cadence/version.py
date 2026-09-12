"""Single source of truth for the version, read by the UI and by the build."""

__version__ = "0.3.1"
APP_NAME = "Cadence"
APP_TAGLINE = "controller input suite"

# Where updates will be looked for once the repo is public. Nothing reads this yet;
# it is here so the version string and the update source stay in one place.
REPO = "KayTwoOne/Cadence"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases/latest"
