class PixelsError(Exception):
    """Base exception class for the library."""


class ClientError(PixelsError):
    """Exceptions raised by the `Client` class."""
