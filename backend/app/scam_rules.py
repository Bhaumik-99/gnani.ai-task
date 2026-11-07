"""Conservative local rules for an explicitly requested demo transcript."""
import re

from app.schemas import ThreatResult

_CREDENTIAL = re.compile(r"\b(otp|one[- ]time password|upi\s*pin|password|passcode|cvv)\b", re.I)
_REQUEST = re.compile(r"\b(share|tell|send|give|read|confirm|provide|bata|bataye|bataiye|bhej|bol)\b", re.I)
_NEGATION = re.compile(r"\b(don't|do not|never|mat|kabhi nahi|not share|never share)\b", re.I)
_URGENCY = re.compile(r"\b(block|blocked|urgent|immediately|suspend|band|turant|abhi)\b", re.I)


def analyse_explicit_request(transcript: str) -> ThreatResult | None:
    text = transcript.strip()
    if not text or not _CREDENTIAL.search(text) or not _REQUEST.search(text):
        return None
    if _NEGATION.search(text):
        return None
    match = _CREDENTIAL.search(text)
    assert match is not None
    credential = match.group(0).lower().replace(" ", "_")
    category = "upi_pin_theft" if "upi" in credential else (
        "otp_harvesting" if "otp" in credential or "one" in credential else "credential_harvesting"
    )
    evidence = [match.group(0)]
    if _URGENCY.search(text):
        evidence.append("urgency language")
    return ThreatResult(
        risk_level="critical", risk_score=98, scam_detected=True,
        scam_type=category, evidence=evidence,
        recommended_action="end_demo_call",
        warning_message="Suspected credential theft. Never share OTPs, UPI PINs or passwords.",
    )
