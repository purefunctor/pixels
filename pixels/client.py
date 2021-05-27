from __future__ import annotations

import asyncio
import typing as t
from enum import Enum
from functools import partial

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
                method, endpoint.value, params=params, json=json, headers=_headers,
            )
            async with request as response:
                status, cooldown = self.limiter.notify(endpoint, response.headers)
                if status in [LimitsStatus.LOW_RESOURCE, LimitsStatus.ON_COOLDOWN]:
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
            Endpoint.SET_PIXEL, "post", _just_decode, json=attr.asdict(pxl)
        )


async def _just_decode(r: ClientResponse) -> dict[str, str]:
    return await r.json()


@attr.s
class _Active:
    remaining: int = attr.ib(converter=int)
    limit: int = attr.ib(converter=int)
    reset: int = attr.ib(converter=int)

    def is_low(self) -> bool:
        return self.remaining == 1


@attr.s
class _Inactive:
    cooldown: int = attr.ib(converter=int)


class LimitsStatus(Enum):
    ALL_GREEN = 0
    LOW_RESOURCE = 1
    ON_COOLDOWN = 2


@attr.s
class Limits:
    endpoint: Endpoint = attr.ib()
    current: t.Union[_Active, _Inactive] = attr.ib()

    @classmethod
    def from_json(cls, endpoint: Endpoint, m: t.Mapping) -> Limits:
        if "Cooldown-Reset" in m:
            return Limits(endpoint, _Inactive(m["Cooldown-Reset"]))
        else:
            markers = (
                "Requests-Remaining",
                "Requests-Limit",
                "Requests-Reset",
            )
            if any(marker not in m for marker in markers):
                raise ValueError("endpoint does not have limits")
            return Limits(endpoint, _Active(*(m[marker] for marker in markers)))

    @property
    def status(self) -> tuple[LimitsStatus, int]:
        if isinstance(self.current, _Active):
            if self.current.is_low():
                return LimitsStatus.LOW_RESOURCE, self.current.reset
            else:
                return LimitsStatus.ALL_GREEN, 0
        elif isinstance(self.current, _Inactive):
            return LimitsStatus.ON_COOLDOWN, self.current.cooldown


@attr.s
class Limiter:
    limits: dict[Endpoint, Limits] = attr.ib(factory=dict)

    def notify(
        self, endpoint: Endpoint, headers: t.Mapping
    ) -> tuple[LimitsStatus, int]:
        try:
            limits = Limits.from_json(endpoint, headers)
            self.limits[endpoint] = Limits.from_json(endpoint, headers)
            return limits.status
        except ValueError:
            return LimitsStatus.ALL_GREEN, 0
