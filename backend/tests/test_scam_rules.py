import pytest
from pydantic import ValidationError

from app.risk.rules import analyse_explicit_request
from app.schemas import ThreatResult


def test_otp_theft_request_is_critical():
    result = analyse_explicit_request("Please share your OTP to unblock your account immediately.")
    assert result is not None
    assert result.scam_type == "otp_harvesting"
    assert result.risk_level == "critical"
    assert "urgency_or_threat" in result.signals


def test_hinglish_upi_pin_request_is_detected():
    result = analyse_explicit_request("Apna UPI PIN bataiye verification ke liye.")
    assert result is not None
    assert result.scam_type == "upi_pin_theft"


def test_legitimate_warning_is_not_detected():
    assert analyse_explicit_request("Never share your OTP with anyone.") is None


def test_negation_does_not_hide_later_pin_request():
    result = analyse_explicit_request("I won't ask for your OTP, but tell me your UPI PIN.")
    assert result is not None
    assert result.scam_type == "upi_pin_theft"


def test_remote_access_request_is_detected():
    result = analyse_explicit_request("Please install AnyDesk and allow remote access.")
    assert result is not None
    assert result.scam_type == "remote_access_manipulation"


def test_normal_bank_notification_is_safe():
    assert analyse_explicit_request("Your bank statement is ready in the mobile app.") is None


def test_reported_scam_is_not_misclassified_as_request():
    assert analyse_explicit_request("The fraudster asked me to share my OTP, but I refused.") is None


def test_benign_otp_arrival_question_is_not_flagged():
    assert analyse_explicit_request("Please tell me whether my OTP has arrived.") is None


def test_later_malicious_clause_is_not_masked_by_reported_scam():
    result = analyse_explicit_request("The fraudster asked me to share my OTP, but now tell me your UPI PIN.")
    assert result is not None
    assert result.scam_type == "upi_pin_theft"


def test_warning_against_remote_access_is_not_flagged():
    assert analyse_explicit_request("Do not install AnyDesk or share your screen with callers.") is None


def test_reported_remote_access_request_is_not_treated_as_current_caller_request():
    assert analyse_explicit_request("The scammer asked me to install AnyDesk, but I refused.") is None


def test_hinglish_negation_and_anaphora_cases():
    assert analyse_explicit_request("Don't share your OTP") is None
    assert analyse_explicit_request("Fraudster asked me for OTP") is None
    assert analyse_explicit_request("Tell me whether my OTP arrived") is None
    assert analyse_explicit_request("OTP mat batana") is None
    assert analyse_explicit_request("OTP share mat karo") is None
    assert analyse_explicit_request("I installed AnyDesk yesterday") is None

    pin = analyse_explicit_request("Give me your UPI PIN")
    assert pin is not None and pin.scam_type == "upi_pin_theft" and pin.risk_level == "critical"

    apna_otp = analyse_explicit_request("Apna OTP bata do")
    assert apna_otp is not None and apna_otp.scam_type == "otp_harvesting" and apna_otp.risk_level == "critical"

    anaphora_pin = analyse_explicit_request("Never share PIN, but tell me yours")
    assert anaphora_pin is not None and anaphora_pin.scam_type == "upi_pin_theft" and anaphora_pin.risk_level == "critical"

    reassurance_otp = analyse_explicit_request("Don't worry, just share your OTP")
    assert reassurance_otp is not None and reassurance_otp.scam_type == "otp_harvesting"

    bank_then_demand = analyse_explicit_request(
        "The bank confirmed that I should never share my OTP. Now please share your OTP with me."
    )
    assert bank_then_demand is not None and bank_then_demand.scam_type == "otp_harvesting"

    remote_ok = analyse_explicit_request("Install AnyDesk to resolve your issue")
    assert remote_ok is not None and remote_ok.scam_type == "remote_access_manipulation" and remote_ok.risk_level == "high"

    remote_neg_then_pos = analyse_explicit_request("Do not install AnyDesk, but install TeamViewer")
    assert remote_neg_then_pos is not None and remote_neg_then_pos.scam_type == "remote_access_manipulation"


def test_threat_result_rejects_semantic_contradictions():
    with pytest.raises(ValidationError):
        ThreatResult(
            risk_level="critical",
            risk_score=95,
            scam_detected=False,
            scam_type="none",
            explanation="Contradiction",
            recommended_action="end_call",
            warning_message="Warning",
        )
    with pytest.raises(ValidationError):
        ThreatResult(
            risk_level="high",
            risk_score=80,
            scam_detected=True,
            scam_type="otp_harvesting",
            signals=["credential_request"],
            explanation="Missing action escalation",
            recommended_action="continue_with_caution",
            warning_message="Warning",
        )
