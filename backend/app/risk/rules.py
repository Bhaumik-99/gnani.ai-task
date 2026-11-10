import re

from app.schemas import Evidence, ThreatResult

_L = r"(?<![A-Za-z0-9\u0900-\u097F])"
_R = r"(?![A-Za-z0-9\u0900-\u097F])"


def _u(pattern: str) -> re.Pattern[str]:
    return re.compile(f"{_L}(?:{pattern}){_R}", re.I)


_CREDENTIAL = _u(
    r"one[- ]time password|o\s*t\s*p|u\s*p\s*i\s*pin|mpin|pin|cvv|cvc|password|passcode|card number|internet banking credentials"
    r"|ओटीपी|वन\s*टाइम\s*पासवर्ड|यूपीआई\s*पिन|एमपिन|पिन|सीवीवी|सीवीसी|पासवर्ड|पासकोड|कार्ड\s*नंबर"
)
_REQUEST = _u(
    r"share|tell|send|give|read(?:\s+out)?|confirm|provide|enter|type"
    r"|bata(?:iye|o|na)?|bhej(?:o|iye|na)?|bol(?:iye|o|na)?|de(?:na|jiye|\s+do|\s+dijiye)?"
    r"|बताइए|बताइये|बताओ|बता\s*दो|बता\s*देना|बोलिए|बोलो|भेजिए|भेजो|भेज\s*दो|भेज\s*देना|दीजिए|दे\s*दो|शेयर|दर्ज|डालो|एंटर"
)
_ANAPHORA = _u(r"yours|it|that|same|woh|wo|uska|apna\s+wala|वह|वो|उसको|उसे|अपना\s*वाला")
_REASSURANCE = _u(
    r"(?:don't|do not)\s+(?:worry|panic|be afraid)|no\s+(?:worries|problem)"
    r"|(?:chinta|tension|fikar)\s+(?:mat|na)\s+(?:karo|lo|kijiye)|ghabrao\s+mat"
    r"|(?:चिंता|टेंशन|फिक्र)\s+(?:मत|ना)\s+(?:करो|लो|कीजिए)|घबराओ\s+मत"
)
_NEGATION = _u(
    r"don't|do not|never|not|avoid|won't|will not|would not|should not|shouldn't"
    r"|mat|kabhi\s+mat|kabhi\s+nahi|nahi\s+(?:batana|bhejna|dena|share)|na\s+(?:share|batana|bhejna|dena|batao|bhejo)"
    r"|मत|कभी\s+मत|कभी\s+नहीं|मना|साझा\s+न\s+करें|नहीं\s+(?:बताना|भेजना|देना|शेयर)|न\s+(?:बताएं|बताओ|भेजें|शेयर)"
)
_URGENCY = _u(
    r"urgent|immediately|right now|unblock|blocked|block|suspend|freeze|turant|abhi|band"
    r"|तुरंत|अभी|फौरन|जल्दी|ब्लॉक|बंद|फ्रीज|सस्पेंड"
)
_IMPERSONATION = _u(
    r"bank|rbi|police|customs|courier|income tax|aadhaar|kyc"
    r"|बैंक|आरबीआई|पुलिस|कस्टम्स|कूरियर|इनकम\s*टैक्स|आधार|केवाईसी"
)
_REMOTE = _u(
    r"any\s*desk|team\s*viewer|screen sharing|remote access|apk"
    r"|एनी\s*डेस्क|टीम\s*व्यूअर|स्क्रीन\s*शेयर(?:िंग)?|रिमोट\s*एक्सेस|एपीके"
)
_REMOTE_INSTRUCTION = _u(
    r"install|download|open|share|give|allow|enable|grant"
    r"|इंस्टॉल|डाउनलोड|खोलो|खोलिए|चालू|अलाउ|ऑन"
)
_REMOTE_PAST_OR_SELF = _u(
    r"(?:i|we)\s+(?:have\s+|had\s+|already\s+)?(?:installed|downloaded|used|opened|enabled)"
    r"|(?:मैंने|हमने).*(?:किया\s+था|था|चुका\s+हूँ|चुके\s+हैं)"
)
_REPORTED = _u(
    r"(?:the\s+)?(?:scammer|fraudster|caller|person|someone|he|she|they)\s+(?:asked|told|said|requested)\s+(?:me|us|him|her|them)"
    r"|(?:i|we)\s+(?:was|were)\s+(?:asked|told)\s+(?:to|for)"
    r"|(?:caller|scammer|fraudster|kisi)\s+ne\s+(?:mujhse|humse)"
    r"|(?:स्कैमर|फ्रॉड|कॉलर|किसी|उसने|उन्होंने)\s+ने\s+(?:मुझसे|हमसे|मुझे|हमें)"
)
_OTP_STATUS = _u(
    r"(?:tell me|check|confirm)\s+(?:whether|if)\s+(?:my|the)\s+(?:otp|o\s*t\s*p)\s+(?:has\s+)?(?:arrived|arrive|been received|was received|came|come)"
    r"|(?:did|has)\s+(?:my|the)\s+(?:otp|o\s*t\s*p)\s+(?:arrived|arrive|come)"
    r"|otp\s+(?:aaya|aa\s+gaya)\s+kya"
    r"|(?:ओटीपी|मेरा\s+ओटीपी)\s+(?:आया|आ\s+गया)\s+(?:क्या|या\s+नहीं)"
)
_CLAUSE_SPLIT = re.compile(
    r"[.!?;,।:]|\b(?:but|however|although|though|yet|instead|actually|lekin|par|magar)\b|(?<![A-Za-z0-9\u0900-\u097F])(?:लेकिन|पर|मगर)(?![A-Za-z0-9\u0900-\u097F])",
    re.I,
)


def _split_clauses(text: str) -> list[str]:
    return [part.strip() for part in _CLAUSE_SPLIT.split(text) if part.strip()]


def _clause_is_negated(clause: str) -> bool:
    cleaned = _REASSURANCE.sub(" ", clause)
    return bool(_NEGATION.search(cleaned))


def _credential_category(credential: str) -> str:
    compact = re.sub(r"[\s-]+", "", credential.lower())
    if any(token in compact for token in ("upipin", "upi", "mpin", "यूपीआई", "एमपिन")) or compact in {"pin", "पिन"}:
        return "upi_pin_theft"
    if any(token in compact for token in ("otp", "onetimepassword", "ओटीपी", "वनटाइमपासवर्ड")):
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
