import asyncio
import io
import zipfile
from collections.abc import AsyncGenerator
from pathlib import Path


def _build_zip(paths: list[str]) -> bytes:
    buf = io.BytesIO()
    seen: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for path in paths:
            p = Path(path)
            if not p.is_file():
                continue
            name = p.name
            if name in seen:
                stem, suffix = p.stem, p.suffix
                i = 1
                while f"{stem}_{i}{suffix}" in seen:
                    i += 1
                name = f"{stem}_{i}{suffix}"
            seen.add(name)
            zf.write(str(p), name)
    return buf.getvalue()


async def zip_generator(paths: list[str]) -> AsyncGenerator[bytes, None]:
    data = await asyncio.get_running_loop().run_in_executor(None, _build_zip, paths)
    chunk = 65536
    for i in range(0, len(data), chunk):
        yield data[i : i + chunk]
