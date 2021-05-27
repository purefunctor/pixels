from __future__ import annotations

import asyncio
from enum import Enum
from functools import partial
import typing as t

from aiohttp import ClientResponse, ClientSession
import attr

from pixels import exceptions as e
from pixels import pixel


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
        self._api_key = api_key
        self._session: t.Optional[ClientSession] = None
        self.limiter = Limiter()

    def _create_session(self) -> None:
        if self._session is None:
            self._session = ClientSession()

    @property
    def session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            raise e.ClientError(
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
        while True:
            request = self.session.request(
                method,
                endpoint.value,
                params=params,
                json=json,
                headers=_headers,
            )
            async with request as response:
                cooldown = self.limiter.consume_headers(endpoint, response.headers)
                if cooldown is not None:
                    await asyncio.sleep(cooldown)
                if response.status >= 500:
                    raise e.FatalGatewayError("server panic!")
                elif 400 <= response.status < 500:
                    raise e.GatewayError(response.status, await response.text())
                return await decode(response)

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
            Endpoint.SET_PIXEL, "post", _just_decode, json=pxl.to_json()
        )


async def _just_decode(r: ClientResponse) -> dict[str, str]:
    return await r.json()


Cls = t.TypeVar("Cls")


class Limits(t.Protocol):
    @property
    def cooldown(self) -> t.Optional[int]:
        ...

    @classmethod
    def from_json(cls: t.Type[Cls], m: t.Mapping) -> Cls:
        ...


@attr.s
class Active:
    remaining: int = attr.ib(converter=int)
    limit: int = attr.ib(converter=int)
    reset: int = attr.ib(converter=int)

    @property
    def cooldown(self) -> t.Optional[int]:
        if self.remaining == 0:
            return self.reset
        return None

    @classmethod
    def from_json(cls, m: t.Mapping) -> Active:
        markers = (
            "Requests-Remaining",
            "Requests-Limit",
            "Requests-Reset",
        )
        if any(marker not in m for marker in markers):
            raise ValueError("endpoint does not have limits")
        return Active(*(m[marker] for marker in markers))


@attr.s
class Inactive:
    _cooldown: int = attr.ib(converter=int)

    @property
    def cooldown(self) -> t.Optional[int]:
        return self._cooldown

    @classmethod
    def from_json(cls, m: t.Mapping) -> Inactive:
        return Inactive(m["Cooldown-Reset"])


@attr.s
class Limiter:
    limits: dict[Endpoint, Limits] = attr.ib(factory=dict)

    def consume_headers(
        self, endpoint: Endpoint, headers: t.Mapping
    ) -> t.Optional[int]:
        for _class in Inactive, Active:
            try:
                limits = t.cast(t.Type[Limits], _class).from_json(headers)
            except (ValueError, KeyError):
                continue
            else:
                self.limits[endpoint] = limits
                return limits.cooldown
        else:
            return None
