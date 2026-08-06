import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dotenv

from core.r2 import AsyncR2Client


async def f():
    async with AsyncR2Client(
        endpoint=os.getenv("STATIC_ASSET_ENDPOINT_URL", ""),
        access_key=os.getenv("STATIC_ASSET_ACCESS_KEY_ID", ""),
        secret_key=os.getenv("STATIC_ASSET_SECRET_ACCESS_KEY", ""),
        bucket=os.getenv("STATIC_ASSET_BUCKET", ""),
    ) as s:
        body = await s.get("test/test.png")
        async with body:
            data = await body.read()
            with open("/tmp/test.png", "wb") as fd:
                fd.write(data)

        body = await s.get("test/test.png")
        with open("/tmp/test1.png", "wb") as fd:
            async with body:
                async for chunk in body.aiter_bytes():
                    fd.write(chunk)


if __name__ == "__main__":
    dotenv.load_dotenv()
    asyncio.run(f())
