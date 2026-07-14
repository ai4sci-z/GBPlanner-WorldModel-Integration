"""P0-2 acceptance sequences (Review 001): ready->silence, ready->not-ready,
controller restart, landing — enable must drop within the lease TTL."""
from enable_lease import EnableLease

READY = {"ok": True, "ready": True, "state": "controller_ready"}


def test_fail_closed_before_any_status():
    l = EnableLease(ttl_sec=3.0)
    assert l.enabled(0.0) is False


def test_ready_enables_and_renews():
    l = EnableLease(ttl_sec=3.0)
    l.observe(READY, 10.0)
    assert l.enabled(10.5) is True
    l.observe(READY, 12.0)
    assert l.enabled(14.9) is True


def test_silence_revokes_after_ttl():
    l = EnableLease(ttl_sec=3.0)
    l.observe(READY, 10.0)
    assert l.enabled(13.0) is True   # exactly at ttl edge
    assert l.enabled(13.1) is False  # stream died -> revoke


def test_not_ready_revokes_immediately():
    l = EnableLease(ttl_sec=3.0)
    l.observe(READY, 10.0)
    l.observe({"ok": False, "ready": False, "state": "waiting_for_pose"}, 10.5)
    assert l.enabled(10.6) is False


def test_controller_restart_revokes():
    l = EnableLease(ttl_sec=3.0)
    l.observe(READY, 10.0)
    l.observe({"ok": False, "ready": False, "state": "waiting_for_fcu_bootstrap"}, 11.0)
    assert l.enabled(11.1) is False
    # re-ready after restart re-enables (lease renewable, not one-shot)
    l.observe(READY, 20.0)
    assert l.enabled(20.5) is True


def test_landing_states_revoke():
    l = EnableLease(ttl_sec=3.0)
    for state in ("hold_position", "landing_complete", "waiting_for_task_completion"):
        l.observe(READY, 10.0)
        l.observe({"ok": True, "ready": True, "state": state}, 11.0)
        assert l.enabled(11.1) is False, state


def test_fuzzy_ok_alone_is_not_enough():
    l = EnableLease(ttl_sec=3.0)
    # the old latch accepted any of these; the lease must not
    l.observe({"ok": True}, 10.0)
    assert l.enabled(10.1) is False
    l.observe({"ready": True, "state": "controller_ready"}, 11.0)  # ok missing
    assert l.enabled(11.1) is False
    l.observe({"ok": True, "ready": True, "state": "exception"}, 12.0)
    assert l.enabled(12.1) is False


def test_malformed_input_ignored_but_fail_closed():
    l = EnableLease(ttl_sec=3.0)
    l.observe(None, 1.0)
    l.observe("garbage", 1.1)
    assert l.enabled(1.2) is False
    l.observe(READY, 2.0)
    l.observe(None, 2.5)  # malformed after ready: ignored, lease keeps running
    assert l.enabled(2.6) is True
