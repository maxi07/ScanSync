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

console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

logger = logging.getLogger("shared_logger")
logger.setLevel(logging.DEBUG)
logger.addHandler(console_handler)
