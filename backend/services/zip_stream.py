import asyncio
import os
import zipstream
from collections.abc import AsyncGenerator


async def _stream_zip(zs: zipstream.ZipStream) -> AsyncGenerator[bytes, None]:
    _sentinel = object()
    loop = asyncio.get_running_loop()
    it = iter(zs)
    while True:
        chunk = await loop.run_in_executor(None, next, it, _sentinel)
        if chunk is _sentinel:
            break
        yield chunk


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

    async for chunk in _stream_zip(zs):
        yield chunk


async def zip_generator_from_content(items: list[tuple[str, object]]) -> AsyncGenerator[bytes, None]:
    """items: [(arcname, content), ...] — 디스크 파일이 아니라 메모리에서 생성한
    내용을 스트리밍 ZIP으로 묶을 때 사용(XMP export 전용). zip_generator()와 달리
    arcname을 호출자가 그대로 지정하므로(원본과 동일한 상대 폴더 구조 유지 목적)
    파일명 중복 처리를 하지 않는다 — **호출자가 arcname 유일성을 직접 보장해야
    한다**(예: XMP export는 확장자를 뺀 stem이 겹치면 원본 파일명 전체로 대체).

    content는 str/bytes를 직접 넘겨도 되지만, 대량 export(XMP export처럼 대상이
    라이브러리 전체일 수 있는 경우)에서는 iterator를 넘기는 걸 권장한다.
    zipstream-ng는 str/bytes를 add() 시점에 그대로 메모리에 들고 있지만, iterator는
    실제 인코딩 시점(아래 _stream_zip 스트리밍 중, 한 항목씩)까지 소비를 미루므로
    전체를 한꺼번에 메모리에 올리지 않는다."""
    zs = zipstream.ZipStream(compress_type=zipstream.ZIP_DEFLATED)
    for arcname, content in items:
        zs.add(content, arcname)

    async for chunk in _stream_zip(zs):
        yield chunk
