import re

from app.schemas import Evidence, ThreatResult

_CREDENTIAL = re.compile(r"\b(?:one[- ]time password|otp|upi\s*pin|pin|cvv|cvc|password|passcode|card number|internet banking credentials)\b", re.I)
_REQUEST = re.compile(r"\b(?:share|tell|send|give|read(?:\s+out)?|confirm|provide|enter|type|bata(?:iye|o)?|bhej(?:o)?|bol(?:iye|o)?)\b", re.I)
_NEGATION = re.compile(r"\b(?:don't|do not|never|not|won't|will not|would not|mat|kabhi\s+mat|kabhi\s+nahi|na\s+share)\b", re.I)
_URGENCY = re.compile(r"\b(?:urgent|immediately|right now|unblock|blocked|block|suspend|freeze|turant|abhi|band)\b", re.I)
_IMPERSONATION = re.compile(r"\b(?:bank|rbi|police|customs|courier|income tax|aadhaar|kyc)\b", re.I)
_REMOTE = re.compile(r"\b(?:anydesk|teamviewer|screen sharing|remote access|apk)\b", re.I)
_REPORTED = re.compile(r"\b(?:the\s+)?(?:scammer|fraudster|caller|person|someone|he|she|they)\s+(?:asked|told|said|requested)\s+(?:me|us|him|her|them)\b|\b(?:i|we)\s+(?:was|were)\s+(?:asked|told)\s+to\b", re.I)
_OTP_STATUS = re.compile(r"\b(?:tell me|check|confirm)\s+(?:whether|if)\s+(?:my|the)\s+otp\s+(?:has\s+)?(?:arrived|arrive|been received|was received)\b", re.I)


def _negated(text: str, start: int) -> bool:
    left = text[max(0, start - 90):start]
    clauses = re.split(r"[.!?;,:]|\b(?:but|however|lekin|par)\b", left, flags=re.I)
    return bool(_NEGATION.search(clauses[-1]))


def analyse_explicit_request(transcript: str) -> ThreatResult | None:
    text = " ".join(transcript.strip().split())
    if not text:
        return None
    separators = r"[.!?;,:]|\b(?:but|however|lekin|par)\b"
    selected = None
    for match in _CREDENTIAL.finditer(text):
        left_matches = list(re.finditer(separators, text[:match.start()], re.I))
        right = re.search(separators, text[match.end():], re.I)
        start = left_matches[-1].end() if left_matches else 0
        end = match.end() + (right.start() if right else len(text))
        clause = text[start:end]
        if not _REPORTED.search(clause) and not _OTP_STATUS.search(clause) and _REQUEST.search(clause) and not _negated(text, match.start()):
            selected = match
            break
    if selected is None:
        remote = _REMOTE.search(text)
        if remote and re.search(r"\b(?:install|download|open|share|give|allow)\b", text, re.I):
            return ThreatResult(
                risk_level="high", risk_score=88, scam_detected=True, scam_type="remote_access_manipulation",
                signals=["remote_access_request"],
                evidence=[Evidence(text=remote.group(0), category="remote_access_request")],
                explanation="The caller is asking the user to install or enable remote-access software.",
                recommended_action="end_call",
                warning_message="Do not install remote-access apps or share screen control with an unverified caller.",
            )
        return None

    credential = selected.group(0)
    normalized = credential.lower().replace(" ", "_")
    category = "upi_pin_theft" if "upi" in normalized or normalized == "pin" else (
        "otp_harvesting" if "otp" in normalized or "one-time" in normalized else "credential_harvesting"
    )
    left = text.rfind(".", 0, selected.start()) + 1
    clause_end = min((p for p in [text.find(mark, selected.end()) for mark in ".!?;,"] if p >= 0), default=len(text))
    evidence_text = text[left:clause_end].strip()[:180] or credential
    signals = ["credential_request"]
    evidence = [Evidence(text=evidence_text, category="credential_request")]
    urgency = _URGENCY.search(text)
    if urgency:
        signals.append("urgency_or_threat")
        evidence.append(Evidence(text=urgency.group(0), category="urgency"))
    impersonation = _IMPERSONATION.search(text)
    if impersonation:
        signals.append("institution_impersonation_context")
        evidence.append(Evidence(text=impersonation.group(0), category="impersonation_context"))
    return ThreatResult(
        risk_level="critical", risk_score=98, scam_detected=True, scam_type=category,
        signals=signals, evidence=evidence,
        explanation="The caller is requesting a sensitive authentication credential. Legitimate support should not ask for an OTP, UPI PIN, CVV or password.",
        recommended_action="end_call",
        warning_message="Never share an OTP, UPI PIN, CVV or password with a caller.",
    )
