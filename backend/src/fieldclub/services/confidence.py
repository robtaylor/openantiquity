"""The confidence engine: one pure function from a finding's contributions to its assessment.

The rules are the "Confidence engine" section of `docs/ARCHITECTURE.md`, and
the reasons for them are Decisions 0003 and 0008. This module reads nothing
from the database and imports nothing from FastAPI or SQLAlchemy.

Interface
=========

    from fieldclub.services.confidence import (
        EvidenceInput, FindingInputs, ObservationInput, VoteInput, assess, load_assessment,
    )

    inputs = FindingInputs(
        author_id=finding.author_id,
        author_role=Role(author.role),
        feature_class=FeatureClass(finding.feature_class),
        state=FindingState(finding.state),
        observations=(ObservationInput(user_id=..., role=..., visible=Visible.YES, ...), ...),
        evidence=(EvidenceInput(id=..., user_id=..., role=..., kind=..., votes=(VoteInput(...),)), ...),
    )
    assessment = assess(inputs)

- Pass every observation and every evidence item, the finder's and deleted
  ones included. The engine decides what counts. Pass each person's current
  role. Enum fields accept the stored strings and are converted, so a bad
  value fails loudly. Inputs that break an assumption (two observations by
  one person, a vote that isn't +1 or -1, two votes by one person on one
  item, a repeated evidence id) raise `InvalidInputsError`.
- `assessment.tier`, `.state`, `.state_reason` and `.score` are the columns
  `findings.tier`, `state`, `state_reason` and `confidence`.
  `assessment.community_class` is `findings.community_class`.
- `assessment.to_json()` is what `findings.assessment` stores.
  `load_assessment(finding.assessment)` reads it back, and returns None for
  the empty default or an older shape. `services.reputation.awards(old, new)`
  takes the loaded old assessment and the new one.
- `assessment.next_steps` lists the unmet requirements of the next tier, each
  with a `code` from `NextStepCode`, an English `prompt`, and the numbers a
  person needs: `people` (how many more members, each of weight 1.0),
  `check`, `strands_needed`, `missing_strands`, `weight_needed` and
  `pending_evidence` (ids of items waiting for an endorsement or a
  verification). The same list drives the help-wanted queue. After them
  comes `look_at_new_part` when more than `NEW_PART_LOOK_M` has been added
  to the line since the newest second look (`added_since_looked_m`), which
  no tier requires.
- `assessment.credits` says who did what, one `Credit` per person and kind,
  so the finding page can name people.

Blind review (Decision 0008) has no place here. The engine sees every answer.
`assessment.observations` and the answer kinds in `assessment.credits` show
how each person answered, so hiding them from a reviewer who hasn't answered
yet is the API's job.

Decisions where the contract is silent or two rules pull apart
==============================================================

Each of these is listed for the contract to take up.

1. The finder's own observation is ignored entirely: for visibility, class
   support, checks and explanations. The finder's class already counts once,
   through the finding's feature class, at the finder's weight.
2. A "yes" that also gives an explanation (modern, natural, artefact) counts
   towards neither `seen` nor `unseen`, and doesn't make its author an
   observer or a reviewer. It still counts as that explanation's weight.
   Like every answer that doesn't count as seeing it, it names no class and
   clears no check (rule 15).
   Otherwise three people saying "I see it, it's a drain" would lift a
   finding to Seen and could never rule it out, because the explanation
   rule needs its weight to exceed `seen`.
3. Votes by the evidence's own contributor and votes by the finder are
   ignored, both for whether an item stands and for endorsement. Without the
   second, a finder could vote down evidence that contradicts their finding.
4. Evidence added by the finder and endorsed (+1) by one other person with
   weight of at least 1.0 is independent, as the contract says. Independence
   is required of contradicting evidence as well as supporting evidence.
5. A field item (photo, field visit, geophysics, excavation) points the way
   its `outcome` says, when it has one: `inconclusive` is neutral. Otherwise,
   and for every other kind, its `stance` decides. "Ground item" means any
   field item, ground or survey, in every rule, and only an independent one
   counts towards "ground items disagree" and the ruling-out on the ground.
   So a finder's own unendorsed site report neither blocks a ruling-out nor
   rules out their own finding.
6. A field item added by the finder needs an endorsement from someone else
   to reach Checked on the ground, even when the finder is trusted. Nobody
   checks their own finding on the ground.
7. "Verified by an expert or moderator" means a verifier whose role is
   expert, moderator or admin, who is neither the finder nor the item's
   contributor, on an official item that stands and supports the finding.
   Verifying is a second person's check, and On record pays the finder 30.
8. Every two-thirds figure is exactly 2/3: `community_class`, the class
   agreement of Corroborated, the seen ratio and the top of the disputed
   band. With 0.67, two people who see it against one who doesn't would fall
   short of Seen, and four against two would be disputed, while a 2:1 split
   on the class counts as agreement.
9. The disputed ratio band is open at both ends, 0.33 < ratio < 2/3, so a
   ratio of 2/3 is Seen and never disputed. The bottom stays at 0.33, with
   the ruled-out ratio, so an exact one-to-two split is disputed rather than
   ruled out: where the rules are close, the engine doesn't rule a finding
   out.
   Contradicting strands make a finding disputed only when there is at least
   one, and they are at least as many as the supporting strands, counted over
   every strand.
10. State precedence is withdrawn, ruled out, disputed, known, open. A known
    finding that is later disputed shows as disputed, and `assessment.known`
    still says it matches a record.
11. When a ruled-out rule holds at Checked on the ground or above, the state
    is disputed and `state_reason` is the rule's reason. Ruled out by weight
    and then supported on the ground is that case. When several ruled-out
    rules hold, the reason is `ground_check` first, then the heaviest
    explanation, then `not_visible`.
12. `withdrawn` is the one state the engine is told, through
    `FindingInputs.state`. A withdrawn finding keeps its computed tier,
    scores that tier's base and offers no next steps. A ruled-out finding
    scores 0 and offers no next steps either. Every other state passed in is
    recomputed from scratch.
13. The score is the tier's base plus the gap to the next base times the
    share of the next tier's requirements met, rounded down. The
    requirements are: Seen, the weight, the observer count and the ratio;
    Corroborated, each strand and the class agreement; Probable, each check
    and the review; the top two tiers, their one item each.
14. `satisfied` holds every tier whose own rule is met, so a finding confirmed
    on record can also be Seen. Reputation awards tier points from it.
15. Class support and the three checks count only answers that count as
    seeing it (a "yes" with no explanation). Someone who can't see a feature
    has no basis to say what it is or that it isn't modern. Explanations
    count from every answer.
"""

from __future__ import annotations

import math
import types
import typing
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import MISSING, dataclass, fields, is_dataclass
from enum import StrEnum
from functools import cache
from typing import Any

from fieldclub.errors import DataIntegrityError
from fieldclub.vocab import (
    CHECK_EXPLANATIONS,
    DESK_STRANDS,
    EVIDENCE_KINDS,
    MODERATOR_ROLES,
    RECORD_STRAND_RELATIONS,
    REVIEWER_ROLES,
    TIER_BASE_SCORES,
    TIER_ORDER,
    TRUSTED_ROLES,
    Check,
    EvidenceGroup,
    EvidenceKind,
    Explanation,
    FeatureClass,
    FindingState,
    NextStepCode,
    Outcome,
    Relation,
    Role,
    Stance,
    StateReason,
    Strand,
    Tier,
    Visible,
    role_weight,
    strand_for,
    tier_rank,
)

# Weights are sums of 1.0, 1.5 and 3.0, which floats hold exactly. Ratios are
# not exact, so comparisons allow for rounding.
_EPS = 1e-9

# Bumped whenever the shape of `Assessment.to_json()` changes, except for a
# field added with a default: a stored assessment without it reads with the
# default until the finding is next reassessed (`_decode`).
ASSESSMENT_VERSION = 1

FIELD_STRANDS: frozenset[Strand] = frozenset(
    info.strand for info in EVIDENCE_KINDS if info.group is EvidenceGroup.FIELD
)

# Who may verify an official item so that it puts a finding on record.
VERIFIER_ROLES: frozenset[Role] = frozenset({Role.EXPERT}) | MODERATOR_ROLES

_OUTCOME_DIRECTION: dict[Outcome, Stance] = {
    Outcome.SUPPORTS: Stance.SUPPORTS,
    Outcome.INCONCLUSIVE: Stance.NEUTRAL,
    Outcome.CONTRADICTS: Stance.CONTRADICTS,
}


class MetBy(StrEnum):
    """What kind of help meets a next step."""

    SECOND_LOOK = "second_look"
    EVIDENCE = "evidence"


class Endorsement(StrEnum):
    """When an evidence item counts for a step only once someone else endorses it.

    An item is endorsed when people other than its contributor and the finder
    vote it up with a summed weight of at least `Thresholds.endorsement_weight`.
    """

    NOT_NEEDED = "not_needed"
    # The finder's own item needs an endorsement. Anyone else's counts as it is.
    IF_ADDED_BY_FINDER = "if_added_by_finder"
    # Every item needs an endorsement, unless someone other than the finder
    # with a trusted role (`vocab.TRUSTED_ROLES`) added it.
    UNLESS_ADDED_BY_TRUSTED_OTHER = "unless_added_by_trusted_other"


@dataclass(frozen=True)
class EvidenceFacts:
    """What `StepRule.counts` needs to know about one evidence item."""

    kind: EvidenceKind
    relation: Relation | None
    stance: Stance
    outcome: Outcome | None
    by_finder: bool
    # The contributor's role is one of `vocab.TRUSTED_ROLES`.
    trusted: bool
    endorsed: bool
    # Its votes sum to zero or more. Every step needs this.
    standing: bool
    # Someone other than the finder and the contributor, in `VERIFIER_ROLES`, verified it.
    verified: bool


@dataclass(frozen=True)
class StepRule:
    """What meets one next step, as `_next_steps` and `_evidence_status` count it.

    A step met by evidence names the kinds that count, the relations a
    record link needs, the stance or outcome the item must point, whether it
    needs an endorsement and whether it needs a verification. An item counts
    only while its votes sum to zero or more. `counts` says whether one item
    meets the step, and `tests/confidence/test_step_rules.py` holds it to the
    engine for every combination.
    """

    code: NextStepCode
    met_by: MetBy
    evidence_kinds: tuple[EvidenceKind, ...] = ()
    # The relations a `record_link` counts with. Empty where no record link counts.
    record_relations: tuple[Relation, ...] = ()
    # What a field item's outcome must say, or None where the stance decides.
    outcome: Outcome | None = None
    stance: Stance | None = None
    endorsement: Endorsement = Endorsement.NOT_NEEDED
    # True when the item counts only once an archaeologist or moderator verifies it.
    needs_verification: bool = False

    def counts(self, item: EvidenceFacts) -> bool:
        """Whether one evidence item meets this step."""
        assert self.met_by is MetBy.EVIDENCE, "only a step met by evidence counts items"
        if not item.standing or item.kind not in self.evidence_kinds:
            return False
        if item.kind is EvidenceKind.RECORD_LINK and item.relation not in self.record_relations:
            return False
        if self.outcome is not None and item.outcome is not self.outcome:
            return False
        if self.stance is not None and item.stance is not self.stance:
            return False
        if self.needs_verification and not item.verified:
            return False
        match self.endorsement:
            case Endorsement.NOT_NEEDED:
                return True
            case Endorsement.IF_ADDED_BY_FINDER:
                return item.endorsed or not item.by_finder
            case Endorsement.UNLESS_ADDED_BY_TRUSTED_OTHER:
                return item.endorsed or (item.trusted and not item.by_finder)


def _kinds_in(strands: Iterable[Strand]) -> tuple[EvidenceKind, ...]:
    wanted = frozenset(strands)
    return tuple(info.id for info in EVIDENCE_KINDS if info.strand in wanted)


# Every next step and what meets it. `/meta` serves this, and the queue and
# the blind steps use the second-look ones (`services.findings.ANSWER_CODES`).
STEP_RULES: tuple[StepRule, ...] = (
    StepRule(NextStepCode.NEED_OBSERVERS, MetBy.SECOND_LOOK),
    StepRule(
        NextStepCode.NEED_STRAND,
        MetBy.EVIDENCE,
        evidence_kinds=_kinds_in(DESK_STRANDS),
        record_relations=tuple(r for r in Relation if r in RECORD_STRAND_RELATIONS),
        stance=Stance.SUPPORTS,
        endorsement=Endorsement.IF_ADDED_BY_FINDER,
    ),
    StepRule(NextStepCode.NEED_CLASS_AGREEMENT, MetBy.SECOND_LOOK),
    StepRule(NextStepCode.NEED_CHECK, MetBy.SECOND_LOOK),
    StepRule(NextStepCode.NEED_TRUSTED_REVIEW, MetBy.SECOND_LOOK),
    StepRule(
        NextStepCode.NEED_GROUND,
        MetBy.EVIDENCE,
        evidence_kinds=_kinds_in(FIELD_STRANDS),
        outcome=Outcome.SUPPORTS,
        endorsement=Endorsement.UNLESS_ADDED_BY_TRUSTED_OTHER,
    ),
    StepRule(
        NextStepCode.NEED_OFFICIAL,
        MetBy.EVIDENCE,
        evidence_kinds=_kinds_in({Strand.OFFICIAL}),
        stance=Stance.SUPPORTS,
        needs_verification=True,
    ),
    StepRule(NextStepCode.LOOK_AT_NEW_PART, MetBy.SECOND_LOOK),
)
assert [rule.code for rule in STEP_RULES] == list(NextStepCode), "every next step says what meets it"
SECOND_LOOK_CODES: frozenset[NextStepCode] = frozenset(
    rule.code for rule in STEP_RULES if rule.met_by is MetBy.SECOND_LOOK
)


# A finding whose line has had more than this many metres added since its
# newest second look asks for a look at the new part (`look_at_new_part`).
# The step is no requirement of a tier, so it moves neither tier nor score.
NEW_PART_LOOK_M = 200.0
# Shown to anyone who sees the finding exactly, so it says nothing of how far or where.
NEW_PART_PROMPT = "Someone needs to look at the part added to its line since the last second look."

# Closed states: they offer nobody a next step, and earn no reputation.
CLOSED_STATES = frozenset({FindingState.RULED_OUT, FindingState.WITHDRAWN})


def _ge(a: float, b: float) -> bool:
    return a >= b - _EPS


def _gt(a: float, b: float) -> bool:
    return a > b + _EPS


def _le(a: float, b: float) -> bool:
    return a <= b + _EPS


def _lt(a: float, b: float) -> bool:
    return a < b - _EPS


class InvalidInputsError(DataIntegrityError):
    code = "invalid_confidence_inputs"
    message = "The confidence engine was given inputs that break its assumptions."


# --------------------------------------------------------------------------
# Thresholds
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Thresholds:
    """Every number the rules use. Role weights are in `vocab.ROLES`."""

    # Seen by others.
    seen_weight: float = 2.0
    seen_observers: int = 2
    seen_ratio: float = 2 / 3
    # Corroborated.
    corroborating_strands: int = 2
    class_agreement: float = 2 / 3
    class_support: float = 2.0
    class_people: int = 2
    # Probable.
    check_weight: float = 2.0
    check_margin: float = 2.0  # asserting weight must exceed this multiple of the explanation's
    probable_seen_without_reviewer: float = 7.0  # Decision 0008
    # Evidence.
    endorsement_weight: float = 1.0
    known_weight: float = 2.0
    # Disputed.
    disputed_weight: float = 2.0
    disputed_ratio_low: float = 0.33
    disputed_ratio_high: float = 2 / 3
    # Ruled out.
    ruled_out_unseen: float = 3.0
    ruled_out_ratio: float = 0.33
    ruled_out_explanation: float = 3.0

    def __post_init__(self) -> None:
        for name in ("seen_ratio", "class_agreement", "disputed_ratio_low", "disputed_ratio_high"):
            value = getattr(self, name)
            assert 0 < value < 1, f"{name} must be a ratio between 0 and 1, not {value}"
        assert self.disputed_ratio_low < self.disputed_ratio_high, "the disputed band is empty"
        assert self.ruled_out_ratio <= self.disputed_ratio_low, "ruled out must sit below the disputed band"
        for name in ("seen_observers", "class_people", "corroborating_strands"):
            assert getattr(self, name) >= 1, f"{name} must be at least 1"


THRESHOLDS = Thresholds()


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


def _coerce(obj: object, name: str, enum: type[StrEnum], *, optional: bool = False) -> None:
    """Turn a stored string into its enum on a frozen dataclass. A bad value raises."""
    value = getattr(obj, name)
    if value is None and optional:
        return
    try:
        object.__setattr__(obj, name, enum(value))
    except ValueError as exc:
        raise InvalidInputsError(
            f"{type(obj).__name__}.{name} is not a valid {enum.__name__}: {value!r}"
        ) from exc


@dataclass(frozen=True)
class VoteInput:
    """An endorsement (+1) or objection (-1) to an evidence item, with the voter's role."""

    user_id: int
    role: Role
    value: int

    def __post_init__(self) -> None:
        _coerce(self, "role", Role)
        if self.value not in (-1, 1):
            raise InvalidInputsError(f"a vote is +1 or -1, not {self.value!r}")


@dataclass(frozen=True)
class ObservationInput:
    """One person's second look, with their role."""

    user_id: int
    role: Role
    visible: Visible
    feature_class: FeatureClass | None = None
    explanation: Explanation | None = None
    not_modern: bool | None = None
    not_natural: bool | None = None
    not_artefact: bool | None = None

    def __post_init__(self) -> None:
        _coerce(self, "role", Role)
        _coerce(self, "visible", Visible)
        _coerce(self, "feature_class", FeatureClass, optional=True)
        _coerce(self, "explanation", Explanation, optional=True)

    def asserts(self, check: Check) -> bool:
        return getattr(self, check.value) is True


@dataclass(frozen=True)
class EvidenceInput:
    """One evidence item, with its contributor's role, its verifier's role and its votes."""

    id: int
    user_id: int
    role: Role
    kind: EvidenceKind
    stance: Stance = Stance.SUPPORTS
    outcome: Outcome | None = None
    relation: Relation | None = None
    deleted: bool = False
    verified_by: int | None = None
    verifier_role: Role | None = None
    votes: tuple[VoteInput, ...] = ()

    def __post_init__(self) -> None:
        _coerce(self, "role", Role)
        _coerce(self, "kind", EvidenceKind)
        _coerce(self, "stance", Stance)
        _coerce(self, "outcome", Outcome, optional=True)
        _coerce(self, "relation", Relation, optional=True)
        _coerce(self, "verifier_role", Role, optional=True)
        object.__setattr__(self, "votes", tuple(self.votes))
        if (self.verified_by is None) != (self.verifier_role is None):
            raise InvalidInputsError(f"evidence {self.id} needs both a verifier and the verifier's role")
        voters = [vote.user_id for vote in self.votes]
        if len(voters) != len(set(voters)):
            raise InvalidInputsError(f"evidence {self.id} has two votes by one person")


@dataclass(frozen=True)
class FindingInputs:
    """Everything the engine reads about one finding."""

    author_id: int
    author_role: Role
    feature_class: FeatureClass
    state: FindingState = FindingState.OPEN
    observations: tuple[ObservationInput, ...] = ()
    evidence: tuple[EvidenceInput, ...] = ()
    # The length extensions added to the finding's line since the newest
    # standing second look, in metres. None when no such answer is older than
    # an extension. It asks for a look at the new part and moves nothing else.
    added_since_looked_m: float | None = None

    def __post_init__(self) -> None:
        if self.added_since_looked_m is not None and not self.added_since_looked_m >= 0:
            raise InvalidInputsError("the length added since the last second look can't be negative")
        _coerce(self, "author_role", Role)
        _coerce(self, "feature_class", FeatureClass)
        _coerce(self, "state", FindingState)
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(self, "evidence", tuple(self.evidence))
        people = [obs.user_id for obs in self.observations]
        if len(people) != len(set(people)):
            raise InvalidInputsError("a person can give only one observation of a finding")
        ids = [item.id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise InvalidInputsError("two evidence items share an id")


# --------------------------------------------------------------------------
# The assessment
# --------------------------------------------------------------------------


class CreditKind(StrEnum):
    """What a person did for a finding, for the credits on its page."""

    SPOTTED = "spotted"
    SAW_IT = "saw_it"
    COULD_NOT_SEE = "could_not_see"
    UNSURE = "unsure"
    EXPLAINED = "explained"
    ADDED_EVIDENCE = "added_evidence"
    ENDORSED = "endorsed"
    VERIFIED = "verified"


_CREDIT_ORDER = {kind: index for index, kind in enumerate(CreditKind)}


@dataclass(frozen=True)
class Credit:
    user_id: int
    kind: CreditKind
    evidence_id: int | None = None


@dataclass(frozen=True)
class CheckStatus:
    check: Check
    asserted: float  # weight of people saying it isn't this
    against: float  # weight of people giving the matching explanation
    cleared: bool


@dataclass(frozen=True)
class ObservationStatus:
    """How one person other than the finder answered, and whether it counts as seeing it."""

    user_id: int
    visible: Visible
    feature_class: FeatureClass | None
    explanation: Explanation | None
    counts_as_seen: bool


@dataclass(frozen=True)
class EvidenceStatus:
    """What the engine made of one evidence item that isn't deleted."""

    id: int
    user_id: int
    kind: EvidenceKind
    strand: Strand | None
    direction: Stance
    outcome: Outcome | None
    verifier: int | None  # who verified it, when their verification counts
    vote_total: float
    endorsers: tuple[int, ...]  # people other than the contributor and the finder who voted +1
    standing: bool
    independent: bool
    checks_ground: bool  # qualifies the finding for Checked on the ground
    puts_on_record: bool  # qualifies the finding for On record
    matches_record: bool  # a same_as record link with enough weight for `known`
    awaiting: bool  # would count for a tier once someone else endorses or verifies it
    # People other than the contributor and the finder who voted -1. Added
    # after the first stored assessments, so it has a default (see `_decode`).
    disputers: tuple[int, ...] = ()


@dataclass(frozen=True)
class NextStep:
    code: NextStepCode
    prompt: str
    people: int | None = None
    check: Check | None = None
    strands_needed: int | None = None
    missing_strands: tuple[Strand, ...] = ()
    weight_needed: float | None = None
    pending_evidence: tuple[int, ...] = ()


@dataclass(frozen=True)
class Assessment:
    finder_id: int
    tier: Tier
    state: FindingState
    state_reason: StateReason | None
    score: int
    next_tier: Tier | None
    progress: float  # share of the next tier's requirements met, 0 at the top
    next_steps: tuple[NextStep, ...]
    satisfied: frozenset[Tier]
    seen: float
    unseen: float
    observers: int
    seen_ratio: float | None
    reviewers: tuple[int, ...]  # trusted or expert people who can see it
    explanations: dict[Explanation, float]
    class_support: dict[FeatureClass, float]
    class_agreement: float
    class_leader: FeatureClass | None
    class_people: int  # people naming the leading class
    community_class: FeatureClass | None
    supporting_strands: frozenset[Strand]
    contradicting_strands: frozenset[Strand]
    checks: tuple[CheckStatus, ...]
    known: bool
    ground_supports: bool
    ground_contradicts: bool
    observations: tuple[ObservationStatus, ...]
    evidence: tuple[EvidenceStatus, ...]
    credits: tuple[Credit, ...]

    @property
    def desk_strands(self) -> frozenset[Strand]:
        return self.supporting_strands & DESK_STRANDS

    def check(self, check: Check) -> CheckStatus:
        return next(status for status in self.checks if status.check is check)

    def to_json(self) -> dict[str, Any]:
        """The JSON stored in `findings.assessment`."""
        encoded = _encode(self)
        assert isinstance(encoded, dict)
        return {"version": ASSESSMENT_VERSION, **encoded}

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Assessment:
        if data.get("version") != ASSESSMENT_VERSION:
            raise InvalidInputsError(
                f"assessment version {data.get('version')!r} is not {ASSESSMENT_VERSION}"
            )
        stored = {key: value for key, value in data.items() if key != "version"}
        decoded = _decode(cls, {**stored, "next_steps": _known_steps(stored["next_steps"])})
        assert isinstance(decoded, cls)
        return decoded


def load_assessment(data: Mapping[str, Any] | None) -> Assessment | None:
    """A stored assessment, or None for the empty default or a shape from another version."""
    if not data or data.get("version") != ASSESSMENT_VERSION:
        return None
    return Assessment.from_json(data)


def load_next_steps(data: Mapping[str, Any]) -> tuple[NextStep, ...]:
    """Only the next steps of a stored assessment, without decoding the rest of it."""
    if data.get("version") != ASSESSMENT_VERSION:
        raise InvalidInputsError(f"assessment version {data.get('version')!r} is not {ASSESSMENT_VERSION}")
    steps = _decode(tuple[NextStep, ...], _known_steps(data["next_steps"]))
    assert isinstance(steps, tuple)
    return steps


def _known_steps(stored: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The stored next steps this version has a name for.

    A newer version serving beside this one during a deploy, or one this
    version was gone back from, can have stored a step it added. That step is
    left out before any of its fields is read: nothing here could ask for it,
    and the rest of the assessment reads as it was written (Decision 0033).
    """
    return [step for step in stored if step["code"] in NextStepCode]


# --------------------------------------------------------------------------
# The engine
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Classes:
    support: dict[FeatureClass, float]
    people: dict[FeatureClass, int]
    total: float
    agreement: float
    top: FeatureClass | None  # leader, ties broken by vocab order, for next-step numbers
    leader: FeatureClass | None  # None on a tie
    community: FeatureClass | None


def assess(inputs: FindingInputs, thresholds: Thresholds = THRESHOLDS) -> Assessment:
    """Assess a finding from its contributions. Pure: the same inputs give the same result."""
    t = thresholds
    finder = inputs.author_id
    observations = sorted(
        (obs for obs in inputs.observations if obs.user_id != finder), key=lambda o: o.user_id
    )
    items = sorted((item for item in inputs.evidence if not item.deleted), key=lambda i: i.id)

    # Visibility.
    seen_by = [obs for obs in observations if obs.visible is Visible.YES and obs.explanation is None]
    seen = sum(role_weight(obs.role) for obs in seen_by)
    unseen = sum(role_weight(obs.role) for obs in observations if obs.visible is Visible.NO)
    observers = len(seen_by)
    ratio = seen / (seen + unseen) if seen + unseen > 0 else None
    reviewers = tuple(obs.user_id for obs in seen_by if obs.role in REVIEWER_ROLES)
    seen_ids = {obs.user_id for obs in seen_by}

    explanations: dict[Explanation, float] = defaultdict(float)
    for obs in observations:
        if obs.explanation is not None:
            explanations[obs.explanation] += role_weight(obs.role)

    # Only people who can see it say what it is, or that it isn't modern, natural or an artefact.
    classes = _class_support(inputs, seen_by, t)
    checks = tuple(_check_status(check, seen_by, explanations, t) for check in Check)
    evidence = tuple(_evidence_status(item, finder, t) for item in items)

    def strands(direction: Stance) -> frozenset[Strand]:
        return frozenset(
            e.strand
            for e in evidence
            if e.strand is not None and e.standing and e.independent and e.direction is direction
        )

    supporting = strands(Stance.SUPPORTS)
    contradicting = strands(Stance.CONTRADICTS)
    desk = supporting & DESK_STRANDS
    field = [e for e in evidence if e.standing and e.independent and e.strand in FIELD_STRANDS]
    ground_supports = any(e.outcome is Outcome.SUPPORTS for e in field)
    ground_contradicts = any(e.outcome is Outcome.CONTRADICTS for e in field)
    known = any(e.matches_record for e in evidence)

    # Tiers.
    seen_parts = (
        _ge(seen, t.seen_weight),
        observers >= t.seen_observers,
        ratio is not None and _ge(ratio, t.seen_ratio),
    )
    class_ok = classes.community is not None and classes.people[classes.community] >= t.class_people
    corroborated_parts = (*(len(desk) > n for n in range(t.corroborating_strands)), class_ok)
    review_ok = bool(reviewers) or _ge(seen, t.probable_seen_without_reviewer)
    probable_parts = (*(status.cleared for status in checks), review_ok)
    satisfied = {Tier.SPOTTED}
    if all(seen_parts):
        satisfied.add(Tier.SEEN)
        if all(corroborated_parts):
            satisfied.add(Tier.CORROBORATED)
            if all(probable_parts):
                satisfied.add(Tier.PROBABLE)
    if any(e.checks_ground for e in evidence):
        satisfied.add(Tier.GROUND_CHECKED)
    if any(e.puts_on_record for e in evidence):
        satisfied.add(Tier.CONFIRMED)
    tier = max(satisfied, key=tier_rank)

    # State.
    ruled_out = _ruled_out_reason(seen, unseen, ratio, explanations, ground_supports, ground_contradicts, t)
    disputed = (
        (
            _ge(seen, t.disputed_weight)
            and _ge(unseen, t.disputed_weight)
            and ratio is not None
            and _gt(ratio, t.disputed_ratio_low)
            and _lt(ratio, t.disputed_ratio_high)
        )
        or (len(contradicting) >= 1 and len(contradicting) >= len(supporting))
        or (ground_supports and ground_contradicts)
    )
    state_reason: StateReason | None = None
    if inputs.state is FindingState.WITHDRAWN:
        state = FindingState.WITHDRAWN
    elif ruled_out is not None:
        state_reason = ruled_out
        if tier_rank(tier) < tier_rank(Tier.GROUND_CHECKED):
            state = FindingState.RULED_OUT
        else:
            state = FindingState.DISPUTED
    elif disputed:
        state = FindingState.DISPUTED
    elif known:
        state = FindingState.KNOWN
    else:
        state = FindingState.OPEN

    # Score and next steps.
    requirements: dict[Tier, tuple[bool, ...]] = {
        Tier.SEEN: seen_parts,
        Tier.CORROBORATED: corroborated_parts,
        Tier.PROBABLE: probable_parts,
        Tier.GROUND_CHECKED: (Tier.GROUND_CHECKED in satisfied,),
        Tier.CONFIRMED: (Tier.CONFIRMED in satisfied,),
    }
    rank = tier_rank(tier)
    next_tier = TIER_ORDER[rank + 1] if rank + 1 < len(TIER_ORDER) else None
    if next_tier is None:
        progress, score = 0.0, TIER_BASE_SCORES[tier]
    else:
        parts = requirements[next_tier]
        progress = sum(parts) / len(parts)
        assert progress < 1, f"every requirement of {next_tier} is met, so the tier should be {next_tier}"
        gap = TIER_BASE_SCORES[next_tier] - TIER_BASE_SCORES[tier]
        score = TIER_BASE_SCORES[tier] + math.floor(gap * progress + _EPS)
    if state is FindingState.RULED_OUT:
        score = 0
    elif state is FindingState.WITHDRAWN:
        score = TIER_BASE_SCORES[tier]

    steps: tuple[NextStep, ...] = ()
    if next_tier is not None and state not in CLOSED_STATES:
        steps = _next_steps(
            next_tier,
            seen=seen,
            unseen=unseen,
            observers=observers,
            desk=desk,
            class_ok=class_ok,
            classes=classes,
            checks=checks,
            review_ok=review_ok,
            evidence=evidence,
            t=t,
        )
    added = inputs.added_since_looked_m
    if state not in CLOSED_STATES and added is not None and added > NEW_PART_LOOK_M:
        steps += (NextStep(NextStepCode.LOOK_AT_NEW_PART, NEW_PART_PROMPT, people=1),)

    return Assessment(
        finder_id=finder,
        tier=tier,
        state=state,
        state_reason=state_reason,
        score=score,
        next_tier=next_tier,
        progress=progress,
        next_steps=steps,
        satisfied=frozenset(satisfied),
        seen=seen,
        unseen=unseen,
        observers=observers,
        seen_ratio=ratio,
        reviewers=reviewers,
        explanations=dict(explanations),
        class_support=classes.support,
        class_agreement=classes.agreement,
        class_leader=classes.leader,
        class_people=classes.people.get(classes.leader, 0) if classes.leader is not None else 0,
        community_class=classes.community,
        supporting_strands=supporting,
        contradicting_strands=contradicting,
        checks=checks,
        known=known,
        ground_supports=ground_supports,
        ground_contradicts=ground_contradicts,
        observations=tuple(
            ObservationStatus(
                user_id=obs.user_id,
                visible=obs.visible,
                feature_class=obs.feature_class,
                explanation=obs.explanation,
                counts_as_seen=obs.user_id in seen_ids,
            )
            for obs in observations
        ),
        evidence=evidence,
        credits=_credits(finder, observations, evidence),
    )


def _class_support(
    inputs: FindingInputs, observations: Iterable[ObservationInput], t: Thresholds
) -> _Classes:
    support: dict[FeatureClass, float] = defaultdict(float)
    people: dict[FeatureClass, int] = defaultdict(int)
    named = [(inputs.feature_class, inputs.author_role)]
    named += [(obs.feature_class, obs.role) for obs in observations if obs.feature_class is not None]
    for feature_class, role in named:
        if feature_class is not FeatureClass.UNKNOWN:
            support[feature_class] += role_weight(role)
            people[feature_class] += 1
    total = sum(support.values())
    best = max(support.values(), default=0.0)
    tops = [c for c in FeatureClass if c in support and _ge(support[c], best)]
    leader = tops[0] if len(tops) == 1 else None
    agreement = best / total if total > 0 else 0.0
    community = (
        leader
        if leader is not None and _ge(agreement, t.class_agreement) and _ge(total, t.class_support)
        else None
    )
    return _Classes(
        support=dict(support),
        people=dict(people),
        total=total,
        agreement=agreement,
        top=tops[0] if tops else None,
        leader=leader,
        community=community,
    )


def _check_status(
    check: Check,
    observations: Iterable[ObservationInput],
    explanations: Mapping[Explanation, float],
    t: Thresholds,
) -> CheckStatus:
    asserted = sum(role_weight(obs.role) for obs in observations if obs.asserts(check))
    against = explanations.get(CHECK_EXPLANATIONS[check], 0.0)
    cleared = _ge(asserted, t.check_weight) and _gt(asserted, t.check_margin * against)
    return CheckStatus(check=check, asserted=asserted, against=against, cleared=cleared)


def counted_votes(votes: Iterable[VoteInput], contributor: int, finder: int) -> list[VoteInput]:
    """The votes on an item that the engine counts, by voter: not its contributor's or the finder's."""
    return sorted((v for v in votes if v.user_id not in (contributor, finder)), key=lambda v: v.user_id)


def _evidence_status(item: EvidenceInput, finder: int, t: Thresholds) -> EvidenceStatus:
    votes = counted_votes(item.votes, item.user_id, finder)
    vote_total = sum(role_weight(v.role) * v.value for v in votes)
    endorsers = tuple(v.user_id for v in votes if v.value > 0)
    disputers = tuple(v.user_id for v in votes if v.value < 0)
    endorsement = sum(role_weight(v.role) for v in votes if v.value > 0)
    endorsed = _ge(endorsement, t.endorsement_weight)
    standing = _ge(vote_total, 0.0)
    by_finder = item.user_id == finder
    independent = not by_finder or endorsed
    strand = strand_for(item.kind, item.relation)
    is_field = strand in FIELD_STRANDS
    # A field item points the way its outcome says, when it has one.
    direction = _OUTCOME_DIRECTION[item.outcome] if is_field and item.outcome is not None else item.stance

    ground_candidate = standing and is_field and item.outcome is Outcome.SUPPORTS
    checks_ground = ground_candidate and (endorsed or (not by_finder and item.role in TRUSTED_ROLES))
    official_candidate = standing and strand is Strand.OFFICIAL and direction is Stance.SUPPORTS
    verified = (
        item.verified_by is not None
        and item.verified_by not in (finder, item.user_id)
        and item.verifier_role in VERIFIER_ROLES
    )
    puts_on_record = official_candidate and verified
    matches_record = (
        standing
        and item.kind is EvidenceKind.RECORD_LINK
        and item.relation is Relation.SAME_AS
        and _ge(role_weight(item.role) + endorsement, t.known_weight)
    )
    desk_candidate = standing and strand in DESK_STRANDS and direction is Stance.SUPPORTS
    awaiting = (
        (desk_candidate and not independent)
        or (ground_candidate and not checks_ground)
        or (official_candidate and not verified)
    )
    return EvidenceStatus(
        id=item.id,
        user_id=item.user_id,
        kind=item.kind,
        strand=strand,
        direction=direction,
        outcome=item.outcome,
        verifier=item.verified_by if verified else None,
        vote_total=vote_total,
        endorsers=endorsers,
        standing=standing,
        independent=independent,
        checks_ground=checks_ground,
        puts_on_record=puts_on_record,
        matches_record=matches_record,
        awaiting=awaiting,
        disputers=disputers,
    )


def _ruled_out_reason(
    seen: float,
    unseen: float,
    ratio: float | None,
    explanations: Mapping[Explanation, float],
    ground_supports: bool,
    ground_contradicts: bool,
    t: Thresholds,
) -> StateReason | None:
    if ground_contradicts and not ground_supports:
        return StateReason.GROUND_CHECK
    heavy = [
        e
        for e in Explanation
        if _ge(explanations.get(e, 0.0), t.ruled_out_explanation) and _gt(explanations[e], seen)
    ]
    if heavy:
        heaviest = max(explanations[e] for e in heavy)
        return StateReason(next(e for e in heavy if _ge(explanations[e], heaviest)).value)
    if _ge(unseen, t.ruled_out_unseen) and ratio is not None and _le(ratio, t.ruled_out_ratio):
        return StateReason.NOT_VISIBLE
    return None


# --------------------------------------------------------------------------
# Next steps
# --------------------------------------------------------------------------

_NUMBER_WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")

CHECK_PHRASES: dict[Check, str] = {
    Check.NOT_MODERN: "isn't modern",
    Check.NOT_NATURAL: "isn't natural",
    Check.NOT_ARTEFACT: "isn't a fault in the data",
}


def _number(n: int) -> str:
    return _NUMBER_WORDS[n] if 0 <= n < len(_NUMBER_WORDS) else str(n)


def _more_people(n: int) -> str:
    """'One more person needs' or 'Three more people need'."""
    return f"{_number(n).capitalize()} more {'person needs' if n == 1 else 'people need'}"


def _members_needed(enough: Callable[[int], bool]) -> int:
    """The fewest extra members, each of weight 1.0, that make `enough` true."""
    for n in range(1, 100_000):
        if enough(n):
            return n
    raise AssertionError("no number of members meets this requirement")


def _next_steps(
    next_tier: Tier,
    *,
    seen: float,
    unseen: float,
    observers: int,
    desk: frozenset[Strand],
    class_ok: bool,
    classes: _Classes,
    checks: tuple[CheckStatus, ...],
    review_ok: bool,
    evidence: tuple[EvidenceStatus, ...],
    t: Thresholds,
) -> tuple[NextStep, ...]:
    """One step per unmet requirement of the next tier. The seen requirements share one step."""
    steps: list[NextStep] = []
    if next_tier is Tier.SEEN:
        n = _members_needed(
            lambda n: (
                _ge(seen + n, t.seen_weight)
                and observers + n >= t.seen_observers
                and _ge((seen + n) / (seen + n + unseen), t.seen_ratio)
            )
        )
        steps.append(
            NextStep(NextStepCode.NEED_OBSERVERS, f"{_more_people(n)} to say they can see it.", people=n)
        )
    elif next_tier is Tier.CORROBORATED:
        needed = t.corroborating_strands - len(desk)
        if needed > 0:
            pending = tuple(e.id for e in evidence if e.awaiting and e.strand in DESK_STRANDS)
            kinds = "kind" if needed == 1 else "kinds"
            prompt = (
                f"It needs {_number(needed)} more {kinds} of evidence, such as an aerial photo or an old map."
            )
            if pending:
                prompt += " Evidence the finder added counts once someone else endorses it."
            steps.append(
                NextStep(
                    NextStepCode.NEED_STRAND,
                    prompt,
                    strands_needed=needed,
                    missing_strands=tuple(s for s in Strand if s in DESK_STRANDS and s not in desk),
                    pending_evidence=pending,
                )
            )
        if not class_ok:
            target = classes.top
            s = classes.support.get(target, 0.0) if target is not None else 0.0
            p = classes.people.get(target, 0) if target is not None else 0
            n = _members_needed(
                lambda n: (
                    _ge((s + n) / (classes.total + n), t.class_agreement)
                    and _ge(classes.total + n, t.class_support)
                    and p + n >= t.class_people
                )
            )
            steps.append(
                NextStep(
                    NextStepCode.NEED_CLASS_AGREEMENT, f"{_more_people(n)} to agree what it is.", people=n
                )
            )
    elif next_tier is Tier.PROBABLE:
        for status in checks:
            if status.cleared:
                continue
            n = _members_needed(
                lambda n, a=status.asserted, e=status.against: (
                    _ge(a + n, t.check_weight) and _gt(a + n, t.check_margin * e)
                )
            )
            steps.append(
                NextStep(
                    NextStepCode.NEED_CHECK,
                    f"{_more_people(n)} to say it {CHECK_PHRASES[status.check]}.",
                    people=n,
                    check=status.check,
                )
            )
        if not review_ok:
            weight = t.probable_seen_without_reviewer - seen
            alternative = math.ceil(weight - _EPS)
            steps.append(
                NextStep(
                    NextStepCode.NEED_TRUSTED_REVIEW,
                    "A trusted member or an archaeologist needs to say they can see it, "
                    f"or {_number(alternative)} more {'person' if alternative == 1 else 'people'}.",
                    people=1,
                    weight_needed=weight,
                )
            )
    elif next_tier is Tier.GROUND_CHECKED:
        pending = tuple(e.id for e in evidence if e.awaiting and e.strand in FIELD_STRANDS)
        prompt = "Someone needs to visit or survey it and report what they find."
        if pending:
            prompt = "A site report that supports it needs someone else to endorse it."
        steps.append(NextStep(NextStepCode.NEED_GROUND, prompt, people=1, pending_evidence=pending))
    else:
        assert next_tier is Tier.CONFIRMED
        pending = tuple(e.id for e in evidence if e.awaiting and e.strand is Strand.OFFICIAL)
        prompt = "It needs a Historic Environment Record entry, a designation or a publication."
        if pending:
            prompt = "An archaeologist or a moderator needs to verify the official record linked to it."
        steps.append(NextStep(NextStepCode.NEED_OFFICIAL, prompt, people=1, pending_evidence=pending))
    return tuple(steps)


# --------------------------------------------------------------------------
# Credits
# --------------------------------------------------------------------------

_ANSWER_CREDITS: dict[Visible, CreditKind] = {
    Visible.YES: CreditKind.SAW_IT,
    Visible.NO: CreditKind.COULD_NOT_SEE,
    Visible.UNSURE: CreditKind.UNSURE,
}
# Every credit that says how someone answered, which a blind viewer mustn't see.
ANSWER_CREDIT_KINDS: frozenset[CreditKind] = frozenset(_ANSWER_CREDITS.values()) | {CreditKind.EXPLAINED}


def _credits(
    finder: int, observations: Iterable[ObservationInput], evidence: Iterable[EvidenceStatus]
) -> tuple[Credit, ...]:
    credits = {Credit(finder, CreditKind.SPOTTED)}
    for obs in observations:
        kind = _ANSWER_CREDITS[obs.visible]
        if obs.visible is Visible.YES and obs.explanation is not None:
            kind = CreditKind.EXPLAINED
        credits.add(Credit(obs.user_id, kind))
    for status in evidence:
        credits.add(Credit(status.user_id, CreditKind.ADDED_EVIDENCE, status.id))
        credits.update(Credit(user, CreditKind.ENDORSED, status.id) for user in status.endorsers)
        if status.verifier is not None:
            credits.add(Credit(status.verifier, CreditKind.VERIFIED, status.id))
    return tuple(sorted(credits, key=lambda c: (c.user_id, _CREDIT_ORDER[c.kind], c.evidence_id or 0)))


# --------------------------------------------------------------------------
# JSON
# --------------------------------------------------------------------------


def _encode(value: Any) -> Any:
    """Plain JSON from an assessment. Sets and mappings come out sorted, so the JSON is stable."""
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _encode(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, frozenset):
        return sorted(_encode(item) for item in value)
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if isinstance(value, dict):
        return {_encode(key): _encode(item) for key, item in sorted(value.items())}
    assert value is None or isinstance(value, bool | int | float | str), f"can't encode {value!r}"
    return value


@cache
def _type_hints(cls: type) -> dict[str, Any]:
    return typing.get_type_hints(cls)


def _decode(tp: Any, value: Any) -> Any:
    """The reverse of `_encode`, guided by the type annotations."""
    origin = typing.get_origin(tp)
    if origin is types.UnionType:
        options = typing.get_args(tp)
        if value is None:
            assert type(None) in options, f"{tp} can't be null"
            return None
        (inner,) = (option for option in options if option is not type(None))
        return _decode(inner, value)
    if origin is tuple:
        inner = typing.get_args(tp)[0]
        return tuple(_decode(inner, item) for item in value)
    if origin is frozenset:
        inner = typing.get_args(tp)[0]
        return frozenset(_decode(inner, item) for item in value)
    if origin is dict:
        key_type, item_type = typing.get_args(tp)
        return {_decode(key_type, key): _decode(item_type, item) for key, item in value.items()}
    if isinstance(tp, type) and is_dataclass(tp):
        hints = _type_hints(tp)
        names = {f.name for f in fields(tp)}
        required = {f.name for f in fields(tp) if f.default is MISSING and f.default_factory is MISSING}
        assert required <= set(value) <= names, f"stored {tp.__name__} has the wrong fields"
        return tp(**{name: _decode(hints[name], item) for name, item in value.items()})
    if isinstance(tp, type) and issubclass(tp, StrEnum):
        return tp(value)
    if tp is float:
        assert isinstance(value, int | float), f"stored {value!r} is not a number"
        assert not isinstance(value, bool), f"stored {value!r} is not a number"
        return float(value)
    assert tp in (int, str, bool), f"can't decode a {tp}"
    assert isinstance(value, tp), f"stored {value!r} is not a {tp}"
    return value
