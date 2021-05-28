import sys

from loguru import logger


FORMAT = (
    "<blue>pixels</blue> | "
    "<cyan>[{time}]</cyan> | "
    "<level>{level:<8}</level> | "
    "<cyan>{name}</cyan>:"
    "<cyan>{function}</cyan>"
    ":<cyan>{line}</cyan> - "
    "<level>{message}</level>"
)

logger.configure(
    handlers=[
        dict(sink=sys.stdout, format=FORMAT, colorize=True)
    ],
)

logger.disable("pixels")
