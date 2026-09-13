from pixelpilot.security import is_owner


def test_owner_true():
    assert is_owner(123, 123)


def test_owner_false():
    assert not is_owner(124, 123)
    assert not is_owner(None, 123)
    assert not is_owner(123, 0)
