"""Fixed citation contract cases independent of a hosted model response."""

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.rag.contracts import RetrievalScope, RetrievedEvidence, SourceLocation
from app.rag.grounding import INSUFFICIENT_EVIDENCE, grounded_answer

CASES = json.loads((Path(__file__).resolve().parents[1] / "evals/citation_cases.json").read_text())


class FixedRetrieval:
    def __init__(self, sources: list[str]):
        self.evidence = [
            RetrievedEvidence(
                document_id=UUID(int=index),
                document_version_id=UUID(int=index + 100),
                chunk_id=UUID(int=index + 200),
                title=f"Fixture {index}",
                text=source,
                location=SourceLocation(page=index),
            )
            for index, source in enumerate(sources, 1)
        ]

    async def search(self, _scope, _query, *, limit):
        assert limit == 5
        return self.evidence


class FixedProvider:
    def __init__(self, answer: str):
        self.answer = answer
        self.calls = 0

    async def stream(self, _prompt):
        self.calls += 1
        yield self.answer


@pytest.mark.asyncio
@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
async def test_fixed_citation_cases(case):
    retrieval = FixedRetrieval(case["sources"])
    provider = FixedProvider(case["model_answer"])
    result = await grounded_answer(
        RetrievalScope(uuid4(), uuid4(), None), case["question"], retrieval, provider
    )
    if case["expected"] == "grounded":
        assert result.content == case["model_answer"]
        assert result.evidence == retrieval.evidence
        assert result.cited_ordinals == case["cited_ordinals"]
    else:
        assert result.content == INSUFFICIENT_EVIDENCE
        assert result.evidence == []
        assert result.cited_ordinals == []
    assert provider.calls == (1 if case["sources"] else 0)
