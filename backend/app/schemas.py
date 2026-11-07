from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SessionType = Literal["scam_demo", "assistant"]
SessionLanguage = Literal["hi-IN", "en-IN"]


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_type: SessionType
    language: SessionLanguage = "hi-IN"


class Evidence(BaseModel):
    text: str = Field(min_length=1, max_length=240)
    category: str = Field(min_length=1, max_length=64)


class ThreatResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    risk_level: Literal["low", "medium", "high", "critical"]
    risk_score: int = Field(ge=0, le=100)
    confidence: float | None = Field(default=None, ge=0, le=1)
    scam_detected: bool
    scam_type: str = Field(max_length=80)
    signals: list[str] = Field(default_factory=list, max_length=12)
    evidence: list[Evidence] = Field(default_factory=list, max_length=12)
    explanation: str = Field(max_length=500)
    recommended_action: Literal["continue_with_caution", "warn_user", "end_call"]
    warning_message: str = Field(max_length=300)
