package tasks

import (
	"errors"
	"strings"
	"testing"

	"navlab/orchestration-sim/internal/config"
	simruntime "navlab/orchestration-sim/internal/runtime"
	"navlab/orchestration-sim/internal/tasks/helpers"
)

func TestBuildLiveRunSummaryRuntimeSuccessStillEvaluatesGateBlockers(t *testing.T) {
	summary := BuildLiveRunSummary(
		config.ProjectConfig{Runtime: config.RuntimeConfig{Mode: "simulation", Backend: "docker"}},
		config.TaskRuntimeConfig{
			Landing:       config.LandingConfig{HoverPolicy: "land_in_place", DefaultPolicy: "land_in_place"},
			FCUController: config.FCUControllerConfig{TakeoffAltM: 0.5},
			SlamHover:     config.SlamHoverConfig{HoverClaim: "evaluated"},
		},
		Plan{
			TaskID:            "hover",
			DurationSec:       90,
			SimulationProfile: "ideal",
			Execution: helpers.ExecutionPlan{
				ResultGates: []helpers.ResultGatePlan{
					{HelperID: "slam-hover", Name: "hover_gate", Inputs: []string{"probe.json"}, Outputs: []string{"blockers"}, Status: "ported_partial"},
				},
			},
		},
		"run-1",
		t.TempDir(),
		[]GeneratedRuntimeArtifact{{Type: "slam_runtime_config", Path: "slam_runtime.toml"}},
		RuntimeSpecBundle{
			Services: []simruntime.ServiceSpec{{Name: "slam"}},
			Probes:   []simruntime.ProbeSpec{{Name: "hover_probe"}},
			Rosbags:  []simruntime.RosbagSpec{{Name: "hover_rosbag"}},
		},
		RuntimeExecutionResult{ProbeResults: []simruntime.ProbeResult{{Name: "hover_probe", ReturnCode: 0}}},
		nil,
	)
	if summary.OK || !summary.Blocked {
		t.Fatalf("summary status = ok:%v blocked:%v", summary.OK, summary.Blocked)
	}
	if summary.RuntimeSpecCounts.Services != 1 || summary.RuntimeSpecCounts.Probes != 1 || summary.RuntimeSpecCounts.Rosbags != 1 {
		t.Fatalf("runtime counts = %#v", summary.RuntimeSpecCounts)
	}
	if len(summary.ResultGates) != 1 || summary.GateParity.Status != "evaluated_from_runtime_artifacts" {
		t.Fatalf("summary gates = %#v parity=%#v", summary.ResultGates, summary.GateParity)
	}
	if !blockersContainPrefix(summary.BlockerCodes, helpers.LandingNotEvaluatedBlocker) {
		t.Fatalf("blockers = %#v, want landing blocker", summary.Blockers)
	}
	if summary.SchemaVersion != "navlab.orchestration.task_result.v1" || summary.Status != "TASK_STATUS_BLOCKED" {
		t.Fatalf("summary contract fields = schema:%q status:%q", summary.SchemaVersion, summary.Status)
	}
	if summary.StartupReadinessPolicy["owner"] != "go_runtime_config" ||
		summary.StartupReadinessPolicy["timeout_sec"] != float64(35) {
		t.Fatalf("startup readiness policy = %#v", summary.StartupReadinessPolicy)
	}
	if summary.SourceEvidence["rangefinderSource"] != "ardupilot_serial7_benewake_tfmini" ||
		summary.SourceEvidence["rangefinderSimulationFidelity"] != "benewake_serial_emulated" {
		t.Fatalf("rangefinder evidence = %#v", summary.SourceEvidence)
	}
}

func TestBuildLiveRunSummaryFailureRecordsBlocker(t *testing.T) {
	summary := BuildLiveRunSummary(
		config.ProjectConfig{Runtime: config.RuntimeConfig{Mode: "simulation", Backend: "docker"}},
		config.TaskRuntimeConfig{},
		Plan{TaskID: "hover"},
		"run-1",
		t.TempDir(),
		nil,
		RuntimeSpecBundle{},
		RuntimeExecutionResult{},
		errors.New("start service slam: boom"),
	)
	if summary.OK || !summary.Blocked {
		t.Fatalf("summary status = ok:%v blocked:%v", summary.OK, summary.Blocked)
	}
	if summary.RuntimeError == "" || !blockersContainPrefix(summary.BlockerCodes, "runtime_execution_failed") {
		t.Fatalf("summary error/blockers = %q %#v", summary.RuntimeError, summary.Blockers)
	}
	if summary.Status != "TASK_STATUS_ERROR" || summary.ExitCode != 1 {
		t.Fatalf("summary status = %q exitCode=%d", summary.Status, summary.ExitCode)
	}
}

func blockersContainPrefix(blockers []string, prefix string) bool {
	for _, blocker := range blockers {
		if strings.HasPrefix(blocker, prefix) {
			return true
		}
	}
	return false
}
