"""Builds the `/meta` document: vocabularies, tiers, layers, providers and sources."""

from __future__ import annotations

from sqlalchemy.orm import Session

from fieldclub import APP_NAME, __version__, vocab
from fieldclub.auth.providers import provider_statuses
from fieldclub.config import Settings
from fieldclub.layers import build_layers
from fieldclub.schemas import meta as schema
from fieldclub.services import record_tiles, records


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
    """Every enabled source, for the attribution list: the same list, in the same order, as `GET /sources`."""
    return [schema.SourceOut.model_validate(source) for source in records.list_sources(db)]


def build_notices() -> schema.Notices:
    notices = {nation.value: list(lines) for nation, lines in vocab.FIELD_VISIT_NOTICES.items()}
    return schema.Notices(
        field_visit=schema.FieldVisitNotices(**notices),
        field_visit_16_17=vocab.FIELD_VISIT_NOTICE_16_17,
        sensitivity=vocab.SENSITIVITY_NOTICE,
    )


def build_layers_for(db: Session) -> schema.Layers:
    """The layer catalogue with the record tiles' address carrying the current `?v=` token."""
    layers = build_layers()
    versioned = [record_tiles.tile_url(record_tiles.tile_token(db))]
    layers.overlays = [
        overlay.model_copy(update={"tiles": versioned})
        if isinstance(overlay, schema.RecordsOverlay)
        else overlay
        for overlay in layers.overlays
    ]
    return layers


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
        layers=build_layers_for(db),
        sources=list_sources(db),
        notices=build_notices(),
    )
