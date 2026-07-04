package helpers

import "testing"

func TestDefaultRegistryContainsNonRealHelpers(t *testing.T) {
	registry := DefaultRegistry()
	definitions := registry.List()
	if len(definitions) < 10 {
		t.Fatalf("len(definitions) = %d, want at least 10", len(definitions))
	}
	for _, id := range []string{"artifacts", "sensors", "slam", "fcu-controller", "exploration-workflow", "nav2-navigation-workflow", "scan-robustness-workflow"} {
		if _, err := registry.Get(id); err != nil {
			t.Fatalf("Get(%q) error = %v", id, err)
		}
	}
}

func TestResolveRejectsUnknownHelper(t *testing.T) {
	registry := DefaultRegistry()
	if _, err := registry.Resolve([]string{"artifacts", "real-prepare"}); err == nil {
		t.Fatal("Resolve() error = nil, want error")
	}
}
