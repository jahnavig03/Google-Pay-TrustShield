from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel
from trustshield_contracts import Decision, PolicyCitation, SafeAction, Signal


class MessageInputs(BaseModel):
    decision: Decision
    risk_type: str
    signals: list[Signal]
    safe_actions: list[SafeAction]
    safe_next_step: str
    citations: list[PolicyCitation]


class CustomerMessageWriter(Protocol):
    name: str

    async def write(self, inputs: MessageInputs) -> str: ...
