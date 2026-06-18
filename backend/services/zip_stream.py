import asyncio
import os
import zipstream
from collections.abc import AsyncGenerator


async def zip_generator(paths: list[str]) -> AsyncGenerator[bytes, None]:
    zs = zipstream.ZipStream(compress_type=zipstream.ZIP_DEFLATED)
    seen: dict[str, int] = {}
    for path in paths:
        if not os.path.isfile(path):
            continue
        name = os.path.basename(path)
        stem, ext = os.path.splitext(name)
        if name in seen:
            seen[name] += 1
            name = f"{stem}_{seen[name]}{ext}"
        else:
            seen[name] = 0
        zs.add_path(path, name)

    _sentinel = object()
    loop = asyncio.get_running_loop()
    it = iter(zs)
    while True:
        chunk = await loop.run_in_executor(None, next, it, _sentinel)
        if chunk is _sentinel:
            break
        yield chunk
