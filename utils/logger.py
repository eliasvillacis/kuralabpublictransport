# utils/logger.py
import logging, sys

__all__ = ["logger", "get_logger"]

def _configure_root() -> logging.Logger:
	root = logging.getLogger("kura")
	if not root.handlers:
		root.setLevel(logging.DEBUG)  # Changed from INFO to DEBUG to show API calls
		h = logging.StreamHandler(sys.stdout)
		h.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
		root.addHandler(h)
	return root

def get_logger(name: str | None = None) -> logging.Logger:
	root = _configure_root()
	return root if not name else root.getChild(name)

# Backward-compatible global logger
logger = _configure_root()
