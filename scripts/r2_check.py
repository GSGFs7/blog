import asyncio
import os
import sys
from pathlib import Path

import dotenv
from blake3 import blake3

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.r2 import AsyncR2Client, ObjectNotFound, PreconditionFailed

ROOT = Path(__file__).parent.parent


async def f():
    async with AsyncR2Client(
        endpoint=os.getenv("STATIC_ASSET_ENDPOINT_URL", ""),
        access_key=os.getenv("STATIC_ASSET_ACCESS_KEY_ID", ""),
        secret_key=os.getenv("STATIC_ASSET_SECRET_ACCESS_KEY", ""),
        bucket=os.getenv("STATIC_ASSET_BUCKET", ""),
    ) as s:
        fd = open(ROOT / "manage.py", "rb")
        raw = fd.read()
        fd.close()

        key = "test/manage.py"
        h = blake3(raw).hexdigest()

        await s.put(key, raw)

        async with await s.get(key) as body:
            assert blake3(await body.read()).hexdigest() == h

        assert (await s.stat(key)).size == len(raw)

        print((await s.list(prefix="test")))

        try:
            await s.put(key, raw, if_none_match="*")
        except PreconditionFailed:
            pass
        else:
            raise Exception("failed!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

        await s.delete(key)

        try:
            await s.get(key)
        except ObjectNotFound:
            pass
        else:
            raise Exception("failed!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")


async def mp():
    class AStream:
        async def __aiter__(self):
            for i in range(2):
                yield bytes(5 * 1024**2)

    async with AsyncR2Client(
        endpoint=os.getenv("STATIC_ASSET_ENDPOINT_URL", ""),
        access_key=os.getenv("STATIC_ASSET_ACCESS_KEY_ID", ""),
        secret_key=os.getenv("STATIC_ASSET_SECRET_ACCESS_KEY", ""),
        bucket=os.getenv("STATIC_ASSET_BUCKET", ""),
        multipart_part_size=5 * 1024**2,
    ) as s:
        key = "/test/test.bin"

        await s.put(key, AStream(), strategy="multipart")


if __name__ == "__main__":
    dotenv.load_dotenv()
    asyncio.run(f())
    asyncio.run(mp())
