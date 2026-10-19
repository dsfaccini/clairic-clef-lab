from __future__ import annotations

import asyncio
from datetime import date
from importlib.resources import files

import httpx2
from pydantic import JsonValue, TypeAdapter
from pydantic_ai.providers import cloudflare
from pytest import MonkeyPatch

from clairic_clef_lab.cli import (
    AmendmentFacts,
    Capture,
    ChoiceEvidence,
    Decision,
    ExtractionEvidence,
    FieldEvidence,
    Operation,
    make_card,
    replay,
    run_live,
)


def test_replay_keeps_an_absent_date_null_even_when_a_guess_exists() -> None:
    card = replay('missing-date')
    assert card.candidate == AmendmentFacts(target='artículo 12 de la Ley Demo B', article_number=12)
    assert card.operation == 'repeal'
    assert card.run is not None and card.run.mode == 'replay'
    assert card.field_evidence['effective_date'].guess == '2026-10-19'
    assert card.field_evidence['effective_date'].value is None


def test_replacement_capture_has_verifiable_unicode_source_offsets() -> None:
    card = replay('replacement')
    assert card.verified_target_span is not None
    start, end = card.verified_target_span
    assert card.source_state[start:end] == card.candidate.target
    assert card.candidate.effective_date == date(2027, 3, 1)


def test_bad_or_truncated_provenance_stays_visible() -> None:
    source = 'artículo 7'
    facts = AmendmentFacts(target=source, article_number=7, effective_date=date(2027, 3, 1))
    evidence = ExtractionEvidence(
        answers={'f0': FieldEvidence(type='text', value=source, span=(0, 999))},
        field_names={'f0': 'target'},
        truncated=True,
    )
    choice = ChoiceEvidence(choice=Operation.replacement, confidence=0.9, probabilities={'replacement': 0.9})
    card = make_card(source, facts, Decision(operation=Operation.replacement), evidence, choice)
    assert card.verified_target_span is None
    assert card.review.status == 'needs_review'
    assert 'The provider truncated its input.' in card.review.reasons
    assert 'The returned target could not be verified against its source offsets.' in card.review.reasons


def test_both_agents_consume_the_captured_service_results(monkeypatch: MonkeyPatch) -> None:
    capture = Capture.model_validate_json(
        files('clairic_clef_lab').joinpath('captures/replacement.json').read_text()
    )
    requested: list[str] = []

    def respond(request: httpx2.Request) -> httpx2.Response:
        payload = TypeAdapter(dict[str, JsonValue]).validate_json(request.content)
        assert payload['state'] == capture.state
        requested.append(request.url.path)
        if request.url.path.endswith('/@cf/cloudflare/clairic'):
            native = {'model': 'clairic', **capture.clairic.model_dump(mode='json', exclude_unset=True)}
        else:
            assert request.url.path.endswith('/@cf/cloudflare/clef')
            native = {'model': 'clef', **capture.clef.model_dump(mode='json', exclude_unset=True)}
        return httpx2.Response(200, json={'success': True, 'result': native})

    def make_client() -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(respond))

    monkeypatch.setenv('CLOUDFLARE_API_TOKEN', 'fixture-token')
    monkeypatch.setenv('CLOUDFLARE_ACCOUNT_ID', 'fixture-account')
    monkeypatch.setattr(cloudflare, 'create_async_httpx2_client', make_client)
    card = asyncio.run(run_live(capture.state))
    assert card.candidate.effective_date == date(2027, 3, 1)
    assert card.operation == Operation.replacement
    assert card.verified_target_span == (47, 74)
    assert len(requested) == 2
    assert card.run is not None and card.run.mode == 'live'
