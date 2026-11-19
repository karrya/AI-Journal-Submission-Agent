"""Credential-free contracts for one-time confirmation challenges."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfirmationChallenge:
    id: str
    token: str
    summary_hash: str
