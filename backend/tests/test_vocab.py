"""Vocabularies are complete, consistent and written for beginners."""

from __future__ import annotations

import itertools
import math
import re
from pathlib import Path

import pytest

from fieldclub import vocab


def test_feature_classes_match_the_design_list() -> None:
    assert [info.id.value for info in vocab.FEATURE_CLASSES] == [
        "enclosure",
        "hillfort",
        "round_barrow",
        "long_barrow",
        "hut_circle",
        "settlement",
        "field_system",
        "ridge_and_furrow",
        "linear",
        "trackway",
        "road",
        "moat",
        "motte",
        "platform",
        "pond",
        "pit",
        "industrial",
        "military",
        "ritual",
        "garden",
        "unknown",
    ]


def test_feature_classes_have_one_sentence_hints_and_fish_terms() -> None:
    for info in vocab.FEATURE_CLASSES:
        assert info.label, info.id
        assert info.label[0].isupper(), info.label
        assert 20 <= len(info.hint) <= 110, f"{info.id}: hint should be one short sentence"
        assert info.hint.endswith("."), info.hint
        assert info.fish_term == info.fish_term.upper(), "FISH terms are written in capitals"
        assert re.fullmatch(r"[A-Z ]+", info.fish_term), info.fish_term
    terms = [info.fish_term for info in vocab.FEATURE_CLASSES]
    assert len(set(terms)) == len(terms), "each class maps to its own thesaurus term"


def test_the_not_sure_class_is_called_unknown() -> None:
    # The confidence rules ignore `unknown` when working out class agreement.
    info = vocab.FEATURE_CLASSES[-1]
    assert (info.id, info.label) == (vocab.FeatureClass.UNKNOWN, "Not sure")


def test_periods() -> None:
    assert [info.id.value for info in vocab.PERIODS] == [
        "prehistoric",
        "neolithic",
        "bronze_age",
        "iron_age",
        "roman",
        "early_medieval",
        "medieval",
        "post_medieval",
        "modern",
        "unknown",
    ]
    by_id = {info.id: info for info in vocab.PERIODS}
    assert by_id[vocab.Period.IRON_AGE].label == "Iron Age"
    assert by_id[vocab.Period.IRON_AGE].hint == "800 BC to AD 43"
    assert all(info.hint for info in vocab.PERIODS)


def test_evidence_kinds_follow_the_strand_rules() -> None:
    strands = {info.id.value: info.strand.value for info in vocab.EVIDENCE_KINDS}
    assert strands == {
        "lidar_view": "lidar",
        "aerial": "aerial",
        "historic_map": "historic_map",
        "record_link": "records",
        "document": "literature",
        "photo": "ground",
        "field_visit": "ground",
        "geophysics": "survey",
        "excavation": "survey",
        "her_record": "official",
        "designation": "official",
        "publication": "official",
    }
    assert {strand.value for strand in vocab.DESK_STRANDS} == {
        "lidar",
        "aerial",
        "historic_map",
        "records",
        "literature",
    }
    for info in vocab.EVIDENCE_KINDS:
        expected = (
            vocab.EvidenceGroup.DESK
            if info.strand in vocab.DESK_STRANDS
            else vocab.EvidenceGroup.OFFICIAL
            if info.strand is vocab.Strand.OFFICIAL
            else vocab.EvidenceGroup.FIELD
        )
        assert info.group is expected, info.id
        assert info.hint.endswith(".")
    assert vocab.EVIDENCE_STRANDS[vocab.EvidenceKind.AERIAL] is vocab.Strand.AERIAL


def test_strand_for_gives_every_kind_but_a_record_link_its_one_strand() -> None:
    for info in vocab.EVIDENCE_KINDS:
        if info.id is not vocab.EvidenceKind.RECORD_LINK:
            assert vocab.strand_for(info.id) is info.strand
            assert vocab.strand_for(info.id.value, None) is info.strand


@pytest.mark.parametrize(
    ("relation", "strand"),
    [
        ("related", vocab.Strand.RECORDS),
        ("part_of", vocab.Strand.RECORDS),
        # "It is this record" drives the known state. It corroborates nothing new.
        ("same_as", None),
        (None, None),
    ],
)
def test_a_record_link_counts_for_the_records_strand_only_when_related_or_part_of(
    relation: str | None, strand: vocab.Strand | None
) -> None:
    assert vocab.strand_for("record_link", relation) is strand
    assert vocab.strand_for(vocab.EvidenceKind.RECORD_LINK, relation) is strand


def test_strand_for_refuses_unknown_kinds_and_relations() -> None:
    with pytest.raises(ValueError, match="hunch"):
        vocab.strand_for("hunch")
    with pytest.raises(ValueError, match="cousin"):
        vocab.strand_for("record_link", "cousin")


def test_tiers_have_the_contract_labels_and_scores() -> None:
    assert [(info.id.value, info.label, info.base_score) for info in vocab.TIERS] == [
        ("spotted", "Spotted", 10),
        ("seen", "Seen by others", 30),
        ("corroborated", "Corroborated", 50),
        ("probable", "Probable", 70),
        ("ground_checked", "Checked on the ground", 85),
        ("confirmed", "On record", 100),
    ]
    assert vocab.tier_rank("spotted") == 0
    assert vocab.tier_rank(vocab.Tier.CONFIRMED) == 5
    assert vocab.TIER_BASE_SCORES[vocab.Tier.PROBABLE] == 70


def test_states() -> None:
    assert [info.id.value for info in vocab.STATES] == ["open", "known", "disputed", "ruled_out", "withdrawn"]
    by_id = {info.id: info for info in vocab.STATES}
    assert by_id[vocab.FindingState.KNOWN].label == "Matches a known record"
    assert {reason.value for reason in vocab.StateReason} == {
        "not_visible",
        "modern",
        "natural",
        "artefact",
        "ground_check",
    }


def test_checks_pair_with_explanations() -> None:
    assert [info.id.value for info in vocab.CHECKS] == ["not_modern", "not_natural", "not_artefact"]
    assert vocab.CHECKS[0].question == "Could it be modern?"
    assert all(info.question.endswith("?") for info in vocab.CHECKS)
    assert {check.value: explanation.value for check, explanation in vocab.CHECK_EXPLANATIONS.items()} == {
        "not_modern": "modern",
        "not_natural": "natural",
        "not_artefact": "artefact",
    }
    assert [info.id.value for info in vocab.EXPLANATIONS] == ["modern", "natural", "artefact"]
    assert vocab.EXPLANATIONS[0].label == "Modern feature"


def test_mention_kinds() -> None:
    assert [info.id.value for info in vocab.MENTION_KINDS] == [
        "video",
        "article",
        "podcast",
        "paper",
        "broadcast",
        "social",
    ]
    assert vocab.MENTION_KINDS[0].label == "Video"


def test_record_categories_have_distinct_colours() -> None:
    assert [info.id.value for info in vocab.RECORD_CATEGORIES] == [
        "designation",
        "monument",
        "find",
        "event",
        "document",
        "community",
        "map_label",
    ]
    colours = [info.colour for info in vocab.RECORD_CATEGORIES]
    assert all(re.fullmatch(r"#[0-9a-f]{6}", colour) for colour in colours)
    assert len(set(colours)) == len(colours)
    assert vocab.RECORD_CATEGORIES[0].label == "Designations"
    assert vocab.RECORD_CATEGORIES[0].colour == "#ff2f99"


UI_DOC = Path(__file__).resolve().parents[2] / "docs" / "UI.md"


def _lab(colour: str) -> tuple[float, float, float]:
    """CIE L*a*b* (D65) of an sRGB colour."""
    channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def _de2000(one: str, two: str) -> float:
    """The CIEDE2000 colour difference."""
    (l1, a1, b1), (l2, a2, b2) = _lab(one), _lab(two)
    c_bar = (math.hypot(a1, b1) + math.hypot(a2, b2)) / 2
    g = 0.5 * (1 - math.sqrt(c_bar**7 / (c_bar**7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p = math.degrees(math.atan2(b1, a1p)) % 360
    h2p = math.degrees(math.atan2(b2, a2p)) % 360
    dh = h2p - h1p
    if c1p * c2p == 0:
        dh = 0.0
    elif dh > 180:
        dh -= 360
    elif dh < -180:
        dh += 360
    d_hp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2))
    l_bar, c_barp = (l1 + l2) / 2, (c1p + c2p) / 2
    if c1p * c2p == 0:
        h_bar = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        h_bar = (h1p + h2p) / 2
    else:
        h_bar = (h1p + h2p + (360 if h1p + h2p < 360 else -360)) / 2
    t = (
        1
        - 0.17 * math.cos(math.radians(h_bar - 30))
        + 0.24 * math.cos(math.radians(2 * h_bar))
        + 0.32 * math.cos(math.radians(3 * h_bar + 6))
        - 0.20 * math.cos(math.radians(4 * h_bar - 63))
    )
    rotation = 30 * math.exp(-(((h_bar - 275) / 25) ** 2))
    r_c = 2 * math.sqrt(c_barp**7 / (c_barp**7 + 25**7))
    s_l = 1 + 0.015 * (l_bar - 50) ** 2 / math.sqrt(20 + (l_bar - 50) ** 2)
    s_c, s_h = 1 + 0.045 * c_barp, 1 + 0.015 * c_barp * t
    r_t = -math.sin(math.radians(2 * rotation)) * r_c
    dl, dc = (l2 - l1) / s_l, (c2p - c1p) / s_c
    return math.sqrt(dl**2 + dc**2 + (d_hp / s_h) ** 2 + r_t * dc * (d_hp / s_h))


def _contrast(one: str, two: str) -> float:
    def luminance(colour: str) -> float:
        channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    high, low = sorted((luminance(one), luminance(two)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_the_cielab_difference_is_the_standard_one() -> None:
    # A colour is 0 from itself, and black is 100 from white.
    assert _de2000("#336699", "#336699") == 0
    assert _de2000("#000000", "#ffffff") == pytest.approx(100, abs=0.01)


def test_record_colours_stand_apart_from_the_interfaces_tiers_and_states() -> None:
    """A record's square mustn't read as a finding's tier or state, nor vanish into grey terrain."""
    css = UI_DOC.read_text(encoding="utf-8")
    tokens = dict(re.findall(r"--([a-z-]+):\s*(#[0-9a-f]{6})", css))
    named = {"tier-seen", "tier-confirmed", "state-known", "state-ruled-out", "good", "bad", "info", "accent"}
    assert named <= set(tokens)
    background = tokens.pop("bg")
    for name in ("surface", "raised", "border", "on-accent"):
        tokens.pop(name)
    colours = [info.colour for info in vocab.RECORD_CATEGORIES]
    greys = [f"#{level:02x}{level:02x}{level:02x}" for level in range(16, 256, 16)]
    for colour in colours:
        assert min(_de2000(colour, token) for token in tokens.values()) >= 20, colour
        assert min(_de2000(colour, grey) for grey in greys) >= 20, colour
        assert _contrast(colour, background) >= 3, colour
    for one, two in itertools.combinations(colours, 2):
        assert _de2000(one, two) >= 20, (one, two)


def test_every_next_step_and_every_kind_of_link_has_words_to_show() -> None:
    for table in (vocab.NEXT_STEPS, vocab.LINK_SHOWS):
        for info in table:
            assert info.label, info
            assert info.description.endswith("."), info
            assert "_" not in info.label, info
    assert [info.label for info in vocab.LINK_COVERAGES][:4] == [
        "England",
        "Scotland",
        "Wales",
        "Northern Ireland",
    ]


def test_roles_are_the_five_in_the_contract() -> None:
    assert [role.value for role in vocab.Role] == ["member", "trusted", "expert", "moderator", "admin"]
    assert [info.id for info in vocab.ROLES] == list(vocab.Role)


def test_role_weights() -> None:
    # Three values: member 1.0, trusted 1.5, expert 3.0. Moderators and admins
    # count as trusted. There is no lower weight for anonymous input.
    assert {role.value: weight for role, weight in vocab.ROLE_WEIGHTS.items()} == {
        "member": 1.0,
        "trusted": 1.5,
        "expert": 3.0,
        "moderator": 1.5,
        "admin": 1.5,
    }
    assert sorted(set(vocab.ROLE_WEIGHTS.values())) == [1.0, 1.5, 3.0]
    assert vocab.role_weight("member") == 1.0
    assert vocab.role_weight(vocab.Role.EXPERT) == 3.0
    with pytest.raises(ValueError, match="wizard"):
        vocab.role_weight("wizard")
    with pytest.raises(ValueError, match="guest"):
        vocab.role_weight("guest")


def test_roles_that_see_restricted_locations() -> None:
    assert {role.value for role in vocab.EXACT_LOCATION_ROLES} == {"trusted", "expert", "moderator", "admin"}


def test_moderators_and_admins_count_as_trusted_reviewers() -> None:
    assert {role.value for role in vocab.REVIEWER_ROLES} == {"trusted", "expert", "moderator", "admin"}
    assert vocab.Role.MEMBER not in vocab.REVIEWER_ROLES
    assert {role.value for role in vocab.MODERATOR_ROLES} == {"moderator", "admin"}


def test_sign_in_providers_are_the_six_in_the_contract_in_sign_in_order() -> None:
    assert [(info.id.value, info.label) for info in vocab.SIGN_IN_PROVIDERS] == [
        ("google", "Google"),
        ("apple", "Apple"),
        ("microsoft", "Microsoft"),
        ("facebook", "Facebook"),
        ("osm", "OpenStreetMap"),
        ("email", "Email link"),
    ]


def test_enumerations_from_the_contract() -> None:
    assert [item.value for item in vocab.Sensitivity] == ["open", "protected", "restricted"]
    assert [item.value for item in vocab.AgeBand] == ["16_17", "18_plus"]
    assert [item.value for item in vocab.Visible] == ["yes", "unsure", "no"]
    assert [item.value for item in vocab.Stance] == ["supports", "neutral", "contradicts"]
    assert [item.value for item in vocab.Relation] == ["same_as", "part_of", "related"]
    assert [item.value for item in vocab.Outcome] == ["supports", "inconclusive", "contradicts"]
    assert [item.value for item in vocab.SourceAccess] == ["bulk", "live", "deeplink"]
    assert [item.value for item in vocab.SourceReuse] == [
        "open",
        "share_alike",
        "non_commercial",
        "link_only",
    ]
    assert [item.value for item in vocab.Visibility] == ["public", "unlisted", "private"]
    assert [item.value for item in vocab.InvestigationRole] == ["owner", "editor", "viewer"]
    assert [item.value for item in vocab.InvestigationItemKind] == [
        "finding",
        "record",
        "view",
        "note",
        "reference",
        "profile",
    ]
    assert [item.value for item in vocab.SurveyResult] == ["nothing", "marked", "skipped"]
    assert [item.value for item in vocab.ReportStatus] == ["open", "upheld", "dismissed"]
    assert [item.value for item in vocab.ActivityKind] == [
        "finding_created",
        "tier_changed",
        "state_changed",
        "observation_added",
        "evidence_added",
        "comment_added",
        "mention_added",
        "followup_logged",
        "investigation_published",
        # A notification only: see services.activity.notify_invitation.
        "investigation_invitation",
        "shape_extended",
    ]
    assert [item.value for item in vocab.NextStepCode] == [
        "need_observers",
        "need_strand",
        "need_class_agreement",
        "need_check",
        "need_trusted_review",
        "need_ground",
        "need_official",
        "look_at_new_part",
    ]
    assert [item.value for item in vocab.Nation] == ["england", "scotland", "wales", "northern_ireland"]


def test_field_visit_notices_cover_the_essentials_in_every_nation() -> None:
    for nation, lines in vocab.FIELD_VISIT_NOTICES.items():
        text = " ".join(lines).lower()
        assert len(lines) >= 4, nation
        assert "not permission to visit" in text, nation
        assert "metal detector" in text, nation
        assert "scheduled monument" in text, nation
        assert "protected place" in text, nation
        assert "dig" in text, nation
        assert "report" in text, nation
        for line in lines:
            # Short plain sentences: no line runs past two of them.
            assert line.endswith("."), line
            assert line.count(". ") <= 1, line
            assert all(len(sentence) <= 150 for sentence in line.split(". ")), line


def _notice(nation: vocab.Nation) -> str:
    return " ".join(vocab.FIELD_VISIT_NOTICES[nation])


def test_england_notices_follow_the_1979_act_and_the_treasure_act() -> None:
    text = _notice(vocab.Nation.ENGLAND)
    assert "Historic England" in text
    assert "Portable Antiquities Scheme" in text
    assert "coroner within 14 days" in text
    assert "open access land" in text


def test_wales_notices_follow_the_2023_act_not_the_1979_act() -> None:
    # Spike platform-duties-and-age: the Historic Environment (Wales) Act 2023
    # replaced the 1979 Act in Wales on 4 November 2024. Consent comes from the
    # Welsh Ministers, applied for through Cadw.
    text = _notice(vocab.Nation.WALES)
    assert "Historic Environment (Wales) Act 2023" in text
    assert "Welsh Ministers" in text
    assert "Cadw" in text
    assert "1979" not in text
    assert "Historic England" not in text
    assert "coroner within 14 days" in text


def test_scotland_notices_follow_the_access_code_and_treasure_trove() -> None:
    text = _notice(vocab.Nation.SCOTLAND)
    assert "Scottish Outdoor Access Code" in text
    assert "Historic Environment Scotland" in text
    assert "Treasure Trove" in text
    assert "coroner" not in text


def test_northern_ireland_notices_follow_the_1995_order() -> None:
    # Art.29 makes it an offence to have a detector with you in a protected
    # place, not only to use one. Art.41 needs a licence to dig for objects.
    text = _notice(vocab.Nation.NORTHERN_IRELAND)
    assert "Department for Communities" in text
    assert "with you" in text
    assert "licence" in text
    assert "within 14 days" in text


def test_16_and_17_year_olds_are_told_to_go_with_an_adult() -> None:
    assert "adult" in vocab.FIELD_VISIT_NOTICE_16_17
    assert vocab.FIELD_VISIT_NOTICE_16_17.endswith(".")


def test_protected_classes_are_the_ones_in_decision_0005() -> None:
    assert {cls.value for cls in vocab.PROTECTED_CLASSES} == {
        "round_barrow",
        "long_barrow",
        "ritual",
        "settlement",
    }


def test_age_bands_and_their_youngest_age() -> None:
    assert vocab.AGE_BAND_YOUNGEST == {vocab.AgeBand.AGE_16_17: 16, vocab.AgeBand.AGE_18_PLUS: 18}


def test_trusted_roles_see_exact_locations_and_approve_photos() -> None:
    expected = {"trusted", "expert", "moderator", "admin"}
    assert {role.value for role in vocab.TRUSTED_ROLES} == expected
    assert vocab.EXACT_LOCATION_ROLES == vocab.TRUSTED_ROLES
    assert vocab.MEDIA_APPROVER_ROLES == vocab.TRUSTED_ROLES


def test_source_reuse_and_access_meanings() -> None:
    # Decision 0004: what the licence allows. Decision 0007: how we may hold it.
    assert "non-commercial" in (vocab.SourceReuse.__doc__ or "")
    assert "never stored" in (vocab.SourceAccess.__doc__ or "")


AMERICAN_SPELLINGS = re.compile(
    r"\b(color|artifact|recognized|organization|center|gray|plow|meter)s?\b", re.IGNORECASE
)


def test_copy_is_british_english() -> None:
    words: list[str] = []
    for table in (
        vocab.ROLES,
        vocab.FEATURE_CLASSES,
        vocab.PERIODS,
        vocab.EVIDENCE_KINDS,
        vocab.CHECKS,
        vocab.EXPLANATIONS,
        vocab.TIERS,
        vocab.STATES,
        vocab.MENTION_KINDS,
        vocab.RECORD_CATEGORIES,
    ):
        for row in table:
            words.extend(value for value in vars(row).values() if isinstance(value, str) and " " in value)
    for lines in vocab.FIELD_VISIT_NOTICES.values():
        words.extend(lines)
    words.append(vocab.FIELD_VISIT_NOTICE_16_17)
    words.append(vocab.SENSITIVITY_NOTICE)
    assert len(words) > 80
    offenders = [text for text in words if AMERICAN_SPELLINGS.search(text)]
    assert offenders == []
