from typing import Literal
from pydantic import BaseModel, Field

SessionType = Literal["scam_demo", "assistant"]


class SessionCreate(BaseModel):
    session_type: SessionType
    language: str = "hi-en"


class ThreatResult(BaseModel):
    risk_level: Literal["low", "medium", "high", "critical"]
    risk_score: int = Field(ge=0, le=100)
    scam_detected: bool
    scam_type: str
    evidence: list[str] = Field(default_factory=list)
    recommended_action: str
    warning_message: str
