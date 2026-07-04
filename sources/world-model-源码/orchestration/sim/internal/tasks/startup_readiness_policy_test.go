package tasks

import (
	"testing"

	"navlab/orchestration-sim/internal/config"
)

func TestStartupReadinessPolicyWaitsWhenProgressIsVisible(t *testing.T) {
	decision := DecideStartupReadinessPolicyAction(config.StartupReadinessPolicyConfig{
		TimeoutSec:        35,
		GraceSec:          8,
		ProgressWindowSec: 3,
		RestartLimit:      1,
	}, StartupReadinessEvidence{
		MissionElapsedSec: 10,
		SerialByteDelta:   24,
	})

	if decision.Action != StartupReadinessActionWaitLonger ||
		decision.Reason != StartupReadinessReasonProgressObserved ||
		decision.SafeToRestart != true {
		t.Fatalf("decision = %#v", decision)
	}
}

func TestStartupReadinessPolicyFailsFastWhenNoProgressAndRestartDisabled(t *testing.T) {
	decision := DecideStartupReadinessPolicyAction(config.StartupReadinessPolicyConfig{
		TimeoutSec:        35,
		GraceSec:          8,
		ProgressWindowSec: 3,
		RestartLimit:      0,
	}, StartupReadinessEvidence{
		MissionElapsedSec: 9,
	})

	if decision.Action != StartupReadinessActionFailFast || decision.Reason != StartupReadinessReasonNoProgress {
		t.Fatalf("decision = %#v", decision)
	}
}

func TestStartupReadinessPolicyAllowsBoundedPrearmRestart(t *testing.T) {
	decision := DecideStartupReadinessPolicyAction(config.StartupReadinessPolicyConfig{
		TimeoutSec:        35,
		GraceSec:          8,
		ProgressWindowSec: 3,
		RestartLimit:      1,
	}, StartupReadinessEvidence{
		MissionElapsedSec: 9,
		RestartAttempts:   0,
	})

	if decision.Action != StartupReadinessActionRestartLeaf ||
		decision.Reason != StartupReadinessReasonRestartAllowed ||
		decision.SafeToRestart != true {
		t.Fatalf("decision = %#v", decision)
	}
}

func TestStartupReadinessPolicyForbidsRestartAfterTakeoffBoundary(t *testing.T) {
	for _, evidence := range []StartupReadinessEvidence{
		{MissionElapsedSec: 9, ArmedSeen: true},
		{MissionElapsedSec: 9, AirborneSeen: true},
		{MissionElapsedSec: 9, HoverHoldSeen: true},
	} {
		decision := DecideStartupReadinessPolicyAction(config.StartupReadinessPolicyConfig{
			TimeoutSec:        35,
			GraceSec:          8,
			ProgressWindowSec: 3,
			RestartLimit:      1,
		}, evidence)
		if decision.Action != StartupReadinessActionFailClosed ||
			decision.Reason != StartupReadinessReasonRestartForbidden ||
			decision.SafeToRestart != false {
			t.Fatalf("decision = %#v for evidence %#v", decision, evidence)
		}
	}
}
