"""Revocable enable lease for /gbp/enable (Review 001 P0-2).

Replaces the permanent latch ("any 'ok' or 'ready' ever seen => enabled
forever") with a lease that must be continuously renewed by strictly-ready
controller status and revokes immediately on degradation or silence.

Schema (verified against fcu_controller_runtime.py.tmpl, 2026-07-14):
  the controller publishes JSON where `ok` and `ready` carry the same
  controller_ready() boolean and `state` is "controller_ready" while flying
  under an armed+taken-off bootstrap; landing / restart phases publish other
  states ("hold_position", "waiting_for_fcu_bootstrap", "landing_complete",
  ...). Only the exact ready state renews the lease — a fuzzy `ok OR ready`
  is forbidden here.
"""

READY_STATE = "controller_ready"


class EnableLease:
    def __init__(self, ttl_sec: float = 3.0):
        self.ttl_sec = float(ttl_sec)
        self._last_ready_mono = None   # last strictly-ready status
        self._revoked = True           # fail-closed until first ready status

    def observe(self, status: dict, now_mono: float) -> None:
        """Feed one controller status message (already JSON-decoded)."""
        if not isinstance(status, dict):
            return
        strictly_ready = (
            status.get("ready") is True
            and status.get("ok") is True
            and status.get("state") == READY_STATE
        )
        if strictly_ready:
            self._last_ready_mono = now_mono
            self._revoked = False
        else:
            # Any newer non-ready status revokes immediately: landing,
            # controller restart (waiting_for_fcu_bootstrap), degraded pose,
            # exception states — no grace period.
            self._revoked = True

    def enabled(self, now_mono: float) -> bool:
        if self._revoked or self._last_ready_mono is None:
            return False
        # Silence revokes too: a dead controller must not keep intents alive.
        return (now_mono - self._last_ready_mono) <= self.ttl_sec
