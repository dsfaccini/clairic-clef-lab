from __future__ import annotations

import argparse
import asyncio
from datetime import date
from enum import StrEnum
from importlib.resources import files
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, JsonValue, ValidationError
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelAPIError, UserError


class AmendmentFacts(BaseModel):
    target: str | None = Field(
        default=None,
        description='Copia el artículo afectado y su norma, exactamente como aparece en el texto.',
    )
    article_number: int | None = Field(default=None, description='Número del artículo afectado.')
    effective_date: date | None = Field(
        default=None,
        description='Fecha expresamente indicada para la entrada en vigor. Null si no aparece.',
    )
    publication_date: date | None = Field(
        default=None,
        description='Fecha de publicación expresamente indicada. Null si no aparece.',
    )


class Operation(StrEnum):
    replacement = 'replacement'
    '''Sustituye texto existente.'''
    addition = 'addition'
    '''Agrega una disposición.'''
    repeal = 'repeal'
    '''Elimina una disposición.'''
    other = 'other'
    '''Describe otra operación.'''
    unclear = 'unclear'
    '''El texto no permite determinar la operación.'''


class Decision(BaseModel):
    operation: Operation = Field(description='Operación legislativa expresamente descrita en el documento ficticio.')


class FieldEvidence(BaseModel):
    type: str
    value: JsonValue
    confidence: float | None = Field(default=None, ge=0, le=1)
    p_null: float | None = Field(default=None, ge=0, le=1)
    guess: JsonValue = None
    span: tuple[int, int] | None = None


class ExtractionEvidence(BaseModel):
    answers: dict[str, FieldEvidence]
    field_names: dict[str, str] = Field(default_factory=dict)
    state_text: str | None = None
    truncated: bool = False
    usage: dict[str, int] = Field(default_factory=dict)


class ChoiceEvidence(BaseModel):
    type: Literal['choice'] = 'choice'
    choice: Operation
    confidence: float = Field(ge=0, le=1)
    probabilities: dict[str, float]


class DecisionEvidence(BaseModel):
    answers: dict[str, ChoiceEvidence]
    usage: dict[str, int] = Field(default_factory=dict)


class DecisionMetadata(BaseModel):
    confidence: dict[str, float]
    probabilities: dict[str, dict[str, float]]


class Capture(BaseModel):
    name: str
    state: str
    recorded_on: date
    provenance: str
    requests: dict[str, JsonValue]
    clairic: ExtractionEvidence
    clef: DecisionEvidence


class Review(BaseModel):
    status: Literal['needs_review'] = 'needs_review'
    reasons: list[str]
    scope: str = 'Candidate amendment intake; legal effect and applicability have not been determined.'


class RunInfo(BaseModel):
    mode: Literal['live', 'replay']
    models: list[str]
    usage: dict[str, dict[str, int]]
    recorded_on: date | None = None
    provenance: str | None = None


class IntakeCard(BaseModel):
    candidate: AmendmentFacts
    operation: Operation
    source_state: str
    verified_target_span: tuple[int, int] | None
    field_evidence: dict[str, FieldEvidence]
    operation_evidence: ChoiceEvidence
    review: Review
    run: RunInfo | None = None


def make_card(
    source: str,
    facts: AmendmentFacts,
    decision: Decision,
    extraction: ExtractionEvidence,
    choice: ChoiceEvidence,
) -> IntakeCard:
    answers = {extraction.field_names.get(name, name): answer for name, answer in extraction.answers.items()}
    state = extraction.state_text if extraction.state_text is not None else source
    target = answers.get('target')
    verified_span: tuple[int, int] | None = None
    if target is not None and target.span is not None and facts.target is not None:
        start, end = target.span
        if 0 <= start < end <= len(state) and state[start:end] == facts.target:
            verified_span = (start, end)

    reasons: list[str] = []
    if facts.target is None:
        reasons.append('No target was found.')
    elif verified_span is None:
        reasons.append('The returned target could not be verified against its source offsets.')
    if facts.effective_date is None:
        reasons.append('No effective date was determined from the supplied text.')
    if facts.publication_date is None:
        reasons.append('No publication date was determined from the supplied text.')
    if decision.operation in (Operation.other, Operation.unclear):
        reasons.append('The operation needs classification review.')
    if extraction.truncated:
        reasons.append('The provider truncated its input.')
    return IntakeCard(
        candidate=facts,
        operation=decision.operation,
        source_state=state,
        verified_target_span=verified_span,
        field_evidence=answers,
        operation_evidence=choice,
        review=Review(reasons=reasons),
    )


def replay(name: str) -> IntakeCard:
    capture = Capture.model_validate_json(files('clairic_clef_lab').joinpath(f'captures/{name}.json').read_text())
    values: dict[str, JsonValue] = {name: answer.value for name, answer in capture.clairic.answers.items()}
    facts = AmendmentFacts.model_validate(values)
    choice = capture.clef.answers['operation']
    card = make_card(capture.state, facts, Decision(operation=choice.choice), capture.clairic, choice)
    card.run = RunInfo(
        mode='replay',
        models=['@cf/cloudflare/clairic', '@cf/cloudflare/clef'],
        recorded_on=capture.recorded_on,
        provenance=capture.provenance,
        usage={'clairic': capture.clairic.usage, 'clef': capture.clef.usage},
    )
    return card


async def run_live(source: str) -> IntakeCard:
    async with (
        Agent('cloudflare:@cf/cloudflare/clairic', output_type=AmendmentFacts) as extractor,
        Agent('cloudflare:@cf/cloudflare/clef', output_type=Decision) as decider,
    ):
        extracted = await extractor.run(source)
        decided = await decider.run(source)
    extraction = ExtractionEvidence.model_validate(extracted.response.provider_details)
    metadata = DecisionMetadata.model_validate(decided.response.provider_details)
    choice = ChoiceEvidence(
        choice=decided.output.operation,
        confidence=metadata.confidence['operation'],
        probabilities=metadata.probabilities['operation'],
    )
    card = make_card(source, extracted.output, decided.output, extraction, choice)
    extraction_usage: dict[str, int] = {
        **extracted.response.usage.details,
        'input_tokens': extracted.response.usage.input_tokens,
        'output_tokens': extracted.response.usage.output_tokens,
    }
    decision_usage: dict[str, int] = {
        **decided.response.usage.details,
        'input_tokens': decided.response.usage.input_tokens,
        'output_tokens': decided.response.usage.output_tokens,
    }
    card.run = RunInfo(
        mode='live',
        models=[
            extracted.response.model_name or '@cf/cloudflare/clairic',
            decided.response.model_name or '@cf/cloudflare/clef',
        ],
        usage={'clairic': extraction_usage, 'clef': decision_usage},
    )
    return card


def main() -> None:
    parser = argparse.ArgumentParser(description='Inspect Clairic extraction and Clef decisions on fictional amendments.')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--replay', choices=('replacement', 'missing-date'), default=None)
    mode.add_argument('--file', type=Path, help='Send the UTF-8 text file to the live models.')
    args = parser.parse_args()
    try:
        if args.file is not None:
            source = args.file.read_text(encoding='utf-8')
            if not source.strip():
                parser.error('The source file must contain text.')
            card = asyncio.run(run_live(source))
        else:
            card = replay(args.replay or 'replacement')
    except (OSError, ValidationError, UserError, ModelAPIError) as error:
        parser.exit(1, f'{error}\n')
    print(card.model_dump_json(indent=2))
