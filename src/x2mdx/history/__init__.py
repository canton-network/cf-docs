"""Shared history contracts for generated reference surfaces."""

from x2mdx.history.events import history_events_for_item
from x2mdx.history.io import (
    history_report_from_dict,
    history_report_to_dict,
    load_history_report,
)
from x2mdx.history.models import (
    ChangeDetail,
    Evidence,
    EvidenceKind,
    HistoryEvent,
    HistoryEventKind,
    HistoryItem,
    HistoryMode,
    IdentityConfidence,
    LifecycleState,
    LifecycleTransition,
    ReferenceFormat,
    ReplacementEdge,
    SourceArtifact,
    SurfaceHistoryReport,
    VersionSelectionPolicy,
)
from x2mdx.history.validation import HistoryValidationError, validate_history_report

__all__ = [
    "ChangeDetail",
    "Evidence",
    "EvidenceKind",
    "HistoryEvent",
    "HistoryEventKind",
    "HistoryItem",
    "HistoryMode",
    "HistoryValidationError",
    "IdentityConfidence",
    "LifecycleState",
    "LifecycleTransition",
    "ReferenceFormat",
    "ReplacementEdge",
    "SourceArtifact",
    "SurfaceHistoryReport",
    "VersionSelectionPolicy",
    "history_events_for_item",
    "history_report_from_dict",
    "history_report_to_dict",
    "load_history_report",
    "validate_history_report",
]
