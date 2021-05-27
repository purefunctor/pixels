import asyncio
from os import getenv

from dotenv import load_dotenv

from pixels.client import Client


async def main() -> None:

    token = getenv("PIXELS_TOKEN")
    if token is None:
        raise RuntimeError("no token found")

    async with Client(token) as client:
        size = await client.get_size()
        canvas = await client.get_pixels(size)
        pixel = await client.get_pixel(0, 0)
        print(pixel)
        canvas.to_image().show()


if __name__ == "__main__":
    load_dotenv(".env")
    asyncio.run(main())
