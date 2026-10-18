import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx


class ServiceError(Exception):
    pass


async def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ServiceError("下载地址不是有效的公开 HTTP(S) 地址")
    try:
        addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, parsed.port or 443)
    except OSError as error:
        raise ServiceError("无法解析下载地址") from error
    if not addresses or any(not ipaddress.ip_address(entry[4][0]).is_global for entry in addresses):
        raise ServiceError("禁止从私有网络地址抓取论文")
    return url


async def public_download(url, destination, max_bytes=60 * 1024 * 1024):
    async with httpx.AsyncClient(timeout=35, follow_redirects=False) as client:
        for _attempt in range(6):
            await public_url(url)
            async with client.stream(
                "GET", url, headers={"User-Agent": "Paper-SA/0.1 (literature research)"}
            ) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                size = 0
                prefix = b""
                with destination.open("wb") as handle:
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise ServiceError("PDF 超过 60 MB 限制")
                        if len(prefix) < 5:
                            prefix = (prefix + chunk)[:5]
                            if len(prefix) == 5 and prefix != b"%PDF-":
                                raise ServiceError("服务器返回了网页而不是 PDF")
                        handle.write(chunk)
                return
        raise ServiceError("下载重定向次数过多")
