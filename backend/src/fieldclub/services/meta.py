"""Builds the `/meta` document: vocabularies, tiers, layers, providers and sources."""

from __future__ import annotations

from sqlalchemy.orm import Session

from fieldclub import APP_NAME, __version__, vocab
from fieldclub.auth.onboarding import allowed_age_bands
from fieldclub.auth.providers import provider_statuses
from fieldclub.config import Settings
from fieldclub.layers import TileVersion, build_layers, default_tile_version
from fieldclub.schemas import meta as schema
from fieldclub.services import record_tiles, records, sensitivity


def build_vocab() -> schema.Vocab:
    return schema.Vocab(
        feature_classes=[
            schema.FeatureClassOut(
                id=item.id,
                label=item.label,
                hint=item.hint,
                fish_term=item.fish_term,
                sensitivity=sensitivity.default_sensitivity(item.id),
            )
            for item in vocab.FEATURE_CLASSES
        ],
        periods=[schema.PeriodOut.model_validate(item) for item in vocab.PERIODS],
        evidence_kinds=[schema.EvidenceKindOut.model_validate(item) for item in vocab.EVIDENCE_KINDS],
        tiers=[schema.TierOut.model_validate(item) for item in vocab.TIERS],
        states=[schema.State.model_validate(item) for item in vocab.STATES],
        checks=[schema.CheckOut.model_validate(item) for item in vocab.CHECKS],
        explanations=[schema.ExplanationOut.model_validate(item) for item in vocab.EXPLANATIONS],
        mention_kinds=[schema.MentionKindOut.model_validate(item) for item in vocab.MENTION_KINDS],
        record_categories=[schema.RecordCategoryOut.model_validate(item) for item in vocab.RECORD_CATEGORIES],
        report_reasons=[schema.ReportReasonOut.model_validate(item) for item in vocab.REPORT_REASONS],
    )


def list_sources(db: Session) -> list[schema.SourceOut]:
    """Every enabled source, for the attribution list: the same list, in the same order, as `GET /sources`."""
    return [schema.SourceOut.model_validate(source) for source in records.list_sources(db)]


def build_notices() -> schema.Notices:
    notices = {nation.value: list(lines) for nation, lines in vocab.FIELD_VISIT_NOTICES.items()}
    reporting = {
        nation.value: schema.FindReporting(scheme=info.scheme, url=info.url, text=info.text)
        for nation, info in vocab.FIND_REPORTING.items()
    }
    return schema.Notices(
        field_visit=schema.FieldVisitNotices(**notices),
        field_visit_16_17=vocab.FIELD_VISIT_NOTICE_16_17,
        sensitivity=vocab.SENSITIVITY_NOTICE,
        find_reporting=schema.FindReportingNotices(**reporting),
    )


def build_layers_for(db: Session, tile_version: TileVersion = default_tile_version) -> schema.Layers:
    """The layer catalogue with the record tiles' address carrying the current `?v=` token.

    `tile_version` gives the token terrain tile URLs carry, normally the terrain service's.
    """
    layers = build_layers(tile_version)
    versioned = [record_tiles.tile_url(record_tiles.tile_token(db))]
    layers.overlays = [
        overlay.model_copy(update={"tiles": versioned})
        if isinstance(overlay, schema.RecordsOverlay)
        else overlay
        for overlay in layers.overlays
    ]
    return layers


def build_meta(
    db: Session, settings: Settings, *, tile_version: TileVersion = default_tile_version
) -> schema.Meta:
    """`tile_version` gives the token terrain tile URLs carry, normally the terrain service's."""
    return schema.Meta(
        app=schema.AppInfo(
            name=APP_NAME, version=__version__, contribution_licence=vocab.CONTRIBUTION_LICENCE
        ),
        auth=schema.AuthInfo(
            providers=[
                schema.Provider(id=info.id.value, label=info.label, enabled=enabled)
                for info, enabled in provider_statuses(settings)
            ],
            dev_login=settings.dev_login_enabled,
            age_bands=list(allowed_age_bands(settings)),
            terms=schema.Terms(summary=settings.terms_summary, url=settings.terms_url),
        ),
        vocab=build_vocab(),
        layers=build_layers_for(db, tile_version),
        sources=list_sources(db),
        notices=build_notices(),
    )
