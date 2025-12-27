"""
Logging configuration for Qdrant and memory components.
Pattern adapted from: /Users/won.suh/Project/rag-hybrid-qdrant/logging_config.py

Provides rotating file handlers and component-specific loggers
for the translation system memory tier.
"""
import logging
import logging.handlers
import os
from datetime import datetime
from typing import Dict, Optional

# Default log directory
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')


def setup_logger(
    name: str,
    log_file: str,
    level: int = logging.DEBUG,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> logging.Logger:
    """
    Setup a logger with file and console handlers.

    Args:
        name: Logger name (e.g., 'qdrant_manager')
        log_file: Path to log file
        level: Logging level (default: DEBUG)
        max_bytes: Max file size before rotation (default: 10MB)
        backup_count: Number of backup files to keep (default: 5)

    Returns:
        Configured logger instance
    """
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger

    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

    # Create file handler with rotation
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(file_formatter)

    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)  # Only show INFO and above in console
    console_handler.setFormatter(console_formatter)

    # Add handlers to logger
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


def setup_qdrant_loggers(log_dir: Optional[str] = None) -> Dict[str, logging.Logger]:
    """
    Setup loggers for all Qdrant/memory components.

    Args:
        log_dir: Directory for log files (default: phase2/logs)

    Returns:
        Dict mapping component names to logger instances
    """
    if log_dir is None:
        log_dir = LOG_DIR

    # Create logs directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)

    # Get current timestamp for log filenames
    timestamp = datetime.now().strftime('%Y%m%d')

    # Setup component loggers
    loggers = {
        'qdrant_manager': setup_logger(
            'memory.qdrant_manager',
            os.path.join(log_dir, f'qdrant_manager_{timestamp}.log')
        ),
        'qdrant_data_loader': setup_logger(
            'loaders.qdrant_data_loader',
            os.path.join(log_dir, f'qdrant_data_loader_{timestamp}.log')
        ),
        'qdrant_config': setup_logger(
            'memory.qdrant_config',
            os.path.join(log_dir, f'qdrant_config_{timestamp}.log')
        )
    }

    return loggers


def get_qdrant_logger(component: str = 'qdrant_manager') -> logging.Logger:
    """
    Get or create a logger for a Qdrant component.

    Args:
        component: Component name ('qdrant_manager', 'qdrant_data_loader', 'qdrant_config')

    Returns:
        Logger instance for the component
    """
    logger_name_map = {
        'qdrant_manager': 'memory.qdrant_manager',
        'qdrant_data_loader': 'loaders.qdrant_data_loader',
        'qdrant_config': 'memory.qdrant_config'
    }

    logger_name = logger_name_map.get(component, component)
    logger = logging.getLogger(logger_name)

    # If logger has no handlers, set up basic config
    if not logger.handlers:
        os.makedirs(LOG_DIR, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d')
        log_file = os.path.join(LOG_DIR, f'{component}_{timestamp}.log')
        return setup_logger(logger_name, log_file)

    return logger


# Initialize loggers when module is imported (lazy initialization)
def init_logging():
    """Initialize all Qdrant loggers. Call once at application startup."""
    return setup_qdrant_loggers()
