from coach.backend.core.limits import RateLimiter


def make(start=0.0):
    t = [start]
    return t, RateLimiter(clock=lambda: t[0])


def test_allows_up_to_limit_then_refuses():
    _, rl = make()
    assert rl.allow("k", 2, 10)
    assert rl.allow("k", 2, 10)
    assert not rl.allow("k", 2, 10)


def test_window_slides():
    t, rl = make()
    assert rl.allow("k", 2, 10)
    t[0] = 5
    assert rl.allow("k", 2, 10)
    assert not rl.allow("k", 2, 10)
    t[0] = 10.1  # first event has left the window, second has not
    assert rl.allow("k", 2, 10)
    assert not rl.allow("k", 2, 10)


def test_refusals_are_not_recorded():
    t, rl = make()
    assert rl.allow("k", 1, 10)
    for _ in range(50):  # hammering while blocked must not extend the block
        assert not rl.allow("k", 1, 10)
    t[0] = 10.1
    assert rl.allow("k", 1, 10)


def test_keys_are_independent():
    _, rl = make()
    assert rl.allow("a", 1, 10)
    assert not rl.allow("a", 1, 10)
    assert rl.allow("b", 1, 10)
