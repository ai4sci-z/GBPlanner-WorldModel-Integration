package fsm

import "testing"

func TestRecorderOutputsNavLabSchema(t *testing.T) {
	recorder := NewRecorder(
		"example",
		"runtime",
		"hover",
		"run-1",
		"actual",
		"idle",
		[]State{{State: "idle"}, {State: "running"}, {State: "completed", Terminal: true}},
		[]Trigger{{Trigger: "start"}, {Trigger: "complete"}},
		[]Rule{
			{From: "idle", Trigger: "start", To: "running"},
			{From: "running", Trigger: "complete", To: "completed"},
		},
	)
	if err := recorder.Fire("start", "2026-06-27T00:00:00Z", true, "started", map[string]any{"source": "test"}, nil); err != nil {
		t.Fatalf("Fire(start) error = %v", err)
	}
	if err := recorder.Fire("complete", "2026-06-27T00:00:01Z", true, "completed", nil, nil); err != nil {
		t.Fatalf("Fire(complete) error = %v", err)
	}
	recorder.Complete()

	summary := recorder.Summary()
	if summary.SchemaVersion != SchemaVersion {
		t.Fatalf("schema version = %q, want %q", summary.SchemaVersion, SchemaVersion)
	}
	if summary.State != "completed" {
		t.Fatalf("state = %q, want completed", summary.State)
	}
	if !summary.OK || summary.Blocked {
		t.Fatalf("ok/blocked = %v/%v, want true/false", summary.OK, summary.Blocked)
	}
	if len(summary.Transitions) != 2 {
		t.Fatalf("transitions = %d, want 2", len(summary.Transitions))
	}
	if summary.Transitions[0].ReasonCode != "started" {
		t.Fatalf("transition reason = %q, want started", summary.Transitions[0].ReasonCode)
	}
	if recorder.DOTGraph() == "" {
		t.Fatal("DOTGraph() is empty")
	}
}
