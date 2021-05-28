from __future__ import annotations

import itertools
import re
import typing as t

from aiohttp import ClientResponse
import attr
from PIL import Image as PIL_Image  # type: ignore
from PIL.Image import Image  # type: ignore


_HEX_PATTERN = "#?" + "([A-Za-z0-9]{2})" * 3


def _from_hex(hxt: t.Union[str, int]) -> int:
    if isinstance(hxt, str):
        return int(hxt, base=16)
    else:
        return hxt


@attr.s(frozen=True, slots=True)
class RGB:
    r: int = attr.ib(converter=_from_hex)
    g: int = attr.ib(converter=_from_hex)
    b: int = attr.ib(converter=_from_hex)

    def as_hex_string(self) -> str:
        return f"{self.r:02x}{self.g:02x}{self.b:02x}"

    @classmethod
    def from_hex_string(cls, hxt: str) -> RGB:
        err = ValueError(f"invalid hex string {hxt}")
        _match = re.match(_HEX_PATTERN, hxt)
        if _match is None:
            raise err
        try:
            return RGB(*_match.groups())
        except ValueError:
            raise err from None


@attr.s(frozen=True, slots=True)
class Pixel:
    x: int = attr.ib(converter=int)
    y: int = attr.ib(converter=int)
    rgb: RGB = attr.ib()

    @classmethod
    def from_json(cls, m: t.Mapping) -> Pixel:
        return Pixel(
            m["x"],
            m["y"],
            RGB.from_hex_string(m["rgb"]),
        )

    def to_json(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "rgb": self.rgb.as_hex_string(),
        }


@attr.s(frozen=True, slots=True)
class CanvasSize:
    width: int = attr.ib(converter=int)
    height: int = attr.ib(converter=int)

    @classmethod
    def from_json(cls, m: t.Mapping) -> CanvasSize:
        return CanvasSize(m["width"], m["height"])


def chunks_of(i: t.Iterable, n: int) -> t.Iterable:
    args = [iter(i)] * n
    return zip(*args)


@attr.s
class Canvas:
    size: CanvasSize = attr.ib()
    _canvas: dict[tuple[int, int], RGB] = attr.ib(factory=dict)

    def __getitem__(self, index: tuple[int, int]) -> RGB:
        return self._canvas[index]

    @classmethod
    def from_bytes(cls, size: CanvasSize, stream: bytes) -> Canvas:
        _canvas = {}
        chunks = iter(chunks_of(stream, 3))
        for y, x in itertools.product(range(size.height), range(size.width)):
            _canvas[x, y] = RGB(*next(chunks))
        return Canvas(size, _canvas)

    def to_image(self) -> Image:
        image = PIL_Image.new("RGB", attr.astuple(self.size), "black")

        image.putdata([attr.astuple(rgb) for rgb in self._canvas.values()])

        return image


async def _decode_pixel(response: ClientResponse) -> Pixel:
    return Pixel.from_json(await response.json())


async def _decode_canvas_size(response: ClientResponse) -> CanvasSize:
    return CanvasSize.from_json(await response.json())


async def _decode_canvas(size: CanvasSize, response: ClientResponse) -> Canvas:
    return Canvas.from_bytes(size, await response.content.read())
