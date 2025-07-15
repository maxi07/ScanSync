import logging
import colorlog

log_colors = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}

formatter = colorlog.ColoredFormatter(
    "%(log_color)s%(levelname)-8s%(reset)s %(asctime)s - %(message)s",
    log_colors=log_colors,
    datefmt="%d.%m.%Y %H:%M:%S",
)

file_formatter = logging.Formatter(
    "%(levelname)-8s %(asctime)s - %(filename)s:%(lineno)d - %(message)s",
    datefmt="%d.%m.%Y %H:%M:%S",
)

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

file_handler = logging.FileHandler("logfile.log", encoding="utf-8")
file_handler.setLevel(logging.WARNING)
file_handler.setFormatter(file_formatter)

# Logger einrichten
logger = logging.getLogger("shared_logger")
logger.setLevel(logging.DEBUG)
logger.addHandler(console_handler)
logger.addHandler(file_handler)
