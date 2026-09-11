# -*- coding: utf-8 -*-
"""
Logging utilities
"""
import logging
import os
from pathlib import Path
import sys
from datetime import datetime
from zoneinfo import ZoneInfo  # or import pytz if Python < 3.9


class LoggerSetup:
    """Class for setting up loggers with consistent formatting and behavior"""

    @staticmethod
    def setup_logger(name, log_dir, level=logging.INFO, timezone="America/Chicago"):
        """
        Set up a logger with the specified name, directory, and level.

        Args:
            name: Logger name
            log_dir: Directory to store log files
            level: Logging level
            timezone: Timezone for log timestamps (default: America/Chicago)

        Returns:
            Configured logger
        """
        # Convert log_dir to Path object
        log_dir = Path(log_dir)

        # Create log directory if it doesn't exist
        os.makedirs(log_dir, exist_ok=True)

        # Create logger
        logger = logging.getLogger(name)
        logger.setLevel(level)

        # Clear existing handlers to avoid duplicate logs when reimporting
        if logger.hasHandlers():
            logger.handlers.clear()

        # Apply timezone
        try:
            tz = ZoneInfo(timezone)
            # Set the converter function to use our timezone
            logging.Formatter.converter = lambda *args: datetime.now(tz).timetuple()
        except (ImportError, ValueError):
            # Fallback to UTC if timezone is invalid or ZoneInfo not available
            tz = None
            logger.warning(
                f"Could not use timezone '{timezone}', falling back to system default"
            )

        # Create formatter with military time format
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H%M",  # Military time without colons
        )

        # Create file handler with current date in filename
        current_date = (
            datetime.now(tz).strftime("%Y%m%d")
            if tz
            else datetime.now().strftime("%Y%m%d")
        )
        file_handler = logging.FileHandler(log_dir / f"{name}_{current_date}.log")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)

        # Create console handler with color formatting
        console_handler = VisualConsoleHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)

        # Add handlers to logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        return logger


class VisualConsoleHandler(logging.StreamHandler):
    """Handler that adds color to console log output"""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[94m",  # Blue
        "INFO": "\033[92m",  # Green
        "WARNING": "\033[93m",  # Yellow
        "ERROR": "\033[91m",  # Red
        "CRITICAL": "\033[91m",  # Red (bold)
        "RESET": "\033[0m",  # Reset to default
    }

    def __init__(self, stream=None):
        """Initialize the handler with optional stream (defaults to sys.stderr)"""
        super().__init__(stream or sys.stderr)
        # Check if the terminal supports colors
        self.use_colors = hasattr(self.stream, "isatty") and self.stream.isatty()

    def emit(self, record):
        """
        Emit a record with color formatting

        Args:
            record: LogRecord instance
        """
        # Add color to levelname if supported
        if self.use_colors:
            levelname = record.levelname
            if levelname in self.COLORS:
                record.levelname = (
                    f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"
                )

        super().emit(record)


# Test function
def test_logger():
    """Test the logger setup"""
    # Create a test log directory
    test_log_dir = Path("logs")

    # Setup loggers at different levels
    debug_logger = LoggerSetup.setup_logger("debug_test", test_log_dir, logging.DEBUG)
    info_logger = LoggerSetup.setup_logger("info_test", test_log_dir, logging.INFO)

    # Log test messages
    debug_logger.debug("This is a DEBUG message")
    debug_logger.info("This is an INFO message")
    debug_logger.warning("This is a WARNING message")
    debug_logger.error("This is an ERROR message")
    debug_logger.critical("This is a CRITICAL message")

    info_logger.debug("This DEBUG message should not appear")
    info_logger.info("This is an INFO message")

    print(f"Logs written to: {test_log_dir}")


# Test code (runs when module is executed directly)
if __name__ == "__main__":
    test_logger()
