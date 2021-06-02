import logging.handlers
import os

LOG_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                             "alaqs-log.log")
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

# adds the root logger
logger_format = '%(asctime)s - %(levelname)s - %(name)-12s : %(message)s'
logger_date_format = '%d-%m-%Y %H:%M:%S'

logging.basicConfig(level=logging.INFO,
                    format=logger_format,
                    datefmt=logger_date_format,
                    filename=LOG_FILE_PATH,
                    filemode='w')

# logger = logging.getLogger(__name__)
# logger.setLevel('DEBUG')

# Use FileHandler() to log to a file
# file_handler = logging.FileHandler(LOG_FILE_PATH, mode='w')
# formatter = logging.Formatter(logger_format)
# file_handler.setFormatter(formatter)
# logger.addHandler(file_handler)
