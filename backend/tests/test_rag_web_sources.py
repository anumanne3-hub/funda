import socket

import httpx
import pytest

from app.rag.web_sources import MAX_BYTES, SourceFetchError, fetch_website, validate_public_url


def resolver(ip):
    def lookup(_host, _port, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 443))]

    return lookup


def test_public_url_validation():
    allowed = {"https://example.com/source", "https://localhost/source"}
    validate_public_url("https://example.com/source", allowed, resolve=resolver("93.184.215.14"))
    with pytest.raises(SourceFetchError):
        validate_public_url("https://localhost/source", allowed, resolve=resolver("127.0.0.1"))
    with pytest.raises(SourceFetchError):
        validate_public_url("https://example.com/other", allowed, resolve=resolver("93.184.215.14"))


@pytest.mark.asyncio
async def test_redirect_is_revalidated_and_body_is_bounded():
    source = "https://example.com/source"
    destination = "https://example.com/final"
    requests = []

    def handler(request):
        requests.append(
            (str(request.url), request.headers["host"], request.extensions["sni_hostname"])
        )
        if request.url.path == "/source":
            return httpx.Response(302, headers={"Location": destination})
        return httpx.Response(200, headers={"Content-Type": "text/plain"}, content=b"hello")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(SourceFetchError):
            await fetch_website(source, {source}, client=client, resolve=resolver("93.184.215.14"))
        assert requests == [("https://93.184.215.14/source", "example.com", "example.com")]
        media_type, body = await fetch_website(
            source, {source, destination}, client=client, resolve=resolver("93.184.215.14")
        )
        assert (media_type, body) == ("text/plain", b"hello")
        assert requests[-2:] == [
            ("https://93.184.215.14/source", "example.com", "example.com"),
            ("https://93.184.215.14/final", "example.com", "example.com"),
        ]

        large = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200, headers={"Content-Type": "text/html"}, content=b"x" * (MAX_BYTES + 1)
                )
            )
        )
        async with large:
            with pytest.raises(SourceFetchError):
                await fetch_website(
                    source, {source}, client=large, resolve=resolver("93.184.215.14")
                )
