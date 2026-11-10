"""Every table. Importing this package registers them all on `Base.metadata`."""

from fieldclub.models.collaboration import (
    Activity,
    Investigation,
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
    Follow,
    Media,
    Mention,
    Observation,
)
from fieldclub.models.people import AuthIdentity, MagicLink, ReputationEvent, User, UserSession
from fieldclub.models.records import AdminArea, IngestRun, Place, Record, RecordCellCount, Source

__all__ = [
    "Activity",
    "AdminArea",
    "AuthIdentity",
    "Comment",
    "Evidence",
    "EvidenceVote",
    "Finding",
    "Follow",
    "IngestRun",
    "Investigation",
    "InvestigationItem",
    "InvestigationMember",
    "MagicLink",
    "Media",
    "Mention",
    "Notification",
    "Observation",
    "Place",
    "Record",
    "RecordCellCount",
    "Report",
    "ReputationEvent",
    "Source",
    "SquareSurvey",
    "User",
    "UserSession",
    "WatchChannel",
]
