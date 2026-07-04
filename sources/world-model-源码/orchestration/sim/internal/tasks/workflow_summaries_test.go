package tasks

import (
	"context"
	"errors"
	"path/filepath"
	"testing"
	"time"

	"navlab/orchestration-sim/internal/config"
	simruntime "navlab/orchestration-sim/internal/runtime"
	"navlab/orchestration-sim/internal/tasks/helpers"
)

func TestBuildSimPrepareSummaryPlansServicesAndResources(t *testing.T) {
	artifactDir := t.TempDir()
	bundle := RuntimeSpecBundle{
		Services: []simruntime.ServiceSpec{{
			Name:        "slam_backend",
			Image:       "navlab/slam:test",
			Command:     []string{"bash", "-lc", "ros2 launch slam"},
			CWD:         "/workspace",
			Volumes:     []simruntime.VolumeMount{{Source: "/repo", Target: "/workspace"}},
			Networks:    []string{"host"},
			Required:    true,
			ServiceRole: "slam",
			LogPath:     filepath.Join(artifactDir, "runtime/logs/slam_backend.start.log"),
		}},
		Probes: []simruntime.ProbeSpec{{
			Name:        "frame_contract_probe",
			Image:       "navlab/official-baseline:test",
			Command:     []string{"bash", "-lc", "python3 probe.py"},
			OutputPath:  filepath.Join(artifactDir, "probes/frame_contract.json"),
			TimeoutSec:  30,
			Required:    true,
			ServiceRole: "frame-contract",
		}},
		Rosbags: []simruntime.RosbagSpec{{
			Name:          "task_rosbag",
			Image:         "navlab/official-baseline:test",
			TopicsProfile: filepath.Join(artifactDir, "profiles/task_rosbag.txt"),
			OutputPath:    filepath.Join(artifactDir, "rosbag/task_rosbag"),
			DurationSec:   10,
			Storage:       "mcap",
			Required:      true,
			ServiceRole:   "rosbag",
		}},
	}
	summary := BuildSimPrepareSummary(
		config.ProjectConfig{
			Runtime: config.RuntimeConfig{Mode: "simulation", Backend: "docker"},
			Orchestration: config.OrchestrationConfig{
				Runtime: config.OrchestrationRuntimeConfig{
					Docker: config.DockerRuntimeConfig{WorkspaceContainerPath: "/workspace"},
				},
			},
		},
		Plan{TaskID: "hover"},
		"run-1",
		artifactDir,
		[]GeneratedRuntimeArtifact{{Type: "slam_runtime_config", Path: filepath.Join(artifactDir, "runtime/config/slam_runtime.toml")}},
		bundle,
		filepath.Join(artifactDir, "runtime_plan.json"),
	)

	if summary.PrepareClaim != "planned_service_probe_resource_artifacts_no_runtime_start" {
		t.Fatalf("PrepareClaim = %q", summary.PrepareClaim)
	}
	if len(summary.ServicePlan) != 1 || len(summary.ProbePlan) != 1 || len(summary.RosbagPlan) != 1 {
		t.Fatalf("plan counts = services:%d probes:%d rosbags:%d", len(summary.ServicePlan), len(summary.ProbePlan), len(summary.RosbagPlan))
	}
	if len(summary.ResourceProvenance.Images) != 2 || summary.ResourceProvenance.DockerDaemonClaim == "" {
		t.Fatalf("resource provenance = %#v", summary.ResourceProvenance)
	}
	if !summary.ForbiddenInputAudit.OK || summary.ForbiddenInputAudit.ScannedContexts == 0 {
		t.Fatalf("forbidden audit = %#v", summary.ForbiddenInputAudit)
	}
	if summary.RuntimeSideEffects.StartedServices || summary.RuntimeSideEffects.StartedProbes || summary.RuntimeSideEffects.StartedRosbags {
		t.Fatalf("prepare started runtime side effects: %#v", summary.RuntimeSideEffects)
	}
	if !summary.NodeResult.OK || summary.NodeResult.ID != "prepare" {
		t.Fatalf("node result = %#v", summary.NodeResult)
	}
}

func TestBuildSimWorkflowBundleWithLiveResourceProbeBlocksMissingImageWithoutStartingServices(t *testing.T) {
	client := &fakeDockerResourceProbeClient{
		missingImages: map[string]bool{"missing/image:test": true},
	}
	bundle := RuntimeSpecBundle{
		Services: []simruntime.ServiceSpec{{
			Name:     "missing_service",
			Image:    "missing/image:test",
			Command:  []string{"bash", "-lc", "should not run"},
			Networks: []string{"host"},
		}},
	}
	workflow := BuildSimWorkflowBundleWithOptions(
		config.ProjectConfig{Runtime: config.RuntimeConfig{Mode: "simulation", Backend: "docker"}},
		config.TaskConfig{ID: "hover"},
		config.TaskRuntimeConfig{},
		Plan{TaskID: "hover", DurationSec: 10, SimulationProfile: "official", Helpers: []helpers.Definition{{ID: "runtime"}}},
		"run-1",
		t.TempDir(),
		t.TempDir(),
		[]GeneratedRuntimeArtifact{{Type: "runtime_config", Path: "runtime/config/example.toml"}},
		bundle,
		"runtime_plan.json",
		SimWorkflowOptions{LiveResourceCheck: true, DockerResourceClient: client},
	)

	if !workflow.DoctorResult.Blocked {
		t.Fatalf("DoctorResult.Blocked = false, want true")
	}
	if workflow.Preflight.Checks["images_available"].Status != "fail" {
		t.Fatalf("images_available = %#v", workflow.Preflight.Checks["images_available"])
	}
	if workflow.Prepare.ResourceProvenance.DockerDaemonClaim != "live_checked_ok" {
		t.Fatalf("resource provenance = %#v", workflow.Prepare.ResourceProvenance)
	}
	if workflow.Preflight.LiveResourceProbe.Provenance.Client != "docker-sdk" {
		t.Fatalf("live probe provenance = %#v", workflow.Preflight.LiveResourceProbe.Provenance)
	}
	if client.probeDaemonCalls != 1 || client.inspectImageCalls != 1 || client.inspectNetworkCalls != 0 {
		t.Fatalf("fake sdk calls daemon=%d image=%d network=%d", client.probeDaemonCalls, client.inspectImageCalls, client.inspectNetworkCalls)
	}
}

func TestBuildSimLiveWorkflowSummaryReplacesRuntimeAndGateNodes(t *testing.T) {
	base := BuildSimWorkflowSummary("hover", "run-1", []WorkflowNodeResult{
		workflowNode("preflight", "preflight", workflowNodeOptions{Mode: "dry_run"}),
		workflowNode("prepare", "prepare", workflowNodeOptions{Mode: "dry_run"}),
		workflowNode("common-doctor", "common-doctor", workflowNodeOptions{Mode: "dry_run"}),
		workflowNode("task-doctor", "task-doctor", workflowNodeOptions{Mode: "dry_run"}),
		skippedWorkflowNode("runtime-execute", "runtime-execute", "dry_run_or_prepare_runtime_execute_not_started"),
		skippedWorkflowNode("gate-evaluate", "gate-evaluate", "dry_run_or_prepare_gate_evaluate_not_started"),
	})
	summary := LiveRunSummary{
		OK:     true,
		TaskID: "hover",
		RunID:  "run-1",
		RuntimeSpecCounts: RuntimeSpecCounts{
			Services: 1,
			Probes:   1,
			Rosbags:  1,
		},
		RuntimeExecution: RuntimeExecutionResult{
			ServiceHandles: []simruntime.RuntimeHandle{{ServiceName: "slam", StartedAt: time.Now()}},
			ProbeResults:   []simruntime.ProbeResult{{Name: "probe", ReturnCode: 0}},
			RosbagHandles:  []simruntime.RuntimeHandle{{ServiceName: "rosbag", FinalizeOK: true}},
		},
		GateEvaluation: GateEvaluation{
			OK:      true,
			Landing: helpers.Acceptance{OK: true},
		},
	}

	workflow := BuildSimLiveWorkflowSummary(base, summary)
	if len(workflow.Nodes) != 6 {
		t.Fatalf("node count = %d", len(workflow.Nodes))
	}
	if workflow.Nodes[4].ID != "runtime-execute" || workflow.Nodes[4].Status != "ok" || workflow.Nodes[4].Skipped {
		t.Fatalf("runtime node = %#v", workflow.Nodes[4])
	}
	if workflow.Nodes[5].ID != "gate-evaluate" || workflow.Nodes[5].Status != "ok" || workflow.Nodes[5].Skipped {
		t.Fatalf("gate node = %#v", workflow.Nodes[5])
	}
	if _, legacy := workflow.Nodes[4].Evidence["node_id"]; legacy {
		t.Fatalf("legacy node evidence leaked: %#v", workflow.Nodes[4].Evidence)
	}
}

type fakeDockerResourceProbeClient struct {
	missingImages       map[string]bool
	missingNetworks     map[string]bool
	probeDaemonCalls    int
	inspectImageCalls   int
	inspectNetworkCalls int
}

func (client *fakeDockerResourceProbeClient) ProbeDaemon(ctx context.Context) (simruntime.DockerDaemonProbe, error) {
	client.probeDaemonCalls++
	return simruntime.DockerDaemonProbe{
		Host:            "unix:///var/run/docker.sock",
		ServerVersion:   "test-server",
		APIVersion:      "1.99",
		OSType:          "linux",
		OperatingSystem: "test-os",
		Architecture:    "amd64",
		DockerRootDir:   "/var/lib/docker",
		SecurityOptions: []string{"name=seccomp"},
	}, nil
}

func (client *fakeDockerResourceProbeClient) InspectImage(ctx context.Context, imageRef string) (simruntime.DockerImageProbe, error) {
	client.inspectImageCalls++
	if client.missingImages[imageRef] {
		return simruntime.DockerImageProbe{}, errors.New("image not found")
	}
	return simruntime.DockerImageProbe{
		Image:    imageRef,
		ID:       "sha256:1234567890abcdef",
		RepoTags: []string{imageRef},
		OS:       "linux",
		Arch:     "amd64",
	}, nil
}

func (client *fakeDockerResourceProbeClient) InspectNetwork(ctx context.Context, network string) (simruntime.DockerNetworkProbe, error) {
	client.inspectNetworkCalls++
	if client.missingNetworks[network] {
		return simruntime.DockerNetworkProbe{}, errors.New("network not found")
	}
	return simruntime.DockerNetworkProbe{Name: network, ID: "network-1234567890", Driver: "bridge", Scope: "local"}, nil
}

func TestBuildDefaultSimTaskDoctorSummaryRecordsNotApplicableSpecificDoctor(t *testing.T) {
	summary := BuildDefaultSimTaskDoctorSummary(
		config.ProjectConfig{Runtime: config.RuntimeConfig{Mode: "simulation", Backend: "docker"}},
		config.TaskConfig{ID: "exploration"},
		config.TaskRuntimeConfig{},
		Plan{
			TaskID:            "exploration",
			DurationSec:       15,
			SimulationProfile: "official",
			Helpers:           nil,
		},
		"run-1",
		t.TempDir(),
		"/tmp/runtime_plan.json",
	)

	if summary.TaskDoctorClaim != "default" {
		t.Fatalf("TaskDoctorClaim = %q", summary.TaskDoctorClaim)
	}
	if summary.TaskSpecificDoctorClaim != "not_applicable" {
		t.Fatalf("TaskSpecificDoctorClaim = %q", summary.TaskSpecificDoctorClaim)
	}
	if summary.Checks["task_specific_doctor"].Status != "not_applicable" {
		t.Fatalf("task_specific_doctor check = %#v", summary.Checks["task_specific_doctor"])
	}
	if summary.NodeResult.OK {
		t.Fatalf("summary should block when required helpers are missing: %#v", summary.NodeResult)
	}
}

func TestBuildTaskDoctorSummaryImplementsHoverDoctor(t *testing.T) {
	runtimeConfig := config.TaskRuntimeConfig{
		FCUController: config.FCUControllerConfig{TakeoffAltM: 0.5, TakeoffMinHeightM: 0.15, TakeoffMinHeightRatio: 0.35},
		SlamHover: config.SlamHoverConfig{
			SlamOdomTopic:             "/slam/odom",
			ExternalNavInputOdomTopic: "/slam/odom",
			ExternalNavStatusTopic:    "/external_nav/status",
			HoverSpanTargetM:          0.10,
			HoverSpanHardCapM:         0.15,
		},
		Landing: config.LandingConfig{Enabled: true, HoverPolicy: "ap_land_mode_after_hover", MaxLandingDurationSec: 35, RequireDisarm: true, RequireMotorsSafe: true},
	}
	summary := BuildDefaultSimTaskDoctorSummary(
		config.ProjectConfig{Runtime: config.RuntimeConfig{Mode: "simulation", Backend: "docker"}},
		config.TaskConfig{ID: "hover"},
		runtimeConfig,
		Plan{TaskID: "hover", DurationSec: 90, SimulationProfile: ProfileSlamDirectNoOdomPrior, Helpers: []helpers.Definition{{ID: "slam-hover"}}},
		"run-1",
		t.TempDir(),
		"/tmp/runtime_plan.json",
	)
	if summary.TaskSpecificDoctorClaim != "implemented" || !summary.NodeResult.OK {
		t.Fatalf("hover task doctor = %#v", summary)
	}
	if summary.Checks["hover_profile_mainline"].Status != "pass" {
		t.Fatalf("hover_profile_mainline = %#v", summary.Checks["hover_profile_mainline"])
	}
}

func TestBuildTaskDoctorSummaryImplementsNavigationDoctor(t *testing.T) {
	runtimeConfig := config.TaskRuntimeConfig{
		Nav2: config.Nav2Config{
			Enabled: true, Profile: "indoor_2d", GlobalFrame: "map", OdomFrame: "odom", BaseFrame: "base_link", ScanTopic: "/scan", MapTopic: "/map",
			Costmap: config.Nav2CostmapConfig{GlobalCostmapTopic: "/global", LocalCostmapTopic: "/local", RequiredLayers: []string{"static_layer"}, MaxCostmapAgeSec: 1.5, HealthTopic: "/health"},
		},
		NavigationMission: config.NavigationMissionConfig{
			Strategy: "bounded_frontier", GoalFrame: "map", NavigationWindowSec: 120, MinAcceptedGoals: 2,
			BoundedGoals: []config.NavigationGoalConfig{{ID: "a"}, {ID: "b"}},
		},
		NavigationAdapter: config.NavigationAdapterConfig{MaxXYSpeedMPS: 0.25, FixedAltitudeM: 0.8, StopOnStaleCostmap: true, StopOnStaleSlam: true},
	}
	summary := BuildDefaultSimTaskDoctorSummary(
		config.ProjectConfig{Runtime: config.RuntimeConfig{Mode: "simulation", Backend: "docker"}},
		config.TaskConfig{ID: "navigation"},
		runtimeConfig,
		Plan{TaskID: "navigation", DurationSec: 360, SimulationProfile: ProfileIdeal, Helpers: []helpers.Definition{{ID: "nav2-navigation-workflow"}}},
		"run-1",
		t.TempDir(),
		"/tmp/runtime_plan.json",
	)
	if summary.TaskSpecificDoctorClaim != "implemented" || !summary.NodeResult.OK {
		t.Fatalf("navigation task doctor = %#v", summary)
	}
	if summary.Checks["navigation_no_truth_input"].Status != "pass" {
		t.Fatalf("navigation_no_truth_input = %#v", summary.Checks["navigation_no_truth_input"])
	}
}

func TestBuildTaskDoctorSummaryImplementsScanRobustnessDoctor(t *testing.T) {
	runtimeConfig := config.TaskRuntimeConfig{
		AirframeDisturbance: config.AirframeDisturbanceConfig{Profile: ProfileRealistic},
		AirframeDisturbanceGate: config.AirframeDisturbanceGateConfig{
			ProfileSet:       []string{ProfileIdeal, ProfileRealistic},
			RequiredProfiles: []string{ProfileIdeal, ProfileRealistic},
		},
	}
	summary := BuildDefaultSimTaskDoctorSummary(
		config.ProjectConfig{Runtime: config.RuntimeConfig{Mode: "simulation", Backend: "docker"}},
		config.TaskConfig{ID: "scan-robustness"},
		runtimeConfig,
		Plan{TaskID: "scan-robustness", DurationSec: 240, SimulationProfile: ProfileRealistic, Helpers: []helpers.Definition{{ID: "scan-stabilization"}, {ID: "scan-robustness-workflow"}}},
		"run-1",
		t.TempDir(),
		"/tmp/runtime_plan.json",
	)
	if summary.TaskSpecificDoctorClaim != "implemented" || !summary.NodeResult.OK {
		t.Fatalf("scan robustness task doctor = %#v", summary)
	}
	if summary.Checks["scan_stabilization_config"].Status != "planned_from_helper_defaults" {
		t.Fatalf("scan_stabilization_config = %#v", summary.Checks["scan_stabilization_config"])
	}
}

func TestBuildSimLiveCommonDoctorSummaryUsesRuntimeProbeEvidence(t *testing.T) {
	summary := BuildSimLiveCommonDoctorSummary(
		config.ProjectConfig{Runtime: config.RuntimeConfig{Mode: "simulation", Backend: "docker"}},
		Plan{
			TaskID: "hover",
			Execution: helpers.ExecutionPlan{
				ROSProbes: []helpers.ROSProbePlan{{
					Name:   "frame_contract_probe",
					Topics: []string{"/scan", "/tf", "/tf_static"},
				}},
			},
		},
		"run-1",
		RuntimeSpecBundle{
			Services: []simruntime.ServiceSpec{{Name: "service"}},
			Probes:   []simruntime.ProbeSpec{{Name: "frame_contract_probe", Required: true}},
			Rosbags:  []simruntime.RosbagSpec{{Name: "rosbag"}},
		},
		RuntimeExecutionResult{
			ServiceHandles: []simruntime.RuntimeHandle{{ServiceName: "service"}},
			RosbagHandles:  []simruntime.RuntimeHandle{{ServiceName: "rosbag", FinalizeOK: true, FinalizeStatus: "metadata_ready", MetadataPath: "rosbag/metadata.yaml"}},
			ProbeResults:   []simruntime.ProbeResult{{Name: "frame_contract_probe", ReturnCode: 0}},
		},
		nil,
	)

	if !summary.NodeResult.OK {
		t.Fatalf("live common doctor = %#v", summary.NodeResult)
	}
	if summary.TopicFreshness["/scan"].Status != "fresh_by_probe" {
		t.Fatalf("/scan freshness = %#v", summary.TopicFreshness["/scan"])
	}
}

func TestBuildSimLiveCommonDoctorSummaryBlocksMissingRequiredProbe(t *testing.T) {
	summary := BuildSimLiveCommonDoctorSummary(
		config.ProjectConfig{Runtime: config.RuntimeConfig{Mode: "simulation", Backend: "docker"}},
		Plan{
			TaskID: "hover",
			Execution: helpers.ExecutionPlan{
				ROSProbes: []helpers.ROSProbePlan{{
					Name:   "frame_contract_probe",
					Topics: []string{"/scan"},
				}},
			},
		},
		"run-1",
		RuntimeSpecBundle{
			Services: []simruntime.ServiceSpec{{Name: "service"}},
			Probes:   []simruntime.ProbeSpec{{Name: "frame_contract_probe", Required: true}},
			Rosbags:  []simruntime.RosbagSpec{{Name: "rosbag"}},
		},
		RuntimeExecutionResult{
			ServiceHandles: []simruntime.RuntimeHandle{{ServiceName: "service"}},
			RosbagHandles:  []simruntime.RuntimeHandle{{ServiceName: "rosbag", FinalizeOK: true, FinalizeStatus: "metadata_ready", MetadataPath: "rosbag/metadata.yaml"}},
		},
		nil,
	)

	if summary.NodeResult.OK {
		t.Fatalf("live common doctor should block missing probe: %#v", summary.NodeResult)
	}
	if summary.TopicFreshness["/scan"].Status != "stale_or_missing" {
		t.Fatalf("/scan freshness = %#v", summary.TopicFreshness["/scan"])
	}
}
