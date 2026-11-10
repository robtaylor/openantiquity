"""Builds the `/meta` document: vocabularies, tiers, layers, providers and sources."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub import APP_NAME, __version__, vocab
from fieldclub.auth.providers import provider_statuses
from fieldclub.config import Settings
from fieldclub.layers import build_layers
from fieldclub.models import Source
from fieldclub.schemas import meta as schema


def build_vocab() -> schema.Vocab:
    return schema.Vocab(
        feature_classes=[schema.FeatureClassOut.model_validate(item) for item in vocab.FEATURE_CLASSES],
        periods=[schema.PeriodOut.model_validate(item) for item in vocab.PERIODS],
        evidence_kinds=[schema.EvidenceKindOut.model_validate(item) for item in vocab.EVIDENCE_KINDS],
        tiers=[schema.TierOut.model_validate(item) for item in vocab.TIERS],
        states=[schema.StateOut.model_validate(item) for item in vocab.STATES],
        checks=[schema.CheckOut.model_validate(item) for item in vocab.CHECKS],
        explanations=[schema.ExplanationOut.model_validate(item) for item in vocab.EXPLANATIONS],
        mention_kinds=[schema.MentionKindOut.model_validate(item) for item in vocab.MENTION_KINDS],
        record_categories=[schema.RecordCategoryOut.model_validate(item) for item in vocab.RECORD_CATEGORIES],
    )


def list_sources(db: Session) -> list[schema.SourceOut]:
    """Every enabled source, for the attribution list."""
    sources = db.scalars(select(Source).where(Source.enabled).order_by(Source.category, Source.name)).all()
    return [schema.SourceOut.model_validate(source) for source in sources]


def build_notices() -> schema.Notices:
    notices = {nation.value: list(lines) for nation, lines in vocab.FIELD_VISIT_NOTICES.items()}
    return schema.Notices(
        field_visit=schema.FieldVisitNotices(**notices),
        field_visit_16_17=vocab.FIELD_VISIT_NOTICE_16_17,
        sensitivity=vocab.SENSITIVITY_NOTICE,
    )


def build_meta(db: Session, settings: Settings) -> schema.Meta:
    return schema.Meta(
        app=schema.AppInfo(
            name=APP_NAME, version=__version__, contribution_licence=vocab.CONTRIBUTION_LICENCE
        ),
        auth=schema.AuthInfo(
            providers=[
                schema.ProviderOut(id=info.id.value, label=info.label, enabled=enabled)
                for info, enabled in provider_statuses(settings)
            ]
        ),
        vocab=build_vocab(),
        layers=build_layers(),
        sources=list_sources(db),
        notices=build_notices(),
    )
