# utils/logger.py
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# This global variable will cache the handlers after they are created the first time.
_HANDLERS = None

def get_logger(name: str) -> logging.Logger:
    """
    Creates and configures a logger instance.
    
    This function is designed to be resilient to interference from other libraries.
    It creates handlers only once and ensures they are attached to any logger
    that requests them, while preventing messages from propagating to the root logger.
    """
    logger = logging.getLogger(name)
    
    # Use LOG_LEVEL environment variable with a sensible default
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level, logging.INFO)
    logger.setLevel(level)
    
    # This is the key to preventing duplicate logs. We only add handlers
    # if the logger doesn't already have them.
    if not logger.handlers:
        for handler in _get_or_build_handlers():
            logger.addHandler(handler)
    
    # This is crucial to prevent interference. It stops messages from this logger
    # from being passed up to the root logger, which other libraries might have configured.
    logger.propagate = False
    
    return logger

def _get_or_build_handlers() -> list[logging.Handler]:
    """
    Builds and caches the logging handlers. This function will only execute its
    main logic once per application run, thanks to the global cache.
    """
    global _HANDLERS
    if _HANDLERS is not None:
        return _HANDLERS

    handlers: list[logging.Handler] = []
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # --- Console Handler ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)

    # --- Optional File Handler ---
    log_file = os.getenv("LOG_FILE")
    if log_file:
        try:
            # Use an absolute path to avoid ambiguity.
            abs_log_file = os.path.abspath(log_file)
            log_dir = os.path.dirname(abs_log_file)
            os.makedirs(log_dir, exist_ok=True)
            
            max_bytes = int(os.getenv("LOG_MAX_BYTES", 1_000_000))
            backups = int(os.getenv("LOG_BACKUPS", 3))
            
            # This handler rotates logs to keep file sizes manageable.
            file_handler = RotatingFileHandler(abs_log_file, maxBytes=max_bytes, backupCount=backups)
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)
        except Exception as e:
            # This is a robust fallback. If file logging fails for any reason
            # (e.g., permissions), print a loud error and continue with console logging.
            print(f"!!! CRITICAL LOGGER ERROR: Could not create file handler for '{log_file}'. Error: {e} !!!", file=sys.stderr)

    _HANDLERS = handlers
    return _HANDLERS