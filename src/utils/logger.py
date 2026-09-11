"""
Logging utilities for CRIA.

Simple logger module that provides a configured logger instance.
"""

import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logger(
    name: str = "cria",
    level: int = logging.INFO,
    log_dir: str = "logs"
) -> logging.Logger:
    """
    Set up a logger with console and file output.

    Args:
        name: Logger name
        level: Logging level (default: INFO)
        log_dir: Directory for log files (default: "logs")

    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Clear existing handlers to avoid duplicates
    if logger.hasHandlers():
        logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    # Create file handler (only if log_dir is accessible)
    try:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        current_date = datetime.now().strftime("%Y%m%d")
        file_handler = logging.FileHandler(
            log_path / f"{name}_{current_date}.log"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    except (OSError, PermissionError) as e:
        # If we can't create log files, just use console
        logger.warning(f"Could not create log file: {e}")

    return logger


# Create default logger instance
logger = setup_logger()
