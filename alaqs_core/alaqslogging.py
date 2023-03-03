import logging
from pathlib import Path

# Set the path to the log file
log_path = Path(__file__).parents[1] / 'alaqs.log'

# Set the message format
log_format = '%(asctime)s - %(levelname)s - %(name)-12s : %(message)s'
log_date_format = '%d-%m-%Y %H:%M:%S'

# Set the (default) log level
log_level = 'INFO'


def log_init():
    """
    Configure the logging module for the OpenALAQS plugin.
    """
    # Remove the log handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Configure the logger
    logging.basicConfig(level=logging.INFO,
                        format=log_format,
                        datefmt=log_date_format,
                        filename=log_path,
                        filemode='w')


def get_logger(name: str) -> logging.Logger:
    """
    Configure the logger for the indicated module by name.
    """
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    return logger
