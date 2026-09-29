from ses.config import _missing_or_placeholder


def test_secret_placeholders_are_rejected():
    assert _missing_or_placeholder(None)
    assert _missing_or_placeholder("")
    assert _missing_or_placeholder("change_me")
    assert _missing_or_placeholder("replace_with_a_real_secret")
    assert not _missing_or_placeholder("local-secret-value-2026")
