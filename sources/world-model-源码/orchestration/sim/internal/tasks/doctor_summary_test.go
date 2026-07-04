package tasks

import (
	"testing"

	"navlab/orchestration-sim/internal/config"
	simruntime "navlab/orchestration-sim/internal/runtime"
	"navlab/orchestration-sim/internal/tasks/helpers"
)

func TestBuildStaticDoctorSummary(t *testing.T) {
	summary := BuildStaticDoctorSummary(
		config.ProjectConfig{Runtime: config.RuntimeConfig{Mode: "simulation", Backend: "docker"}},
		Plan{
			TaskID: "hover",
			Execution: helpers.ExecutionPlan{
				ResultGates: []helpers.ResultGatePlan{
					{HelperID: "landing", Name: "landing_acceptance", Status: "ported_basic"},
				},
			},
		},
		"run-1",
		t.TempDir(),
		[]GeneratedRuntimeArtifact{{Type: "probe_script", Path: "probe.py"}},
		RuntimeSpecBundle{
			Services: []simruntime.ServiceSpec{{Name: "service"}},
			Probes:   []simruntime.ProbeSpec{{Name: "probe"}},
			Rosbags:  []simruntime.RosbagSpec{{Name: "rosbag"}},
		},
	)
	if !summary.OK || summary.Blocked || len(summary.Blockers) != 0 {
		t.Fatalf("summary status = %#v", summary)
	}
	if summary.DoctorStage != "static_sim_task_doctor" {
		t.Fatalf("DoctorStage = %q", summary.DoctorStage)
	}
	if !summary.Checks["runtime_specs_valid"] || !summary.Checks["runtime_artifacts_generated"] {
		t.Fatalf("checks = %#v", summary.Checks)
	}
	if summary.RuntimeSpecCounts.Services != 1 || len(summary.ResultGates) != 1 {
		t.Fatalf("summary = %#v", summary)
	}
}
