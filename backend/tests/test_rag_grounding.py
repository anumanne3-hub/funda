from uuid import uuid4

import pytest

from app.rag.contracts import RetrievalScope, RetrievedEvidence, SourceLocation
from app.rag.grounding import INSUFFICIENT_EVIDENCE, grounded_answer


class FakeRetrieval:
    def __init__(self, evidence):
        self.evidence = evidence

    async def search(self, _scope, _query, *, limit):
        assert limit == 5
        return self.evidence


class FakeProvider:
    def __init__(self, answer):
        self.answer = answer
        self.prompts = []
        self.model = "fake"

    async def stream(self, prompt):
        self.prompts.append(prompt)
        yield self.answer


@pytest.mark.asyncio
async def test_grounded_answer_requires_evidence_and_citation():
    scope = RetrievalScope(uuid4(), uuid4(), None)
    provider = FakeProvider("Unsupported")
    empty = await grounded_answer(scope, "What happened?", FakeRetrieval([]), provider)
    assert empty.content == INSUFFICIENT_EVIDENCE
    assert provider.prompts == []

    evidence = RetrievedEvidence(
        document_id=uuid4(),
        document_version_id=uuid4(),
        chunk_id=uuid4(),
        title="Report",
        text="The mission launched.",
        location=SourceLocation(page=2),
    )
    unsupported = await grounded_answer(
        scope, "What happened?", FakeRetrieval([evidence]), provider
    )
    assert unsupported.content == INSUFFICIENT_EVIDENCE
    assert "untrusted data" in provider.prompts[-1]
    assert "The mission launched." in provider.prompts[-1]

    cited_provider = FakeProvider("The mission launched [1].")
    cited = await grounded_answer(
        scope, "What happened?", FakeRetrieval([evidence]), cited_provider
    )
    assert cited.content == "The mission launched [1]."
    assert cited.evidence == [evidence]
