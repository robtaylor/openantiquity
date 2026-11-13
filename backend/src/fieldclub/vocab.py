"""Vocabularies: every enumeration the product uses, with the words shown to people.

Enumerations are `StrEnum` classes and are stored as `TEXT`. The descriptive
tables below (`FEATURE_CLASSES`, `PERIODS` and so on) are what `/meta` serves,
so the frontend hard-codes none of this. Copy is British English, and hints are
written for someone who has never heard the term before.

Monument-type terms are preferred labels in the FISH Thesaurus of Monument
Types (http://purl.org/heritagedata/schemes/eh_tmt2), checked in November 2026.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------


class Role(StrEnum):
    MEMBER = "member"
    TRUSTED = "trusted"
    EXPERT = "expert"
    MODERATOR = "moderator"
    ADMIN = "admin"


@dataclass(frozen=True)
class RoleInfo:
    id: Role
    label: str
    weight: float
    description: str


# A person's weight in the confidence engine. Every contributor is a signed-in
# account, so there is no lower weight for anonymous input. Moderators and
# admins count as trusted.
ROLES: tuple[RoleInfo, ...] = (
    RoleInfo(Role.MEMBER, "Member", 1.0, "Someone who has signed in."),
    RoleInfo(Role.TRUSTED, "Trusted member", 1.5, "A member whose contributions have earned fifty points."),
    RoleInfo(Role.EXPERT, "Archaeologist", 3.0, "A recognised archaeologist or records officer."),
    RoleInfo(Role.MODERATOR, "Moderator", 1.5, "Looks after reports and protected locations."),
    RoleInfo(Role.ADMIN, "Admin", 1.5, "Runs the service."),
)

ROLE_WEIGHTS: dict[Role, float] = {info.id: info.weight for info in ROLES}

# Trusted members and everyone above them. Moderators and admins count as
# trusted, and so do experts. On top of what a member may do, they download a
# protected finding's exact place (`services.sensitivity.downloads_exact`),
# protect a finding someone else found (`services.sensitivity.MAY_RAISE_ROLES`),
# approve photos (`MEDIA_APPROVER_ROLES`), and their second looks count as an
# experienced review (`REVIEWER_ROLES`). On a finding's page they see what a
# member sees.
TRUSTED_ROLES: frozenset[Role] = frozenset({Role.TRUSTED, Role.EXPERT, Role.MODERATOR, Role.ADMIN})

# Roles that may approve an uploaded photo so other people can see it
# (Decision 0009). See `services.media`.
MEDIA_APPROVER_ROLES: frozenset[Role] = TRUSTED_ROLES

# Roles whose "yes" counts as an experienced review for the Probable tier. The
# contract asks for "a trusted or expert reviewer" and also says "Moderators
# and admins count as trusted", so they are reviewers too, at the trusted
# weight of 1.5.
REVIEWER_ROLES: frozenset[Role] = TRUSTED_ROLES

# Roles that can moderate content.
MODERATOR_ROLES: frozenset[Role] = frozenset({Role.MODERATOR, Role.ADMIN})


def role_weight(role: Role | str) -> float:
    """The confidence weight for a role. An unknown role is a bug, so it raises."""
    return ROLE_WEIGHTS[Role(role)]


class AgeBand(StrEnum):
    """The age band a contributor declares on the welcome sheet (Decision 0009)."""

    AGE_16_17 = "16_17"
    AGE_18_PLUS = "18_plus"


# The youngest age in each band. A band is offered only when this is at least
# `FIELDCLUB_MIN_AGE`.
AGE_BAND_YOUNGEST: dict[AgeBand, int] = {AgeBand.AGE_16_17: 16, AgeBand.AGE_18_PLUS: 18}


class SignInProvider(StrEnum):
    GOOGLE = "google"
    APPLE = "apple"
    MICROSOFT = "microsoft"
    FACEBOOK = "facebook"
    OSM = "osm"
    EMAIL = "email"


@dataclass(frozen=True)
class SignInProviderInfo:
    id: SignInProvider
    label: str


# In the order the sign-in sheet shows them. The emailed link comes last,
# because it is the fallback for people who use none of the others.
SIGN_IN_PROVIDERS: tuple[SignInProviderInfo, ...] = (
    SignInProviderInfo(SignInProvider.GOOGLE, "Google"),
    SignInProviderInfo(SignInProvider.APPLE, "Apple"),
    SignInProviderInfo(SignInProvider.MICROSOFT, "Microsoft"),
    SignInProviderInfo(SignInProvider.FACEBOOK, "Facebook"),
    SignInProviderInfo(SignInProvider.OSM, "OpenStreetMap"),
    SignInProviderInfo(SignInProvider.EMAIL, "Email link"),
)


# --------------------------------------------------------------------------
# Feature classes
# --------------------------------------------------------------------------


class FeatureClass(StrEnum):
    ENCLOSURE = "enclosure"
    HILLFORT = "hillfort"
    ROUND_BARROW = "round_barrow"
    LONG_BARROW = "long_barrow"
    HUT_CIRCLE = "hut_circle"
    SETTLEMENT = "settlement"
    FIELD_SYSTEM = "field_system"
    RIDGE_AND_FURROW = "ridge_and_furrow"
    LINEAR = "linear"
    TRACKWAY = "trackway"
    ROAD = "road"
    MOAT = "moat"
    MOTTE = "motte"
    PLATFORM = "platform"
    POND = "pond"
    PIT = "pit"
    INDUSTRIAL = "industrial"
    MILITARY = "military"
    RITUAL = "ritual"
    GARDEN = "garden"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FeatureClassInfo:
    id: FeatureClass
    label: str
    hint: str
    fish_term: str


FEATURE_CLASSES: tuple[FeatureClassInfo, ...] = (
    FeatureClassInfo(
        FeatureClass.ENCLOSURE,
        "Enclosure",
        "A patch of ground with a bank, a ditch or both running round it.",
        "ENCLOSURE",
    ),
    FeatureClassInfo(
        FeatureClass.HILLFORT,
        "Hillfort",
        "A hilltop ringed by one or more big banks and ditches, usually Iron Age.",
        "HILLFORT",
    ),
    FeatureClassInfo(
        FeatureClass.ROUND_BARROW,
        "Round barrow or mound",
        "A round burial mound, often with a ditch circling it, usually Bronze Age.",
        "ROUND BARROW",
    ),
    FeatureClassInfo(
        FeatureClass.LONG_BARROW,
        "Long barrow",
        "A long, low burial mound from the Neolithic, often with a ditch down each side.",
        "LONG BARROW",
    ),
    FeatureClassInfo(
        FeatureClass.HUT_CIRCLE,
        "Hut circle",
        "A low ring a few metres across, left by the wall of a prehistoric round house.",
        "HUT CIRCLE",
    ),
    FeatureClassInfo(
        FeatureClass.SETTLEMENT,
        "Settlement earthworks",
        "The bumps and hollows left by the houses, yards and lanes of an abandoned village or farm.",
        "SETTLEMENT",
    ),
    FeatureClassInfo(
        FeatureClass.FIELD_SYSTEM,
        "Field system",
        "A pattern of old field edges, seen as low banks, ditches or steps in a slope.",
        "FIELD SYSTEM",
    ),
    FeatureClassInfo(
        FeatureClass.RIDGE_AND_FURROW,
        "Ridge and furrow",
        "Long parallel ridges, like corduroy, left by medieval and later ploughing.",
        "RIDGE AND FURROW",
    ),
    FeatureClassInfo(
        FeatureClass.LINEAR,
        "Linear bank or ditch",
        "A single bank or ditch running across country, such as an old boundary.",
        "LINEAR EARTHWORK",
    ),
    FeatureClassInfo(
        FeatureClass.TRACKWAY,
        "Trackway or hollow way",
        "An old route worn into the ground by feet, hooves and wheels, often a sunken lane.",
        "TRACKWAY",
    ),
    FeatureClassInfo(
        FeatureClass.ROAD,
        "Road",
        "A built road, often straight and raised on a bank, such as a Roman road.",
        "ROAD",
    ),
    FeatureClassInfo(
        FeatureClass.MOAT,
        "Moat",
        "A wide ditch, once full of water, round the island where a house stood.",
        "MOAT",
    ),
    FeatureClassInfo(
        FeatureClass.MOTTE,
        "Motte or castle earthwork",
        "A steep man-made mound or ring of bank built for an early castle.",
        "MOTTE",
    ),
    FeatureClassInfo(
        FeatureClass.PLATFORM,
        "Platform",
        "A levelled patch cut into a slope or built out from it, where a building once stood.",
        "BUILDING PLATFORM",
    ),
    FeatureClassInfo(
        FeatureClass.POND,
        "Pond or water management",
        "Ponds, dams and channels made to hold or move water, such as fishponds and water meadows.",
        "POND",
    ),
    FeatureClassInfo(
        FeatureClass.PIT,
        "Pit or quarry",
        "A hollow or cluster of hollows left by digging for stone, chalk, clay or ore.",
        "EXTRACTIVE PIT",
    ),
    FeatureClassInfo(
        FeatureClass.INDUSTRIAL,
        "Industrial",
        "Remains of industry, such as spoil heaps, kilns, tramways and mine workings.",
        "INDUSTRIAL SITE",
    ),
    FeatureClassInfo(
        FeatureClass.MILITARY,
        "Military",
        "Remains of defence or training, such as trenches, gun positions and airfields.",
        "MILITARY INSTALLATION",
    ),
    FeatureClassInfo(
        FeatureClass.RITUAL,
        "Ritual monument",
        "A prehistoric ceremonial site, such as a henge, a stone circle or a cursus.",
        "RELIGIOUS RITUAL AND FUNERARY",
    ),
    FeatureClassInfo(
        FeatureClass.GARDEN,
        "Garden earthworks",
        "Terraces, mounds, ponds and paths left by a formal garden that has gone.",
        "GARDEN",
    ),
    FeatureClassInfo(
        FeatureClass.UNKNOWN,
        "Not sure",
        "You can see something but can't say what it is. Other people can help work it out.",
        "SITE",
    ),
)


def stored_class(value: str) -> FeatureClass:
    """What a stored feature class is to this version: itself, or `unknown` for one it has no name for.

    A later version serving beside this one during a deploy, or one this
    version was gone back from, can have stored a class it added. Every
    reader of a stored class goes through here, so such a finding is shown,
    listed, assessed and downloaded as "Not sure" and never answers 500. The
    stored value is left as it is (Decision 0035).
    """
    try:
        return FeatureClass(value)
    except ValueError:
        return FeatureClass.UNKNOWN


# --------------------------------------------------------------------------
# Periods
# --------------------------------------------------------------------------


class Period(StrEnum):
    PREHISTORIC = "prehistoric"
    NEOLITHIC = "neolithic"
    BRONZE_AGE = "bronze_age"
    IRON_AGE = "iron_age"
    ROMAN = "roman"
    EARLY_MEDIEVAL = "early_medieval"
    MEDIEVAL = "medieval"
    POST_MEDIEVAL = "post_medieval"
    MODERN = "modern"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PeriodInfo:
    id: Period
    label: str
    hint: str


PERIODS: tuple[PeriodInfo, ...] = (
    PeriodInfo(Period.PREHISTORIC, "Prehistoric", "Before AD 43, when you can't say which part"),
    PeriodInfo(Period.NEOLITHIC, "Neolithic", "4000 to 2500 BC"),
    PeriodInfo(Period.BRONZE_AGE, "Bronze Age", "2500 to 800 BC"),
    PeriodInfo(Period.IRON_AGE, "Iron Age", "800 BC to AD 43"),
    PeriodInfo(Period.ROMAN, "Roman", "AD 43 to 410"),
    PeriodInfo(Period.EARLY_MEDIEVAL, "Early medieval", "AD 410 to 1066"),
    PeriodInfo(Period.MEDIEVAL, "Medieval", "1066 to 1540"),
    PeriodInfo(Period.POST_MEDIEVAL, "Post-medieval", "1540 to 1901"),
    PeriodInfo(Period.MODERN, "Modern", "1901 to today"),
    PeriodInfo(Period.UNKNOWN, "Not sure", "No guess at a date"),
)


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------


class Strand(StrEnum):
    LIDAR = "lidar"
    AERIAL = "aerial"
    HISTORIC_MAP = "historic_map"
    RECORDS = "records"
    LITERATURE = "literature"
    GROUND = "ground"
    SURVEY = "survey"
    OFFICIAL = "official"


class EvidenceGroup(StrEnum):
    DESK = "desk"
    FIELD = "field"
    OFFICIAL = "official"


# The strands that count towards the Corroborated tier.
DESK_STRANDS: frozenset[Strand] = frozenset(
    {Strand.LIDAR, Strand.AERIAL, Strand.HISTORIC_MAP, Strand.RECORDS, Strand.LITERATURE}
)


class EvidenceKind(StrEnum):
    LIDAR_VIEW = "lidar_view"
    AERIAL = "aerial"
    HISTORIC_MAP = "historic_map"
    RECORD_LINK = "record_link"
    DOCUMENT = "document"
    PHOTO = "photo"
    FIELD_VISIT = "field_visit"
    GEOPHYSICS = "geophysics"
    EXCAVATION = "excavation"
    HER_RECORD = "her_record"
    DESIGNATION = "designation"
    PUBLICATION = "publication"


@dataclass(frozen=True)
class EvidenceKindInfo:
    id: EvidenceKind
    label: str
    strand: Strand
    group: EvidenceGroup
    hint: str


EVIDENCE_KINDS: tuple[EvidenceKindInfo, ...] = (
    EvidenceKindInfo(
        EvidenceKind.LIDAR_VIEW,
        "LIDAR view",
        Strand.LIDAR,
        EvidenceGroup.DESK,
        "Another LIDAR view that shows it, in a different style or with the light from another side.",
    ),
    EvidenceKindInfo(
        EvidenceKind.AERIAL,
        "Aerial photo",
        Strand.AERIAL,
        EvidenceGroup.DESK,
        "An aerial or satellite photo that shows it, as a mark in a crop, in bare soil or in shadow.",
    ),
    EvidenceKindInfo(
        EvidenceKind.HISTORIC_MAP,
        "Old map",
        Strand.HISTORIC_MAP,
        EvidenceGroup.DESK,
        "An old map that draws or names it, such as a first edition Ordnance Survey sheet.",
    ),
    EvidenceKindInfo(
        EvidenceKind.RECORD_LINK,
        "Heritage record",
        Strand.RECORDS,
        EvidenceGroup.DESK,
        "A link to an existing record of the same site or one connected to it.",
    ),
    EvidenceKindInfo(
        EvidenceKind.DOCUMENT,
        "Book or report",
        Strand.LITERATURE,
        EvidenceGroup.DESK,
        "A book, article or report that mentions it.",
    ),
    EvidenceKindInfo(
        EvidenceKind.PHOTO,
        "Ground photo",
        Strand.GROUND,
        EvidenceGroup.FIELD,
        "A photograph taken standing at the site.",
    ),
    EvidenceKindInfo(
        EvidenceKind.FIELD_VISIT,
        "Site visit",
        Strand.GROUND,
        EvidenceGroup.FIELD,
        "Notes from someone who has been to look, with the landowner's permission.",
    ),
    EvidenceKindInfo(
        EvidenceKind.GEOPHYSICS,
        "Geophysical survey",
        Strand.SURVEY,
        EvidenceGroup.FIELD,
        "A survey that maps what lies under the surface without digging, such as magnetometry.",
    ),
    EvidenceKindInfo(
        EvidenceKind.EXCAVATION,
        "Excavation",
        Strand.SURVEY,
        EvidenceGroup.FIELD,
        "A dig by archaeologists that tested what's there.",
    ),
    EvidenceKindInfo(
        EvidenceKind.HER_RECORD,
        "HER entry",
        Strand.OFFICIAL,
        EvidenceGroup.OFFICIAL,
        "An entry in a Historic Environment Record, the local list of known sites.",
    ),
    EvidenceKindInfo(
        EvidenceKind.DESIGNATION,
        "Designation",
        Strand.OFFICIAL,
        EvidenceGroup.OFFICIAL,
        "Legal protection, such as being scheduled as an ancient monument.",
    ),
    EvidenceKindInfo(
        EvidenceKind.PUBLICATION,
        "Publication",
        Strand.OFFICIAL,
        EvidenceGroup.OFFICIAL,
        "A published account in a journal, a monograph or a report series.",
    ),
)

# The strand each kind is filed under, as `/meta` shows it. To decide what an
# evidence item counts towards, use `strand_for`, which also looks at the relation.
EVIDENCE_STRANDS: dict[EvidenceKind, Strand] = {info.id: info.strand for info in EVIDENCE_KINDS}


class Stance(StrEnum):
    SUPPORTS = "supports"
    NEUTRAL = "neutral"
    CONTRADICTS = "contradicts"


class Relation(StrEnum):
    SAME_AS = "same_as"
    PART_OF = "part_of"
    RELATED = "related"


# A record link counts towards the records strand only with one of these
# relations. `same_as` says the finding is the record, which drives the
# `known` state and is no corroboration of anything new.
RECORD_STRAND_RELATIONS: frozenset[Relation] = frozenset({Relation.RELATED, Relation.PART_OF})


def strand_for(kind: EvidenceKind | str, relation: Relation | str | None = None) -> Strand | None:
    """The strand an evidence item counts towards, or None when it counts towards none.

    Every kind has one strand, except that a `record_link` only counts for
    `records` when its relation is `related` or `part_of`.
    """
    kind = EvidenceKind(kind)
    if kind is EvidenceKind.RECORD_LINK and (
        relation is None or Relation(relation) not in RECORD_STRAND_RELATIONS
    ):
        return None
    return EVIDENCE_STRANDS[kind]


class Outcome(StrEnum):
    SUPPORTS = "supports"
    INCONCLUSIVE = "inconclusive"
    CONTRADICTS = "contradicts"


# --------------------------------------------------------------------------
# Observations
# --------------------------------------------------------------------------


class Visible(StrEnum):
    YES = "yes"
    UNSURE = "unsure"
    NO = "no"


class Check(StrEnum):
    NOT_MODERN = "not_modern"
    NOT_NATURAL = "not_natural"
    NOT_ARTEFACT = "not_artefact"


class Explanation(StrEnum):
    MODERN = "modern"
    NATURAL = "natural"
    ARTEFACT = "artefact"


@dataclass(frozen=True)
class CheckInfo:
    id: Check
    question: str
    hint: str
    explanation: Explanation


CHECKS: tuple[CheckInfo, ...] = (
    CheckInfo(
        Check.NOT_MODERN,
        "Could it be modern?",
        "Drains, pipelines, golf bunkers, vehicle tracks and recent field edges can all look old in LIDAR.",
        Explanation.MODERN,
    ),
    CheckInfo(
        Check.NOT_NATURAL,
        "Could it be natural?",
        "Old river channels, landslips, sinkholes and frost patterns make shapes that look built.",
        Explanation.NATURAL,
    ),
    CheckInfo(
        Check.NOT_ARTEFACT,
        "Could it be a fault in the data?",
        (
            "Stripes where survey flights overlap, steps at tile edges and blotches under trees come from "
            "processing, not from the ground."
        ),
        Explanation.ARTEFACT,
    ),
)

CHECK_EXPLANATIONS: dict[Check, Explanation] = {info.id: info.explanation for info in CHECKS}


@dataclass(frozen=True)
class ExplanationInfo:
    id: Explanation
    label: str
    hint: str


EXPLANATIONS: tuple[ExplanationInfo, ...] = (
    ExplanationInfo(
        Explanation.MODERN,
        "Modern feature",
        "Something recent, such as a drain, a pipeline, a bunker or a vehicle track.",
    ),
    ExplanationInfo(
        Explanation.NATURAL,
        "Natural feature",
        "Shaped by water, ice or geology, not by people.",
    ),
    ExplanationInfo(
        Explanation.ARTEFACT,
        "Data artefact",
        "A stripe, step or blotch that comes from how the LIDAR was flown or processed.",
    ),
)


# --------------------------------------------------------------------------
# The confidence ladder
# --------------------------------------------------------------------------


class Tier(StrEnum):
    SPOTTED = "spotted"
    SEEN = "seen"
    CORROBORATED = "corroborated"
    PROBABLE = "probable"
    GROUND_CHECKED = "ground_checked"
    CONFIRMED = "confirmed"


@dataclass(frozen=True)
class TierInfo:
    id: Tier
    label: str
    description: str
    base_score: int


TIERS: tuple[TierInfo, ...] = (
    TierInfo(Tier.SPOTTED, "Spotted", "One person has marked it.", 10),
    TierInfo(
        Tier.SEEN,
        "Seen by others",
        "At least two other people can see it too, and few can't.",
        30,
    ),
    TierInfo(
        Tier.CORROBORATED,
        "Corroborated",
        (
            "It shows up in two more kinds of evidence, such as an aerial photo and an old map, "
            "and people agree what it is."
        ),
        50,
    ),
    TierInfo(
        Tier.PROBABLE,
        "Probable",
        (
            "Reviewers have ruled out modern, natural and data-processing explanations, "
            "and an experienced reviewer or many other people can see it."
        ),
        70,
    ),
    TierInfo(
        Tier.GROUND_CHECKED,
        "Checked on the ground",
        "Someone has visited or surveyed it and what they found supports it.",
        85,
    ),
    TierInfo(
        Tier.CONFIRMED,
        "On record",
        "A Historic Environment Record, a designation or a publication now includes it.",
        100,
    ),
)

TIER_ORDER: tuple[Tier, ...] = tuple(info.id for info in TIERS)
TIER_BASE_SCORES: dict[Tier, int] = {info.id: info.base_score for info in TIERS}


def tier_rank(tier: Tier | str) -> int:
    """Position on the ladder, starting at 0 for Spotted."""
    return TIER_ORDER.index(Tier(tier))


class FindingState(StrEnum):
    OPEN = "open"
    KNOWN = "known"
    DISPUTED = "disputed"
    RULED_OUT = "ruled_out"
    WITHDRAWN = "withdrawn"


@dataclass(frozen=True)
class StateInfo:
    id: FindingState
    label: str
    description: str


STATES: tuple[StateInfo, ...] = (
    StateInfo(FindingState.OPEN, "Open", "Still being looked at."),
    StateInfo(
        FindingState.KNOWN,
        "Matches a known record",
        "It's the same thing as an existing heritage record, which is linked from the finding.",
    ),
    StateInfo(FindingState.DISPUTED, "Disputed", "People or evidence disagree about it."),
    StateInfo(
        FindingState.RULED_OUT,
        "Explained",
        "Most people can't see it, or it turned out to be modern, natural or a fault in the data.",
    ),
    StateInfo(FindingState.WITHDRAWN, "Withdrawn", "The finder took it back."),
)


class StateReason(StrEnum):
    """Why a finding was ruled out. The middle three match `Explanation`."""

    NOT_VISIBLE = "not_visible"
    MODERN = "modern"
    NATURAL = "natural"
    ARTEFACT = "artefact"
    GROUND_CHECK = "ground_check"


class NextStepCode(StrEnum):
    NEED_OBSERVERS = "need_observers"
    NEED_STRAND = "need_strand"
    NEED_CLASS_AGREEMENT = "need_class_agreement"
    NEED_CHECK = "need_check"
    NEED_TRUSTED_REVIEW = "need_trusted_review"
    NEED_GROUND = "need_ground"
    NEED_OFFICIAL = "need_official"
    # Not a requirement of any tier: second looks at what an extension added
    # to a line since the last one (`confidence.NEW_PART_LOOK_M`).
    LOOK_AT_NEW_PART = "look_at_new_part"


@dataclass(frozen=True)
class NextStepInfo:
    """A next step as the help-wanted lists name it: the work it asks of someone, in a line."""

    id: NextStepCode
    label: str
    description: str


NEXT_STEPS: tuple[NextStepInfo, ...] = (
    NextStepInfo(
        NextStepCode.NEED_OBSERVERS,
        "Second looks",
        "Look at it as the finder did and say whether you can see it too.",
    ),
    NextStepInfo(
        NextStepCode.NEED_STRAND,
        "Another kind of evidence",
        "Check old maps, aerial photos, heritage records and reports for it.",
    ),
    NextStepInfo(
        NextStepCode.NEED_CLASS_AGREEMENT,
        "Say what it is",
        "Look at it and say what kind of feature you think it is.",
    ),
    NextStepInfo(
        NextStepCode.NEED_CHECK,
        "Rule out the everyday",
        "Say whether it could be something modern, something natural or a quirk of the data.",
    ),
    NextStepInfo(
        NextStepCode.NEED_TRUSTED_REVIEW,
        "An experienced eye",
        "A trusted member or an archaeologist looks at it and says whether they see it.",
    ),
    NextStepInfo(
        NextStepCode.NEED_GROUND,
        "Look on the ground",
        "Visit it with the landowner's permission, or survey it, and say what you found.",
    ),
    NextStepInfo(
        NextStepCode.NEED_OFFICIAL,
        "Find it on record",
        "Find a heritage record, designation or publication that includes it, for an archaeologist to check.",
    ),
    NextStepInfo(
        NextStepCode.LOOK_AT_NEW_PART,
        "Look at the new part",
        "Look at what was added to a line since the last second look and say whether you can see it.",
    ),
)


class Sensitivity(StrEnum):
    """How much of a finding's position each viewer sees (Decision 0005, Decision 0032).

    In order from least to most protected. `services.sensitivity` decides who
    sees what.
    """

    OPEN = "open"
    PROTECTED = "protected"


SENSITIVITY_ORDER: tuple[Sensitivity, ...] = tuple(Sensitivity)


def sensitivity_rank(level: Sensitivity | str) -> int:
    """Position in `SENSITIVITY_ORDER`, starting at 0 for open."""
    return SENSITIVITY_ORDER.index(Sensitivity(level))


# Classes that suggest burials, rich occupation or ritual use. A new finding
# of one of these is `protected`.
PROTECTED_CLASSES: frozenset[FeatureClass] = frozenset(
    {FeatureClass.ROUND_BARROW, FeatureClass.LONG_BARROW, FeatureClass.RITUAL, FeatureClass.SETTLEMENT}
)


class SensitivityViewer(StrEnum):
    """The kinds of viewer the sensitivity rules tell apart. Admins count as moderators.

    A finding's page tells apart only the signed-out visitor. A download also
    tells the finder and the trusted roles from a member.
    """

    SIGNED_OUT = "signed_out"
    MEMBER = "member"
    FINDER = "finder"
    TRUSTED = "trusted"
    EXPERT = "expert"
    MODERATOR = "moderator"


@dataclass(frozen=True)
class SensitivityInfo:
    id: Sensitivity
    label: str
    # Who sees the exact place, and who sees the square, in one or two sentences, and a third
    # when a download gives the exact place to fewer people than the page does.
    who_sees: str
    # What someone shown only the square is told: why, and what would change it. None for open.
    square_sentence: str | None
    # The viewers who see the exact place. `tests/services/test_sensitivity_words.py`
    # holds each to `services.sensitivity.sees_exact`.
    exact_for: frozenset[SensitivityViewer]


# Downloads are stricter than the page (Decision 0005, rule 8: `sensitivity.downloads_exact`). This is
# what a trusted member or an archaeologist sees of a protected finding that a member doesn't.
_FEW_DOWNLOAD_IT = (
    "Downloads give its exact place only to its finder, trusted members, archaeologists and moderators."
)

SENSITIVITY_LEVELS: tuple[SensitivityInfo, ...] = (
    SensitivityInfo(
        Sensitivity.OPEN, "Open", "Everyone sees its exact place.", None, frozenset(SensitivityViewer)
    ),
    SensitivityInfo(
        Sensitivity.PROTECTED,
        "Protected",
        "Only people who have signed in see its exact place. Everyone else sees its one-kilometre square. "
        + _FEW_DOWNLOAD_IT,
        "Sites like this can attract illegal metal detecting, so its exact place is kept back. "
        "Sign in to see it.",
        frozenset(SensitivityViewer) - {SensitivityViewer.SIGNED_OUT},
    ),
)


# --------------------------------------------------------------------------
# Mentions
# --------------------------------------------------------------------------


class MentionKind(StrEnum):
    VIDEO = "video"
    ARTICLE = "article"
    PODCAST = "podcast"
    PAPER = "paper"
    BROADCAST = "broadcast"
    SOCIAL = "social"


@dataclass(frozen=True)
class MentionKindInfo:
    id: MentionKind
    label: str


MENTION_KINDS: tuple[MentionKindInfo, ...] = (
    MentionKindInfo(MentionKind.VIDEO, "Video"),
    MentionKindInfo(MentionKind.ARTICLE, "Article"),
    MentionKindInfo(MentionKind.PODCAST, "Podcast"),
    MentionKindInfo(MentionKind.PAPER, "Paper"),
    MentionKindInfo(MentionKind.BROADCAST, "Broadcast"),
    MentionKindInfo(MentionKind.SOCIAL, "Social post"),
)


# --------------------------------------------------------------------------
# Records and sources
# --------------------------------------------------------------------------


class RecordCategory(StrEnum):
    DESIGNATION = "designation"
    MONUMENT = "monument"
    FIND = "find"
    EVENT = "event"
    DOCUMENT = "document"
    COMMUNITY = "community"
    MAP_LABEL = "map_label"


@dataclass(frozen=True)
class RecordCategoryInfo:
    id: RecordCategory
    label: str
    colour: str


# Records are drawn as squares, so they never rely on colour to differ from
# findings, but a square's colour mustn't read as a finding's tier or state
# either. So the colours keep apart, by CIEDE2000, from every colour token of
# docs/UI.md (the tiers, the states, good, warn, bad, info, the accent and the
# text colours) by at least 21, from each other by at least 21, and from every
# grey of the terrain by at least 23, and each has at least 3:1 contrast with
# the dark chrome (`--bg`), as UI.md asks of what isn't text. The earlier set
# reused `--bad`, `--info` and `--good` outright. `tests/test_vocab.py` checks
# the distances.
RECORD_CATEGORIES: tuple[RecordCategoryInfo, ...] = (
    RecordCategoryInfo(RecordCategory.DESIGNATION, "Designations", "#ff2f99"),
    RecordCategoryInfo(RecordCategory.MONUMENT, "Monument records", "#2ae3e4"),
    RecordCategoryInfo(RecordCategory.FIND, "Finds", "#aeff00"),
    RecordCategoryInfo(RecordCategory.EVENT, "Fieldwork", "#3557e6"),
    RecordCategoryInfo(RecordCategory.DOCUMENT, "Reports and publications", "#ffb3e6"),
    RecordCategoryInfo(RecordCategory.COMMUNITY, "Community data", "#18ffae"),
    RecordCategoryInfo(RecordCategory.MAP_LABEL, "Antiquities on old maps", "#c400ff"),
)


# Record types that say where a source has looked rather than what it found. Such a record's polygon
# covers thousands of square kilometres, so every position inside it is 0 m from it, and it would crowd
# real records out of "near here" and "is this already recorded?". It stays in search and on the map.
MAPPING_PROJECT_AREA = "Mapping project area"
COVERAGE_RECORD_TYPES: frozenset[str] = frozenset({MAPPING_PROJECT_AREA})


class SourceAccess(StrEnum):
    """How OpenAntiquity may hold a source's data, per Decision 0007.

    A `bulk` source is downloaded and stored in `records`. A `live` source is
    queried by the browser and never stored on our servers. A `deeplink`
    source is only linked. A finding linked to a live or deep-link record
    keeps the record's identifier and address and nothing else.
    """

    BULK = "bulk"
    LIVE = "live"
    DEEPLINK = "deeplink"


class SourceReuse(StrEnum):
    """What a source's licence allows, per Decision 0004.

    `non_commercial` sources may be ingested because the service is
    non-commercial. A `link_only` source is deep-linked and never copied.
    """

    OPEN = "open"
    SHARE_ALIKE = "share_alike"
    NON_COMMERCIAL = "non_commercial"
    LINK_ONLY = "link_only"


class IngestStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AdminAreaKind(StrEnum):
    NATION = "nation"
    COUNTY = "county"


class Nation(StrEnum):
    ENGLAND = "england"
    SCOTLAND = "scotland"
    WALES = "wales"
    NORTHERN_IRELAND = "northern_ireland"


# --------------------------------------------------------------------------
# Collaboration
# --------------------------------------------------------------------------


class Visibility(StrEnum):
    PUBLIC = "public"
    UNLISTED = "unlisted"
    PRIVATE = "private"


class InvestigationRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class InvestigationItemKind(StrEnum):
    FINDING = "finding"
    RECORD = "record"
    VIEW = "view"
    NOTE = "note"
    REFERENCE = "reference"
    PROFILE = "profile"


class SurveyResult(StrEnum):
    NOTHING = "nothing"
    MARKED = "marked"
    SKIPPED = "skipped"


class ReportStatus(StrEnum):
    OPEN = "open"
    UPHELD = "upheld"
    DISMISSED = "dismissed"


class ReportTarget(StrEnum):
    """What a report, or a moderator's action, can be about. See `services.moderation`."""

    FINDING = "finding"
    COMMENT = "comment"
    EVIDENCE = "evidence"
    MENTION = "mention"
    PHOTO = "photo"
    USER = "user"
    INVESTIGATION = "investigation"


class ReportReason(StrEnum):
    LOCATION_RISK = "location_risk"
    ILLEGAL = "illegal"
    INTIMATE_IMAGE = "intimate_image"
    PRIVACY = "privacy"
    DEFAMATION = "defamation"
    ABUSE = "abuse"
    UNDER_AGE = "under_age"
    SPAM = "spam"
    MISLEADING = "misleading"
    OTHER = "other"


@dataclass(frozen=True)
class ReportReasonInfo:
    id: ReportReason
    label: str
    hint: str
    # Hours within which a report for this reason must be dealt with, or None
    # when the law sets no time. See the platform-duties spike.
    due_hours: int | None = None


# What the report button offers. The two with a deadline follow the law the
# research read: the Online Safety Act s.10(3A) takes down a reported intimate
# image within 48 hours, and the Defamation (Operators of Websites)
# Regulations 2013 give an operator 48 hours to act on a notice of complaint.
REPORT_REASONS: tuple[ReportReasonInfo, ...] = (
    ReportReasonInfo(
        ReportReason.LOCATION_RISK,
        "Puts a site at risk",
        "It could lead someone to damage a site or dig or detect there.",
    ),
    ReportReasonInfo(
        ReportReason.ILLEGAL,
        "Illegal",
        "It encourages a crime, such as metal detecting on a scheduled monument.",
    ),
    ReportReasonInfo(
        ReportReason.INTIMATE_IMAGE,
        "Intimate image",
        "A sexual or intimate image of someone shared without their consent.",
        due_hours=48,
    ),
    ReportReasonInfo(
        ReportReason.PRIVACY,
        "Reveals personal details",
        "It identifies a person, a home or a private garden, or says who owns the land.",
    ),
    ReportReasonInfo(
        ReportReason.DEFAMATION,
        "Untrue about a person",
        "It says something untrue that harms a person's or an organisation's reputation.",
        due_hours=48,
    ),
    ReportReasonInfo(
        ReportReason.ABUSE,
        "Abusive",
        "Harassment, threats, hate or bullying of anyone.",
    ),
    ReportReasonInfo(
        ReportReason.UNDER_AGE,
        "Under 16",
        "The person behind this account seems to be younger than 16.",
    ),
    ReportReasonInfo(
        ReportReason.SPAM, "Spam", "Advertising, or posts that have nothing to do with the map."
    ),
    ReportReasonInfo(
        ReportReason.MISLEADING,
        "Deliberately false",
        "Made up on purpose, such as a fake finding or a doctored picture.",
    ),
    ReportReasonInfo(ReportReason.OTHER, "Something else", "Tell the moderators what is wrong in the note."),
)

REPORT_DUE_HOURS: dict[ReportReason, int] = {
    info.id: info.due_hours for info in REPORT_REASONS if info.due_hours is not None
}


class ModerationActionKind(StrEnum):
    """What a moderator, or a trusted member approving photos, did. One row each in `moderation_actions`."""

    HIDE = "hide"
    UNHIDE = "unhide"
    RESOLVE_REPORT = "resolve_report"
    CHANGE_ROLE = "change_role"
    BAN = "ban"
    UNBAN = "unban"
    CHANGE_SENSITIVITY = "change_sensitivity"
    APPROVE_PHOTO = "approve_photo"
    REJECT_PHOTO = "reject_photo"


class PointKind(StrEnum):
    """A tapped point of a finding's path. A segment between two corners is straight."""

    CORNER = "corner"
    SMOOTH = "smooth"


class ShapeKind(StrEnum):
    """What a finding's shape is: an open line or a closed area."""

    LINE = "line"
    AREA = "area"


class ShapeChangeKind(StrEnum):
    """How a change to a finding's path changed it (`services.shapes.classify_change`)."""

    DRAWN = "drawn"
    EXTENDED = "extended"
    RESHAPED = "reshaped"
    CLOSED = "closed"
    OPENED = "opened"
    REMOVED = "removed"


class ActivityKind(StrEnum):
    FINDING_CREATED = "finding_created"
    TIER_CHANGED = "tier_changed"
    STATE_CHANGED = "state_changed"
    OBSERVATION_ADDED = "observation_added"
    EVIDENCE_ADDED = "evidence_added"
    COMMENT_ADDED = "comment_added"
    MENTION_ADDED = "mention_added"
    FOLLOWUP_LOGGED = "followup_logged"
    INVESTIGATION_PUBLISHED = "investigation_published"
    # A notification only, never an `activity` row: someone was invited to an investigation.
    INVESTIGATION_INVITATION = "investigation_invitation"
    # The finder added to an end of the finding's line. Listed only to those who see it exactly.
    SHAPE_EXTENDED = "shape_extended"


# --------------------------------------------------------------------------
# Notices
# --------------------------------------------------------------------------

_NOT_PERMISSION = "A marker on this map is not permission to visit."
_NEVER_DIG = "Look, photograph and take notes. Never dig, and don't take anything away."
_ASK_LANDOWNER = "Get the landowner's permission before you leave a public right of way or open access land."
_NO_DETECTING_ON_ACCESS_LAND = "The right to roam on open access land doesn't cover metal detecting."
_DAMAGE = "Damaging a scheduled monument, or working on one without consent, is also a crime."
_TREASURE = "Possible treasure must be reported to the coroner within 14 days."

# Shown before someone logs a site visit. The law differs between the nations.
# Checked on 2026-11-10 against the legislation recorded in
# docs/architecture/decisions/spikes/platform-duties-and-age.md: the Ancient
# Monuments and Archaeological Areas Act 1979 (England and Scotland), the
# Historic Environment (Wales) Act 2023, the Historic Monuments and
# Archaeological Objects (NI) Order 1995, the Countryside and Rights of Way
# Act 2000, the Land Reform (Scotland) Act 2003 and the Treasure Act 1996.
FIELD_VISIT_NOTICES: dict[Nation, tuple[str, ...]] = {
    Nation.ENGLAND: (
        _NOT_PERMISSION,
        _ASK_LANDOWNER,
        _NEVER_DIG,
        (
            "Using a metal detector on a scheduled monument or other protected place without written "
            "consent from Historic England is a crime."
        ),
        _NO_DETECTING_ON_ACCESS_LAND,
        _DAMAGE,
        f"Report anything you find to the Portable Antiquities Scheme. {_TREASURE}",
    ),
    Nation.SCOTLAND: (
        _NOT_PERMISSION,
        "You have a right of responsible access to most land. Follow the Scottish Outdoor Access Code.",
        _NEVER_DIG,
        (
            "Using a metal detector on a scheduled monument or other protected place without consent "
            "from Historic Environment Scotland is a crime."
        ),
        "Access rights don't cover metal detecting. Always ask the landowner first.",
        "Every archaeological object you find, whatever it's made of, must be reported to Treasure Trove.",
    ),
    Nation.WALES: (
        _NOT_PERMISSION,
        _ASK_LANDOWNER,
        _NEVER_DIG,
        (
            "Under the Historic Environment (Wales) Act 2023, using a metal detector in a protected place "
            "without consent is a crime."
        ),
        (
            "Scheduled monuments are protected places. Consent comes from the Welsh Ministers through Cadw, "
            "and is rarely given."
        ),
        _NO_DETECTING_ON_ACCESS_LAND,
        _DAMAGE,
        f"Report anything you find to the Portable Antiquities Scheme in Wales. {_TREASURE}",
        "To report heritage crime, call 101 and quote Op Heritage Cymru, or 999 if it's happening now.",
    ),
    Nation.NORTHERN_IRELAND: (
        _NOT_PERMISSION,
        "Get the landowner's permission before you go onto private land.",
        _NEVER_DIG,
        (
            "Digging to search for archaeological objects needs a licence from the Department for "
            "Communities, even if you don't remove the surface."
        ),
        (
            "Having a metal detector with you in a protected place, such as a scheduled monument, without "
            "the Department's consent is a crime."
        ),
        (
            "Report any archaeological object you find within 14 days, to the Ulster Museum, the police "
            "or the Department for Communities."
        ),
    ),
}

# Added to the notices above for an account in the 16 to 17 age band
# (Decision 0009).
FIELD_VISIT_NOTICE_16_17 = (
    "You're 16 or 17, so go with an adult you know, and tell someone at home where you're going."
)


@dataclass(frozen=True)
class FindReportingInfo:
    """Where someone in a nation reports an object they found (Decision 0005, item 9)."""

    scheme: str
    # The scheme's own site, or None where the research recorded no address for it.
    url: str | None
    text: str


# OpenAntiquity stores nothing about a find. Where someone mentions one, the tool
# shows this. The Portable Antiquities Scheme covers England and Wales, and its
# site terms allow links to its home page only. Northern Ireland has no
# Portable Antiquities Scheme: the 1995 Order sends finds to the Ulster Museum,
# the police or the Department for Communities. Checked against the same
# legislation as FIELD_VISIT_NOTICES.
FIND_REPORTING: dict[Nation, FindReportingInfo] = {
    Nation.ENGLAND: FindReportingInfo(
        "Portable Antiquities Scheme",
        "https://finds.org.uk/",
        f"Report anything you find to the Portable Antiquities Scheme. {_TREASURE}",
    ),
    Nation.SCOTLAND: FindReportingInfo(
        "Treasure Trove Scotland",
        "https://treasuretrovescotland.co.uk/",
        "Every archaeological object you find, whatever it's made of, must be reported to Treasure Trove.",
    ),
    Nation.WALES: FindReportingInfo(
        "Portable Antiquities Scheme in Wales",
        "https://finds.org.uk/",
        f"Report anything you find to the Portable Antiquities Scheme in Wales. {_TREASURE}",
    ),
    Nation.NORTHERN_IRELAND: FindReportingInfo(
        "Department for Communities",
        None,
        (
            "Report any archaeological object you find within 14 days, to the Ulster Museum, the police "
            f"or the Department for Communities. {_TREASURE}"
        ),
    ),
}


class LinkShows(StrEnum):
    """What an external viewer in `GET /context/links` shows at a place."""

    RECORDS = "records"
    HISTORIC_MAPS = "historic_maps"
    AERIAL_PHOTOGRAPHS = "aerial_photographs"
    LIDAR = "lidar"
    PHOTOGRAPHS = "photographs"
    OTHER = "other"


@dataclass(frozen=True)
class LinkShowsInfo:
    id: LinkShows
    label: str
    description: str


LINK_SHOWS: tuple[LinkShowsInfo, ...] = (
    LinkShowsInfo(
        LinkShows.RECORDS, "Heritage records", "What a register or database of known sites holds here."
    ),
    LinkShowsInfo(LinkShows.HISTORIC_MAPS, "Old maps", "Maps of this place from the last two hundred years."),
    LinkShowsInfo(
        LinkShows.AERIAL_PHOTOGRAPHS, "Aerial photographs", "Photographs of this place taken from the air."
    ),
    LinkShowsInfo(
        LinkShows.LIDAR, "LIDAR", "The shape of the ground here, from laser survey, in another viewer."
    ),
    LinkShowsInfo(LinkShows.PHOTOGRAPHS, "Photographs", "Photographs people have taken here on the ground."),
    LinkShowsInfo(
        LinkShows.OTHER, "Other", "Something else about this place, such as a report or a place-name."
    ),
)


class LinkCoverage(StrEnum):
    """Where an external viewer in `GET /context/links` has something to show."""

    ENGLAND = "england"
    SCOTLAND = "scotland"
    WALES = "wales"
    NORTHERN_IRELAND = "northern_ireland"
    GB = "gb"
    UK = "uk"
    WIDER = "wider"


@dataclass(frozen=True)
class LinkCoverageInfo:
    id: LinkCoverage
    label: str


LINK_COVERAGES: tuple[LinkCoverageInfo, ...] = (
    LinkCoverageInfo(LinkCoverage.ENGLAND, "England"),
    LinkCoverageInfo(LinkCoverage.SCOTLAND, "Scotland"),
    LinkCoverageInfo(LinkCoverage.WALES, "Wales"),
    LinkCoverageInfo(LinkCoverage.NORTHERN_IRELAND, "Northern Ireland"),
    LinkCoverageInfo(LinkCoverage.GB, "Great Britain"),
    LinkCoverageInfo(LinkCoverage.UK, "The United Kingdom"),
    LinkCoverageInfo(LinkCoverage.WIDER, "Beyond the UK too"),
)


class LiveFormat(StrEnum):
    """The shape of a live source's answer, so the browser reads it without guessing (Decision 0007)."""

    # A GeoJSON FeatureCollection: names and ids are in each feature's `properties`.
    GEOJSON = "geojson"
    # The Archaeology Data Service catalogue search: `hits[]`, with `total.value`.
    ADS_SEARCH = "ads_search"
    # The catalogue's map search: up to 500 `hits[]`, otherwise a geohash grid in `aggregations`.
    ADS_MAP = "ads_map"
    # One catalogue record, shaped as a search hit.
    ADS_RECORD = "ads_record"
    # A MediaWiki `action=query` answer: the items are the values of `query.pages`.
    MEDIAWIKI_QUERY = "mediawiki_query"


SENSITIVITY_NOTICE = (
    "Some findings have their position hidden to protect the site, and are shown as a one-kilometre "
    "square to anyone who hasn't signed in. Signed-in members see protected findings exactly."
)

CONTRIBUTION_LICENCE = "CC BY 4.0"
CONTRIBUTION_LICENCE_URL = "https://creativecommons.org/licenses/by/4.0/"


class FollowUp(StrEnum):
    """Whether an evidence kind is a follow-up, and of which sort: work at the site, or the official record.

    `none` for the desk kinds. A follow-up is logged as `followup_logged`.
    """

    FIELD = "field"
    OFFICIAL = "official"
    NONE = "none"


class LinkVerified(StrEnum):
    """Whether the research found that a deep link opens where it should (`GET /context/links`)."""

    YES = "yes"
    REDIRECT_ONLY = "redirect_only"
    NOT_TESTED = "not_tested"


@dataclass(frozen=True)
class LinkVerifiedInfo:
    id: LinkVerified
    label: str
    description: str


LINK_VERIFIED: tuple[LinkVerifiedInfo, ...] = (
    LinkVerifiedInfo(LinkVerified.YES, "Checked", "When it was last checked, the page opened."),
    LinkVerifiedInfo(
        LinkVerified.REDIRECT_ONLY,
        "Redirects",
        "When it was last checked, the address sent the browser on to a new one, "
        "but the page it reached wasn't seen.",
    ),
    LinkVerifiedInfo(LinkVerified.NOT_TESTED, "Not checked", "Nobody has checked yet that it opens."),
)


class CreditPlacement(StrEnum):
    """Where a live source's credit must be shown (`GET /context/live-sources`)."""

    # Once, wherever the source's layer or list is shown.
    LAYER = "layer"
    # Beside each record the source gives.
    RECORD = "record"


def _check_complete() -> None:
    """Every enum member needs exactly one row in its descriptive table, in enum order."""
    tables: tuple[tuple[type[StrEnum], tuple[object, ...]], ...] = (
        (Role, ROLES),
        (SignInProvider, SIGN_IN_PROVIDERS),
        (FeatureClass, FEATURE_CLASSES),
        (Period, PERIODS),
        (EvidenceKind, EVIDENCE_KINDS),
        (Check, CHECKS),
        (Explanation, EXPLANATIONS),
        (Tier, TIERS),
        (FindingState, STATES),
        (MentionKind, MENTION_KINDS),
        (RecordCategory, RECORD_CATEGORIES),
        (NextStepCode, NEXT_STEPS),
        (LinkShows, LINK_SHOWS),
        (LinkCoverage, LINK_COVERAGES),
        (Sensitivity, SENSITIVITY_LEVELS),
        (LinkVerified, LINK_VERIFIED),
    )
    for enum_cls, rows in tables:
        ids = [getattr(row, "id") for row in rows]  # noqa: B009 - rows are heterogeneous dataclasses
        assert ids == list(enum_cls), f"{enum_cls.__name__} and its descriptive table disagree: {ids}"
    assert set(FIELD_VISIT_NOTICES) == set(Nation), "every nation needs field visit notices"
    assert set(FIND_REPORTING) == set(Nation), "every nation needs a route for reporting a find"
    assert set(AGE_BAND_YOUNGEST) == set(AgeBand), "every age band needs its youngest age"
    assert SENSITIVITY_ORDER[0] is Sensitivity.OPEN
    assert [info.base_score for info in TIERS] == sorted(info.base_score for info in TIERS)


_check_complete()
