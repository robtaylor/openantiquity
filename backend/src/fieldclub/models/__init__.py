"""Every table. Importing this package registers them all on `Base.metadata`."""

from fieldclub.models.collaboration import (
    Activity,
    Investigation,
    InvestigationHeldFinding,
    InvestigationItem,
    InvestigationMember,
    Notification,
    Report,
    SquareSurvey,
    WatchChannel,
)
from fieldclub.models.findings import (
    Comment,
    Evidence,
    EvidenceVote,
    Finding,
    FindingShapeChange,
    Follow,
    Media,
    Mention,
    Observation,
)
from fieldclub.models.moderation import ModerationAction
from fieldclub.models.people import (
    AuthIdentity,
    MagicLink,
    ReleasedHandle,
    ReputationEvent,
    User,
    UserSession,
)
from fieldclub.models.records import AdminArea, IngestRun, Place, Record, RecordCellCount, Source

__all__ = [
    "Activity",
    "AdminArea",
    "AuthIdentity",
    "Comment",
    "Evidence",
    "EvidenceVote",
    "Finding",
    "FindingShapeChange",
    "Follow",
    "IngestRun",
    "Investigation",
    "InvestigationHeldFinding",
    "InvestigationItem",
    "InvestigationMember",
    "MagicLink",
    "Media",
    "Mention",
    "ModerationAction",
    "Notification",
    "Observation",
    "Place",
    "Record",
    "RecordCellCount",
    "ReleasedHandle",
    "Report",
    "ReputationEvent",
    "Source",
    "SquareSurvey",
    "User",
    "UserSession",
    "WatchChannel",
]
