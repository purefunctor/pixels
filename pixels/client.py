from __future__ import annotations

import typing as t
from enum import Enum
from functools import partial

from aiohttp import ClientResponse, ClientSession

import attr

from pixels import pixel
from pixels.exceptions import ClientError


T = t.TypeVar("T")


_MAKE_ENDPOINT = "https://pixels.pythondiscord.com/{}".format


class Endpoint(Enum):
    GET_PIXELS = _MAKE_ENDPOINT("get_pixels")
    GET_PIXEL = _MAKE_ENDPOINT("get_pixel")
    GET_SIZE = _MAKE_ENDPOINT("get_size")
    SET_PIXEL = _MAKE_ENDPOINT("set_pixel")


_Method = t.Literal["get", "post"]


class Client:
    def __init__(self, api_key: str) -> None:
        # TODO: Rate limiter service
        self._api_key = api_key
        self._session: t.Optional[ClientSession] = None

    def _create_session(self) -> None:
        if self._session is None:
            self._session = ClientSession()

    @property
    def session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            raise ClientError(
                "ClientSession does not exist or is closed. "
                "Use with a context manager instead."
            )
        return self._session

    async def __aenter__(self) -> Client:
        self._create_session()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:  # noqa: ANN001
        if self._session is None:
            return
        await self._session.close()
        self._session = None

    async def _request(
        self,
        endpoint: Endpoint,
        method: _Method,
        decode: t.Callable[[ClientResponse], t.Awaitable[T]],
        *,
        json: t.Mapping = None,
        params: t.Mapping[str, str] = None,
    ) -> T:
        _headers = {"Authorization": f"Bearer {self._api_key}"}
        async with self.session.request(
            method, endpoint.value, params=params, json=json, headers=_headers
        ) as response:
            return await decode(response)
        # TODO: Response status validation, more exceptions

    async def get_pixels(self, size: pixel.CanvasSize) -> pixel.Canvas:
        _decode = partial(pixel._decode_canvas, size)
        return await self._request(
            Endpoint.GET_PIXELS,
            "get",
            _decode,
        )

    async def get_pixel(self, x: int, y: int) -> pixel.Pixel:
        return await self._request(
            Endpoint.GET_PIXEL,
            "get",
            pixel._decode_pixel,
            params={"x": str(x), "y": str(y)},
        )

    async def get_size(self) -> pixel.CanvasSize:
        return await self._request(Endpoint.GET_SIZE, "get", pixel._decode_canvas_size)

    async def set_pixel(self, pxl: pixel.Pixel) -> dict[str, str]:
        return await self._request(
            Endpoint.SET_PIXEL, "post", _just_decode, json=attr.asdict(pxl)
        )


async def _just_decode(r: ClientResponse) -> dict[str, str]:
    return await r.json()
