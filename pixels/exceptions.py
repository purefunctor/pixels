class PixelsError(Exception):
    """Base exception class for the library."""


class ClientError(PixelsError):
    """Exceptions raised by the `Client` class."""


class GatewayError(ClientError):
    """Exceptions raised from interaction with the API."""


class FatalGatewayError(GatewayError):
    """Fatal exceptions raised from server-side errors."""
