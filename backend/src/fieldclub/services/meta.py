"""Builds the `/meta` document: vocabularies, the ladder's numbers, layers, providers, sources, terrain and
the limits on shapes."""

from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.orm import Session

from fieldclub import APP_NAME, __version__, vocab
from fieldclub.auth.onboarding import allowed_age_bands
from fieldclub.auth.providers import provider_statuses
from fieldclub.config import Settings
from fieldclub.layers import TileVersion, build_layers, default_tile_version
from fieldclub.schemas import meta as schema
from fieldclub.services import looked_at, record_tiles, records, sensitivity, shapes
from fieldclub.services.confidence import STEP_RULES, THRESHOLDS
from fieldclub.services.findings import FIELD_KINDS, OFFICIAL_KINDS
from fieldclub.terrain.catalogue import england_catalogue
from fieldclub.terrain.service import TerrainStatus
from fieldclub.terrain.styles import FINE_MINZOOM


def follow_up(kind: vocab.EvidenceKind) -> vocab.FollowUp:
    """Whether adding evidence of this kind logs `followup_logged`, and of which sort.

    From the sets `services.findings` logs it by, so the timeline and the log agree.
    """
    if kind in FIELD_KINDS:
        return vocab.FollowUp.FIELD
    if kind in OFFICIAL_KINDS:
        return vocab.FollowUp.OFFICIAL
    return vocab.FollowUp.NONE


def build_vocab() -> schema.Vocab:
    steps = {info.id: info for info in vocab.NEXT_STEPS}
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
        evidence_kinds=[
            schema.EvidenceKindOut(**asdict(item), follow_up=follow_up(item.id))
            for item in vocab.EVIDENCE_KINDS
        ],
        tiers=[schema.TierOut.model_validate(item) for item in vocab.TIERS],
        states=[schema.State.model_validate(item) for item in vocab.STATES],
        checks=[schema.CheckKindOut.model_validate(item) for item in vocab.CHECKS],
        explanations=[schema.ExplanationOut.model_validate(item) for item in vocab.EXPLANATIONS],
        mention_kinds=[schema.MentionKindOut.model_validate(item) for item in vocab.MENTION_KINDS],
        record_categories=[schema.RecordCategoryOut.model_validate(item) for item in vocab.RECORD_CATEGORIES],
        report_reasons=[schema.ReportReasonOut.model_validate(item) for item in vocab.REPORT_REASONS],
        next_steps=[
            schema.NextStepRuleOut(
                id=rule.code,
                label=steps[rule.code].label,
                description=steps[rule.code].description,
                met_by=rule.met_by,
                evidence_kinds=list(rule.evidence_kinds),
                record_relations=list(rule.record_relations),
                outcome=rule.outcome,
                stance=rule.stance,
                endorsement=rule.endorsement,
                needs_verification=rule.needs_verification,
            )
            for rule in STEP_RULES
        ],
        link_shows=[schema.LinkShowsOut.model_validate(item) for item in vocab.LINK_SHOWS],
        link_coverages=[schema.LinkCoverageOut.model_validate(item) for item in vocab.LINK_COVERAGES],
        link_verified=[schema.LinkVerifiedOut.model_validate(item) for item in vocab.LINK_VERIFIED],
        sensitivity_levels=[
            schema.SensitivityLevelOut(
                id=item.id,
                label=item.label,
                who_sees=item.who_sees,
                square_sentence=item.square_sentence,
                exact_for=[viewer for viewer in vocab.SensitivityViewer if viewer in item.exact_for],
            )
            for item in vocab.SENSITIVITY_LEVELS
        ],
    )


def build_ladder() -> schema.Ladder:
    """The ladder's numbers, read from the engine's `THRESHOLDS` and role weights, never copied."""
    t = THRESHOLDS
    weight = vocab.role_weight
    return schema.Ladder(
        weights=schema.LadderWeights(
            member=weight(vocab.Role.MEMBER),
            trusted=weight(vocab.Role.TRUSTED),
            expert=weight(vocab.Role.EXPERT),
        ),
        seen=schema.SeenRule(weight=t.seen_weight, observers=t.seen_observers, ratio=t.seen_ratio),
        corroborated=schema.CorroboratedRule(
            strands=t.corroborating_strands,
            class_agreement=t.class_agreement,
            class_people=t.class_people,
            class_support=t.class_support,
        ),
        probable=schema.ProbableRule(
            check_weight=t.check_weight,
            check_margin=t.check_margin,
            seen_without_reviewer=t.probable_seen_without_reviewer,
        ),
        evidence=schema.EvidenceRule(endorsement_weight=t.endorsement_weight, known_weight=t.known_weight),
        disputed=schema.DisputedRule(
            weight=t.disputed_weight, ratio_low=t.disputed_ratio_low, ratio_high=t.disputed_ratio_high
        ),
        ruled_out=schema.RuledOutRule(
            unseen=t.ruled_out_unseen, ratio=t.ruled_out_ratio, explanation=t.ruled_out_explanation
        ),
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


def terrain_state(status: TerrainStatus | None) -> schema.TerrainState:
    """The terrain facts `/meta` gives, or, without a terrain service, those of no build."""
    if status is None:
        return schema.TerrainState(
            fine_minzoom=FINE_MINZOOM,
            catalogue_tiles=len(england_catalogue()),
            mirrored_tiles=None,
            overview=schema.OverviewState(built=False, built_at=None, tiles=0, covers_mirror=None),
        )
    overview = status.overview
    return schema.TerrainState(
        fine_minzoom=status.fine_minzoom,
        catalogue_tiles=status.catalogue_tiles,
        mirrored_tiles=status.mirrored_tiles,
        overview=schema.OverviewState(
            built=overview.built,
            built_at=overview.built_at,
            tiles=overview.tiles,
            covers_mirror=overview.covers_mirror,
        ),
    )


def build_meta(
    db: Session,
    settings: Settings,
    *,
    tile_version: TileVersion = default_tile_version,
    terrain: TerrainStatus | None = None,
) -> schema.Meta:
    """`tile_version` gives the token terrain tile URLs carry, and `terrain` the terrain's state,
    normally both the terrain service's."""
    return schema.Meta(
        app=schema.AppInfo(
            name=APP_NAME,
            version=__version__,
            contribution_licence=vocab.CONTRIBUTION_LICENCE,
            contribution_licence_url=vocab.CONTRIBUTION_LICENCE_URL,
            contact=settings.contact.strip() or None,
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
        terrain=terrain_state(terrain),
        ladder=build_ladder(),
        shapes=schema.ShapeLimits(
            path_max_points=shapes.PATH_MAX_POINTS,
            shape_max_vertices=shapes.SHAPE_MAX_VERTICES,
            shape_max_across_m=shapes.SHAPE_MAX_ACROSS_M,
            line_max_length_m=shapes.LINE_MAX_LENGTH_M,
            shape_max_gap_m=shapes.SHAPE_MAX_GAP_M,
            curve=shapes.CURVE,
            looked_at_max_move_m=looked_at.LOOKED_AT_MAX_MOVE_M,
            looked_at_min_kept=looked_at.LOOKED_AT_MIN_KEPT,
        ),
    )
