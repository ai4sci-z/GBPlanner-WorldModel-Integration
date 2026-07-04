package helpers

import (
	"strings"
	"testing"
)

func TestMotionFoxgloveNotes(t *testing.T) {
	notes := MotionFoxgloveNotes(DefaultMotionGateSpec())
	if !strings.Contains(notes, "Motion status") || !strings.Contains(notes, "/navlab/motion/status") {
		t.Fatalf("notes missing motion topic:\n%s", notes)
	}
}

func TestMotionHelperMarkedPortedBasic(t *testing.T) {
	definition, err := DefaultRegistry().Get("motion")
	if err != nil {
		t.Fatal(err)
	}
	if definition.MigrationStatus != "ported_basic" {
		t.Fatalf("motion status = %q, want ported_basic", definition.MigrationStatus)
	}
}
