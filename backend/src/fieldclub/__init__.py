"""Field Club: a collaborative map for finding and checking archaeological earthworks."""

from importlib.metadata import PackageNotFoundError, version

APP_NAME = "Field Club"

try:
    __version__ = version("fieldclub")
except PackageNotFoundError:  # pragma: no cover - only when run from an uninstalled checkout
    __version__ = "0.0.0"

__all__ = ["APP_NAME", "__version__"]
