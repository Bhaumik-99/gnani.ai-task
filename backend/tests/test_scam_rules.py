from app.scam_rules import analyse_explicit_request


def test_otp_harvesting():
    result = analyse_explicit_request("Please share your OTP to unblock your account.")
    assert result is not None
    assert result.scam_detected
    assert result.risk_level == "critical"
    assert result.scam_type == "otp_harvesting"


def test_upi_pin_theft():
    result = analyse_explicit_request("Apna UPI PIN bataiye verification ke liye.")
    assert result is not None
    assert result.scam_type == "upi_pin_theft"


def test_benign_safety_warning_not_flagged():
    assert analyse_explicit_request("Never share your OTP with anyone.") is None


def test_no_sensitive_request_not_flagged():
    assert analyse_explicit_request("Your bank statement is ready.") is None


def test_empty_transcript():
    assert analyse_explicit_request("   ") is None
