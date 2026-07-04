package contractsgen_test

import (
	"os"
	"path/filepath"
	"testing"

	"google.golang.org/protobuf/encoding/protojson"
	"google.golang.org/protobuf/proto"
	orchestrationv1 "navlab/contracts/gen/go/navlab/orchestration/v1"
	runtimev1 "navlab/contracts/gen/go/navlab/runtime/v1"
	safetyv1 "navlab/contracts/gen/go/navlab/safety/v1"
	sensorsv1 "navlab/contracts/gen/go/navlab/sensors/v1"
)

func TestGoldenExamplesParseWithGeneratedTypes(t *testing.T) {
	tests := []struct {
		path    string
		message proto.Message
	}{
		{filepath.Join("orchestration", "sim_task_request.json"), &orchestrationv1.TaskRequest{}},
		{filepath.Join("orchestration", "real_task_result.json"), &orchestrationv1.TaskResult{}},
		{filepath.Join("orchestration", "doctor_result_blocked.json"), &orchestrationv1.DoctorResult{}},
		{filepath.Join("runtime", "sim_runtime_plan.json"), &runtimev1.RuntimePlan{}},
		{filepath.Join("runtime", "real_process_event.json"), &runtimev1.ProcessEvent{}},
		{filepath.Join("safety", "motor_debug_ack_failed.json"), &safetyv1.MavlinkAck{}},
		{filepath.Join("sensors", "real_source_evidence.json"), &sensorsv1.SourceEvidence{}},
	}
	for _, tt := range tests {
		t.Run(tt.path, func(t *testing.T) {
			data, err := os.ReadFile(filepath.Join("..", "..", "examples", tt.path))
			if err != nil {
				t.Fatal(err)
			}
			if err := (protojson.UnmarshalOptions{DiscardUnknown: true}).Unmarshal(data, tt.message); err != nil {
				t.Fatalf("protojson.Unmarshal(%s) error = %v", tt.path, err)
			}
		})
	}
}
