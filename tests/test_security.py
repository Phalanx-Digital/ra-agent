from aura_link.security import constant_time_token_valid


def test_token_validation() -> None:
    assert constant_time_token_valid("secret", "secret")
    assert not constant_time_token_valid("wrong", "secret")
    assert not constant_time_token_valid("", "secret")

