import re

from app.schemas import Evidence, ThreatResult

_CREDENTIAL = re.compile(
    r"\b(?:one[- ]time password|otp|upi\s*pin|pin|cvv|cvc|password|passcode|card number|internet banking credentials)\b",
    re.I,
)
_REQUEST = re.compile(
    r"\b(?:share|tell|send|give|read(?:\s+out)?|confirm|provide|enter|type|bata(?:iye|o|na)?|bhej(?:o|iye|na)?|bol(?:iye|o|na)?|de(?:na|jiye|\s+do|\s+dijiye)?)\b",
    re.I,
)
_ANAPHORA = re.compile(r"\b(?:yours|it|that|same|woh|wo|uska|apna\s+wala)\b", re.I)
_REASSURANCE = re.compile(
    r"\b(?:don't|do not)\s+(?:worry|panic|be afraid)|no\s+(?:worries|problem)|(?:chinta|tension|fikar)\s+(?:mat|na)\s+(?:karo|lo|kijiye)|ghabrao\s+mat\b",
    re.I,
)
_NEGATION = re.compile(
    r"\b(?:don't|do not|never|not|avoid|won't|will not|would not|should not|shouldn't|mat|kabhi\s+mat|kabhi\s+nahi|nahi\s+(?:batana|bhejna|dena|share)|na\s+(?:share|batana|bhejna|dena|batao|bhejo))\b",
    re.I,
)
_URGENCY = re.compile(r"\b(?:urgent|immediately|right now|unblock|blocked|block|suspend|freeze|turant|abhi|band)\b", re.I)
_IMPERSONATION = re.compile(r"\b(?:bank|rbi|police|customs|courier|income tax|aadhaar|kyc)\b", re.I)
_REMOTE = re.compile(r"\b(?:anydesk|teamviewer|screen sharing|remote access|apk)\b", re.I)
_REMOTE_INSTRUCTION = re.compile(r"\b(?:install|download|open|share|give|allow|enable|grant)\b", re.I)
_REMOTE_PAST_OR_SELF = re.compile(
    r"\b(?:i|we)\s+(?:have\s+|had\s+|already\s+)?(?:installed|downloaded|used|opened|enabled)\b",
    re.I,
)
_REPORTED = re.compile(
    r"\b(?:the\s+)?(?:scammer|fraudster|caller|person|someone|he|she|they)\s+(?:asked|told|said|requested)\s+(?:me|us|him|her|them)\b"
    r"|\b(?:i|we)\s+(?:was|were)\s+(?:asked|told)\s+(?:to|for)\b"
    r"|\b(?:caller|scammer|fraudster|kisi)\s+ne\s+(?:mujhse|humse)\b",
    re.I,
)
_OTP_STATUS = re.compile(
    r"\b(?:tell me|check|confirm)\s+(?:whether|if)\s+(?:my|the)\s+otp\s+(?:has\s+)?(?:arrived|arrive|been received|was received|came|come)\b"
    r"|\b(?:did|has)\s+(?:my|the)\s+otp\s+(?:arrived|arrive|come)\b"
    r"|\botp\s+(?:aaya|aa\s+gaya)\s+kya\b",
    re.I,
)
_CLAUSE_SPLIT = re.compile(
    r"[.!?;,:]|\b(?:but|however|although|though|yet|instead|actually|lekin|par|magar)\b",
    re.I,
)


def _split_clauses(text: str) -> list[str]:
    return [part.strip() for part in _CLAUSE_SPLIT.split(text) if part.strip()]


def _clause_is_negated(clause: str) -> bool:
    cleaned = _REASSURANCE.sub(" ", clause)
    return bool(_NEGATION.search(cleaned))


def _credential_category(credential: str) -> str:
    normalized = credential.lower().replace(" ", "_")
    if "upi" in normalized or normalized == "pin":
        return "upi_pin_theft"
    if "otp" in normalized or "one-time" in normalized:
        return "otp_harvesting"
    return "credential_harvesting"


def _build_credential_threat(text: str, evidence_clause: str, category: str) -> ThreatResult:
    signals = ["credential_request"]
    evidence = [Evidence(text=evidence_clause[:180] or category, category="credential_request")]
    urgency = _URGENCY.search(text)
    if urgency:
        signals.append("urgency_or_threat")
        evidence.append(Evidence(text=urgency.group(0), category="urgency"))
    impersonation = _IMPERSONATION.search(text)
    if impersonation:
        signals.append("institution_impersonation_context")
        evidence.append(Evidence(text=impersonation.group(0), category="impersonation_context"))
    return ThreatResult(
        risk_level="critical",
        risk_score=98,
        scam_detected=True,
        scam_type=category,
        signals=signals,
        evidence=evidence,
        explanation="The caller is requesting a sensitive authentication credential. Legitimate support should not ask for an OTP, UPI PIN, CVV or password.",
        recommended_action="end_call",
        warning_message="Never share an OTP, UPI PIN, CVV or password with a caller.",
    )


def analyse_explicit_request(transcript: str) -> ThreatResult | None:
    text = " ".join(transcript.strip().split())
    if not text:
        return None

    clauses = _split_clauses(text)
    last_credential: str | None = None

    for clause in clauses:
        reported = bool(_REPORTED.search(clause))
        status_check = bool(_OTP_STATUS.search(clause))
        negated = _clause_is_negated(clause)
        cred_match = _CREDENTIAL.search(clause)

        if cred_match:
            last_credential = cred_match.group(0)
            if not reported and not status_check and not negated and _REQUEST.search(clause):
                return _build_credential_threat(text, clause, _credential_category(last_credential))
            continue

        if last_credential and not reported and not status_check and not negated:
            if _REQUEST.search(clause) and _ANAPHORA.search(clause):
                return _build_credential_threat(text, clause, _credential_category(last_credential))

    for clause in clauses:
        if not _REMOTE.search(clause):
            continue
        if _REPORTED.search(clause) or _REMOTE_PAST_OR_SELF.search(clause) or _clause_is_negated(clause):
            continue
        if _REMOTE_INSTRUCTION.search(clause):
            return ThreatResult(
                risk_level="high",
                risk_score=88,
                scam_detected=True,
                scam_type="remote_access_manipulation",
                signals=["remote_access_request"],
                evidence=[Evidence(text=clause[:180], category="remote_access_request")],
                explanation="The caller is asking the user to install or enable remote-access software.",
                recommended_action="end_call",
                warning_message="Do not install remote-access apps or share screen control with an unverified caller.",
            )

    return None
