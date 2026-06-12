"""xzSSH package."""
from importlib.metadata import PackageNotFoundError, version as _dist_version

__all__ = ["__version__"]

# Fallback for environments where package metadata is unavailable — notably
# the Nuitka onefile release binaries. Must match pyproject.toml's version;
# tests/test_version.py and scripts/check_version.py enforce that.
_FALLBACK_VERSION = "0.17.0"

try:
    __version__ = _dist_version("xzssh")
except PackageNotFoundError:
    __version__ = _FALLBACK_VERSION
