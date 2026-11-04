"""Fictional exhibition material. This module is not the LATIS engine."""


def retention_hours(log_kind: str) -> int:
    """Return the demo's configured retention period in hours."""
    periods = {"normal": 24, "audit": 2160}
    try:
        return periods[log_kind]
    except KeyError as exc:
        raise ValueError(f"Unknown demo log kind: {log_kind}") from exc
