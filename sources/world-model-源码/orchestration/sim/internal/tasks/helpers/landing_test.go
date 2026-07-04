package helpers

import "testing"

func TestDefaultLandingRequiresReturnHome(t *testing.T) {
	summary := DefaultLanding(Config{Policy: PolicyReturnHomeThenLand, RequireDisarm: true})
	if !summary.ReturnHome.Required {
		t.Fatal("ReturnHome.Required = false, want true")
	}
	if len(summary.Blockers) != 1 || summary.Blockers[0] != LandingNotEvaluatedBlocker {
		t.Fatalf("blockers = %#v", summary.Blockers)
	}
}

func TestBuildAcceptanceBlocksGazeboTruthInput(t *testing.T) {
	acceptance := BuildAcceptance("simulation", Config{
		Policy:                 PolicyLandInPlace,
		UsesGazeboTruthAsInput: true,
	}, nil, false)
	if !acceptance.Blocked {
		t.Fatal("Blocked = false, want true")
	}
	found := false
	for _, blocker := range acceptance.Blockers {
		if blocker == GazeboTruthLandingInputBlocker {
			found = true
		}
	}
	if !found {
		t.Fatalf("blockers = %#v, want %q", acceptance.Blockers, GazeboTruthLandingInputBlocker)
	}
}
