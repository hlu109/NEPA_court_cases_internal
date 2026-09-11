"""
General logging utility for CourtListener data processing
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum

# Add project root to Python path to allow imports from src.utils
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.utils.config import RUN_DIR


class LogLevel(Enum):
    """Log level enumeration"""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class Logger:
    """
    General-purpose activity logger.
    """

    def __init__(self,
                 log_filename: str = "log.txt",
                 log_dir: Path = RUN_DIR,
                 console_output: bool = True,
                 log_level: LogLevel = LogLevel.INFO):
        """
        Initialize the logger.

        Args:
            log_filename: File name
            log_dir: Directory to save log file 
            console_output: Whether to also output to console
            log_level: Minimum log level to record
        """
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = log_dir / log_filename

        # Set up logger
        self.logger = logging.getLogger('courtlistener_activity')
        self.logger.setLevel(log_level.value)

        # Clear any existing handlers
        self.logger.handlers.clear()

        # File handler
        file_handler = logging.FileHandler(self.log_path, encoding='utf-8')
        file_handler.setLevel(log_level.value)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)

        # Console handler (optional)
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(log_level.value)
            console_formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S')
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)

        # Statistics tracking
        self.stats = {
            'info': 0,
            'warnings': 0,
            'errors': 0,
            'downloads_successful': 0,
            'downloads_failed': 0,
            'api_requests': 0,
            'api_errors': 0
        }
        self.error_details = []

    def debug(self, message: str, **kwargs):
        """Log debug message"""
        self.logger.debug(self._format_message(message, **kwargs))

    def info(self, message: str, **kwargs):
        """Log info message"""
        self.stats['info'] += 1
        self.logger.info(self._format_message(message, **kwargs))

    def warning(self, message: str, **kwargs):
        """Log warning message"""
        self.stats['warnings'] += 1
        self.logger.warning(self._format_message(message, **kwargs))

    def error(self,
              message: str,
              exception: Optional[Exception] = None,
              **kwargs):
        """Log error message with optional exception details"""
        self.stats['errors'] += 1

        error_msg = self._format_message(message, **kwargs)
        if exception:
            error_msg += f" | Exception: {type(exception).__name__}: {str(exception)}"
            self.error_details.append({
                'message': message,
                'exception_type': type(exception).__name__,
                'exception_msg': str(exception),
                'kwargs': kwargs
            })

        self.logger.error(error_msg)

    def critical(self,
                 message: str,
                 exception: Optional[Exception] = None,
                 **kwargs):
        """Log critical error message"""
        self.stats['errors'] += 1
        error_msg = self._format_message(message, **kwargs)
        if exception:
            error_msg += f" | Exception: {type(exception).__name__}: {str(exception)}"
            self.error_details.append({
                'message': message,
                'exception_type': type(exception).__name__,
                'exception_msg': str(exception),
                'kwargs': kwargs
            })
        self.logger.critical(error_msg)

    def _format_message(self, message: str, **kwargs) -> str:
        """Format message with optional context"""
        if kwargs:
            context = " | ".join([f"{k}={v}" for k, v in kwargs.items()])
            return f"{message} | {context}"
        return message

    # Convenience methods for specific use cases
    def log_download_success(self, opinion_id: int, message: str = ""):
        """Log successful download"""
        self.stats['downloads_successful'] += 1
        msg = f"Download SUCCESS: Opinion {opinion_id}"
        if message:
            msg += f" - {message}"
        self.info(msg, opinion_id=opinion_id)

    def log_download_failure(self,
                             opinion_id: int,
                             error: str,
                             exception: Optional[Exception] = None):
        """Log failed download"""
        self.stats['downloads_failed'] += 1
        msg = f"Download FAILED: Opinion {opinion_id} - {error}"
        self.error(msg, exception=exception, opinion_id=opinion_id)

    def log_api_request(self, endpoint: str, status: str = "success"):
        """Log API request"""
        self.stats['api_requests'] += 1
        if status != "success":
            self.stats['api_errors'] += 1
        self.debug(f"API Request: {endpoint} | Status: {status}")

    def log_api_error(self,
                      endpoint: str,
                      error: str,
                      exception: Optional[Exception] = None):
        """Log API error"""
        self.stats['api_errors'] += 1
        msg = f"API Error: {endpoint} - {error}"
        self.error(msg, exception=exception, endpoint=endpoint)

    def print_summary(self):
        """Print summary of logged activity and append it to the log file"""
        lines = [
            "=" * 60,
            "ACTIVITY SUMMARY",
            "=" * 60,
            f"Info messages: {self.stats['info']}",
            f"Warnings: {self.stats['warnings']}",
            f"Errors: {self.stats['errors']}",
            f"Downloads successful: {self.stats['downloads_successful']}",
            f"Downloads failed: {self.stats['downloads_failed']}",
            f"API requests: {self.stats['api_requests']}",
            f"API errors: {self.stats['api_errors']}",
            f"Log saved to: {self.log_path}",
        ]

        if self.error_details:
            lines.append("")
            lines.append("First 5 errors:")
            for i, error in enumerate(self.error_details[:5], 1):
                lines.append(f"  {i}. {error['message']}")
                lines.append(
                    f"     Exception: {error['exception_type']}: {error['exception_msg']}"
                )
        lines.append("=" * 60)

        summary = "\n" + "\n".join(lines) + "\n"
        print(summary)

        # also write the summary to the log file
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(summary)

    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics"""
        return self.stats.copy()

    def get_error_details(self) -> list:
        """Get list of error details"""
        return self.error_details.copy()


# Global logger instance (will be initialized by config)
_logger_instance: Optional[Logger] = None


def get_logger() -> Logger:
    """
    Get the global logger instance
    
    Returns:
        Logger instance
    """
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = Logger(log_dir=RUN_DIR)
    return _logger_instance


def set_logger(logger: Logger):
    """
    Set the global logger instance
    
    Args:
        logger: Logger instance to use globally
    """
    global _logger_instance
    _logger_instance = logger
