from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SessionType = Literal["scam_demo", "assistant"]
SessionLanguage = Literal["hi-IN", "en-IN"]

_RISK_SCORE_BOUNDS: dict[str, tuple[int, int]] = {
    "low": (0, 39),
    "medium": (40, 69),
    "high": (70, 89),
    "critical": (90, 100),
}


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

    @model_validator(mode="after")
    def validate_semantic_consistency(self):
        min_score, max_score = _RISK_SCORE_BOUNDS[self.risk_level]
        if not (min_score <= self.risk_score <= max_score):
            raise ValueError(f"risk_score {self.risk_score} is inconsistent with risk_level {self.risk_level}")
        if self.scam_detected:
            if self.risk_level == "low":
                raise ValueError("scam_detected=True cannot have risk_level='low'")
            if self.recommended_action == "continue_with_caution":
                raise ValueError("scam_detected=True cannot recommend 'continue_with_caution'")
            if not self.explanation.strip():
                raise ValueError("scam_detected=True requires a non-empty explanation")
            if not self.signals and not self.evidence:
                raise ValueError("scam_detected=True requires at least one signal or evidence entry")
        else:
            if self.risk_level in {"high", "critical"}:
                raise ValueError("scam_detected=False cannot have high or critical risk_level")
            if self.recommended_action != "continue_with_caution":
                raise ValueError("scam_detected=False must use recommended_action='continue_with_caution'")
        return self
