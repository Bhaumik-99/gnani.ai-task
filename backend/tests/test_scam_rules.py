from app.risk.rules import analyse_explicit_request


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
