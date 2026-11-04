import hashlib

import pytest

from app.rag.prepare import PreparationError, prepare_website


@pytest.mark.asyncio
async def test_website_preparation_preserves_source_and_chunks():
    original = b"<h1>Facts</h1><p>Earth orbits the Sun.</p>"

    async def fake_fetch(url, allowed):
        assert url in allowed
        return "text/html", original

    prepared = await prepare_website(
        "https://example.com/facts", {"https://example.com/facts"}, fetch=fake_fetch
    )
    assert prepared.content_hash == hashlib.sha256(original).hexdigest()
    assert prepared.original == original
    assert prepared.chunks[0].location.section == "Facts"
    assert prepared.chunks[0].text == "Earth orbits the Sun."


@pytest.mark.asyncio
async def test_empty_website_is_not_prepared():
    async def fake_fetch(_url, _allowed):
        return "text/plain", b"   "

    with pytest.raises(PreparationError):
        await prepare_website("https://example.com/empty", set(), fetch=fake_fetch)
