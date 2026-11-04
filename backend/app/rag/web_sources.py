"""Bounded fetch of explicitly configured public website sources."""

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

import httpx

MAX_REDIRECTS = 3
MAX_BYTES = 2 * 1024 * 1024
ALLOWED_TYPES = {"text/plain", "text/html", "text/markdown"}


class SourceFetchError(Exception):
    pass


def validate_public_url(
    url: str, allowed_urls: set[str], *, resolve: Callable[..., list[tuple]] = socket.getaddrinfo
) -> str:
    try:
        parsed = urlsplit(url)
        if (
            url not in allowed_urls
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.port not in (None, 443)
        ):
            raise SourceFetchError("Source URL is not permitted")
        addresses = resolve(parsed.hostname, 443, type=socket.SOCK_STREAM)
        if not addresses:
            raise SourceFetchError("Source host has no address")
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise SourceFetchError("Source host resolves to a non-public address")
        return str(ipaddress.ip_address(addresses[0][4][0]))
    except (ValueError, OSError) as exc:
        raise SourceFetchError("Source URL could not be validated") from exc


async def fetch_website(
    url: str,
    allowed_urls: set[str],
    *,
    client: httpx.AsyncClient | None = None,
    resolve: Callable[..., list[tuple]] = socket.getaddrinfo,
) -> tuple[str, bytes]:
    """Return media type and bounded body. No assets, links, or subpages are crawled."""
    owned_client = client is None
    if client is None:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": "FundaSourceIndexer/1.0"},
        )
    try:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            address = validate_public_url(current, allowed_urls, resolve=resolve)
            hostname = urlsplit(current).hostname
            assert hostname is not None
            pinned_url = httpx.URL(current).copy_with(host=address)
            try:
                async with client.stream(
                    "GET",
                    pinned_url,
                    headers={"Host": hostname},
                    extensions={"sni_hostname": hostname},
                    follow_redirects=False,
                ) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise SourceFetchError("Redirect has no location")
                        current = urljoin(current, location)
                        continue
                    response.raise_for_status()
                    media_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                    if media_type not in ALLOWED_TYPES:
                        raise SourceFetchError("Unsupported source type")
                    declared = response.headers.get("content-length")
                    if declared and int(declared) > MAX_BYTES:
                        raise SourceFetchError("Source exceeds size limit")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_BYTES:
                            raise SourceFetchError("Source exceeds size limit")
                    return media_type, bytes(body)
            except (httpx.HTTPError, ValueError) as exc:
                raise SourceFetchError("Source request failed") from exc
        raise SourceFetchError("Too many redirects")
    finally:
        if owned_client:
            await client.aclose()
