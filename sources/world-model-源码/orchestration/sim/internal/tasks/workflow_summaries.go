package tasks

import (
	"context"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
	"navlab/orchestration-sim/internal/config"
	simruntime "navlab/orchestration-sim/internal/runtime"
)

const simWorkflowSchemaVersion = "navlab.sim.workflow.v1"

type CheckResult struct {
	Status   string   `json:"status"`
	Required bool     `json:"required"`
	Evidence []string `json:"evidence,omitempty"`
	Warnings []string `json:"warnings,omitempty"`
	Blockers []string `json:"blockers,omitempty"`
}

type WorkflowNodeResult struct {
	ID               string                 `json:"id,omitempty"`
	Kind             string                 `json:"kind,omitempty"`
	Deps             []string               `json:"deps,omitempty"`
	Required         bool                   `json:"required"`
	Mode             string                 `json:"mode,omitempty"`
	Domain           string                 `json:"domain,omitempty"`
	SideEffectPolicy string                 `json:"side_effect_policy,omitempty"`
	SummaryPath      string                 `json:"summary_path,omitempty"`
	ArtifactPaths    []string               `json:"artifact_paths,omitempty"`
	Status           string                 `json:"status"`
	OK               bool                   `json:"ok"`
	Blocked          bool                   `json:"blocked"`
	Skipped          bool                   `json:"skipped"`
	SkipReason       string                 `json:"skip_reason,omitempty"`
	Blockers         []string               `json:"blockers"`
	Warnings         []string               `json:"warnings,omitempty"`
	Inputs           []string               `json:"inputs,omitempty"`
	Outputs          []string               `json:"outputs,omitempty"`
	Artifacts        map[string]string      `json:"artifacts,omitempty"`
	Evidence         map[string]interface{} `json:"evidence,omitempty"`
	StartedAt        string                 `json:"started_at,omitempty"`
	FinishedAt       string                 `json:"finished_at,omitempty"`
	CreatedAt        string                 `json:"created_at"`
}

type SimWorkflowBundle struct {
	Preflight    SimPreflightSummary    `json:"preflight"`
	Prepare      SimPrepareSummary      `json:"prepare"`
	CommonDoctor SimCommonDoctorSummary `json:"common_doctor"`
	TaskDoctor   SimTaskDoctorSummary   `json:"task_doctor"`
	Workflow     SimWorkflowSummary     `json:"workflow"`
	DoctorResult SimDoctorResult        `json:"doctor_result"`
}

type SimWorkflowOptions struct {
	LiveResourceCheck    bool
	DockerResourceClient simruntime.DockerResourceProbeClient
	ResourceCheckTimeout time.Duration
}

type SimPreflightSummary struct {
	SchemaVersion     string                    `json:"schema_version"`
	NodeResult        WorkflowNodeResult        `json:"node_result"`
	TaskID            string                    `json:"task_id"`
	RunID             string                    `json:"run_id"`
	RuntimeMode       string                    `json:"runtime_mode"`
	Backend           string                    `json:"backend"`
	ArtifactRoot      string                    `json:"artifact_root"`
	ArtifactDir       string                    `json:"artifact_dir"`
	Checks            map[string]CheckResult    `json:"checks"`
	ImageRefs         []ImageRefSummary         `json:"image_refs"`
	HostCommands      map[string]HostCommandRef `json:"host_commands"`
	LiveResourceProbe LiveResourceProbeSummary  `json:"live_resource_probe"`
}

type HostCommandRef struct {
	Command string `json:"command"`
	Path    string `json:"path,omitempty"`
	Found   bool   `json:"found"`
}

type LiveResourceProbeSummary struct {
	Enabled       bool                       `json:"enabled"`
	Claim         string                     `json:"claim"`
	Provenance    DockerResourceProvenance   `json:"provenance,omitempty"`
	DockerInfo    CheckResult                `json:"docker_info"`
	DockerUser    CheckResult                `json:"docker_user"`
	ImageChecks   []ImageAvailabilityCheck   `json:"image_checks,omitempty"`
	NetworkChecks []NetworkAvailabilityCheck `json:"network_checks,omitempty"`
}

type DockerResourceProvenance struct {
	Client                string   `json:"client,omitempty"`
	Host                  string   `json:"host,omitempty"`
	ServerVersion         string   `json:"server_version,omitempty"`
	APIVersion            string   `json:"api_version,omitempty"`
	MinAPIVersion         string   `json:"min_api_version,omitempty"`
	OSType                string   `json:"os_type,omitempty"`
	OperatingSystem       string   `json:"operating_system,omitempty"`
	Architecture          string   `json:"architecture,omitempty"`
	DockerRootDir         string   `json:"docker_root_dir,omitempty"`
	Rootless              bool     `json:"rootless,omitempty"`
	RootlessClaim         string   `json:"rootless_claim,omitempty"`
	SecurityOptions       []string `json:"security_options,omitempty"`
	RemoteContextEvidence string   `json:"remote_context_evidence,omitempty"`
}

type ImageAvailabilityCheck struct {
	Image string      `json:"image"`
	Check CheckResult `json:"check"`
}

type NetworkAvailabilityCheck struct {
	Network string      `json:"network"`
	Check   CheckResult `json:"check"`
}

type SimPrepareSummary struct {
	SchemaVersion        string                     `json:"schema_version"`
	NodeResult           WorkflowNodeResult         `json:"node_result"`
	TaskID               string                     `json:"task_id"`
	RunID                string                     `json:"run_id"`
	PrepareClaim         string                     `json:"prepare_claim"`
	ArtifactDir          string                     `json:"artifact_dir"`
	ContainerArtifactDir string                     `json:"container_artifact_dir,omitempty"`
	ContainerLogDir      string                     `json:"container_log_dir,omitempty"`
	RuntimePlanPath      string                     `json:"runtime_plan_path"`
	GeneratedArtifacts   []GeneratedRuntimeArtifact `json:"generated_runtime_artifacts"`
	ServicePlan          []ServicePlanEntry         `json:"service_plan"`
	ProbePlan            []ProbePlanEntry           `json:"probe_plan"`
	RosbagPlan           []RosbagPlanEntry          `json:"rosbag_plan"`
	ResourceProvenance   ResourceProvenance         `json:"resource_provenance"`
	ForbiddenInputAudit  ForbiddenInputAudit        `json:"forbidden_input_audit"`
	RuntimeSideEffects   RuntimeSideEffects         `json:"runtime_side_effects"`
}

type ServicePlanEntry struct {
	Name          string   `json:"name"`
	Role          string   `json:"role,omitempty"`
	Backend       string   `json:"backend"`
	Image         string   `json:"image"`
	ContainerName string   `json:"container_name,omitempty"`
	Command       []string `json:"command"`
	Networks      []string `json:"networks,omitempty"`
	Required      bool     `json:"required"`
	Restartable   bool     `json:"restartable"`
	LogPath       string   `json:"log_path,omitempty"`
}

type ProbePlanEntry struct {
	Name       string   `json:"name"`
	Role       string   `json:"role,omitempty"`
	Backend    string   `json:"backend"`
	Image      string   `json:"image"`
	Command    []string `json:"command"`
	OutputPath string   `json:"output_path,omitempty"`
	TimeoutSec float64  `json:"timeout_sec"`
	Required   bool     `json:"required"`
	LogPath    string   `json:"log_path,omitempty"`
}

type RosbagPlanEntry struct {
	Name          string   `json:"name"`
	Role          string   `json:"role,omitempty"`
	Backend       string   `json:"backend"`
	Image         string   `json:"image"`
	TopicsProfile string   `json:"topics_profile"`
	OutputPath    string   `json:"output_path"`
	DurationSec   float64  `json:"duration_sec"`
	Storage       string   `json:"storage"`
	Networks      []string `json:"networks,omitempty"`
	Required      bool     `json:"required"`
	LogPath       string   `json:"log_path,omitempty"`
}

type ResourceProvenance struct {
	RuntimeMode            string               `json:"runtime_mode"`
	Backend                string               `json:"backend"`
	DockerDaemonClaim      string               `json:"docker_daemon_claim"`
	DockerNetworkClaim     string               `json:"docker_network_claim"`
	DockerHost             string               `json:"docker_host,omitempty"`
	DockerServerVersion    string               `json:"docker_server_version,omitempty"`
	DockerAPIVersion       string               `json:"docker_api_version,omitempty"`
	DockerOSType           string               `json:"docker_os_type,omitempty"`
	DockerRootDir          string               `json:"docker_root_dir,omitempty"`
	DockerRootlessClaim    string               `json:"docker_rootless_claim,omitempty"`
	LiveResourceProbeClaim string               `json:"live_resource_probe_claim"`
	DockerNetworks         []string             `json:"docker_networks"`
	Images                 []ImageRefSummary    `json:"images"`
	WorkspaceMounts        []VolumeMountSummary `json:"workspace_mounts"`
	ContainerWorkspace     string               `json:"container_workspace,omitempty"`
	ContainerArtifactDir   string               `json:"container_artifact_dir,omitempty"`
	SimulationSourceClaim  string               `json:"simulation_source_claim"`
}

type ImageRefSummary struct {
	Image string `json:"image"`
	Tag   string `json:"tag,omitempty"`
	RefOK bool   `json:"ref_ok"`
}

type VolumeMountSummary struct {
	Source string `json:"source"`
	Target string `json:"target"`
	Mode   string `json:"mode,omitempty"`
}

type ForbiddenInputAudit struct {
	OK              bool              `json:"ok"`
	Claim           string            `json:"claim"`
	ForbiddenTokens []string          `json:"forbidden_tokens"`
	ScannedContexts int               `json:"scanned_contexts"`
	Matches         []ForbiddenMatch  `json:"matches"`
	ReviewOnly      map[string]string `json:"review_only,omitempty"`
}

type ForbiddenMatch struct {
	Kind    string `json:"kind"`
	Name    string `json:"name"`
	Token   string `json:"token"`
	Context string `json:"context"`
}

type RuntimeSideEffects struct {
	StartedServices bool   `json:"started_services"`
	StartedProbes   bool   `json:"started_probes"`
	StartedRosbags  bool   `json:"started_rosbags"`
	Policy          string `json:"policy"`
}

type SimCommonDoctorSummary struct {
	SchemaVersion        string                 `json:"schema_version"`
	NodeResult           WorkflowNodeResult     `json:"node_result"`
	TaskID               string                 `json:"task_id"`
	RunID                string                 `json:"run_id"`
	DoctorStage          string                 `json:"doctor_stage"`
	Checks               map[string]CheckResult `json:"checks"`
	LiveObservationClaim string                 `json:"live_observation_claim"`
	RequiredTopics       []string               `json:"required_topics,omitempty"`
}

type SimLiveCommonDoctorSummary struct {
	SchemaVersion        string                 `json:"schema_version"`
	NodeResult           WorkflowNodeResult     `json:"node_result"`
	TaskID               string                 `json:"task_id"`
	RunID                string                 `json:"run_id"`
	DoctorStage          string                 `json:"doctor_stage"`
	Checks               map[string]CheckResult `json:"checks"`
	TopicFreshness       map[string]CheckResult `json:"topic_freshness"`
	FSMArtifacts         []FSMArtifactRef       `json:"fsm_artifacts,omitempty"`
	RuntimeError         string                 `json:"runtime_error,omitempty"`
	LiveObservationClaim string                 `json:"live_observation_claim"`
}

type SimTaskDoctorSummary struct {
	SchemaVersion           string                 `json:"schema_version"`
	NodeResult              WorkflowNodeResult     `json:"node_result"`
	TaskID                  string                 `json:"task_id"`
	RunID                   string                 `json:"run_id"`
	DoctorStage             string                 `json:"doctor_stage"`
	TaskDoctorClaim         string                 `json:"task_doctor_claim"`
	TaskSpecificDoctorClaim string                 `json:"task_specific_doctor_claim"`
	Checks                  map[string]CheckResult `json:"checks"`
}

type SimWorkflowSummary struct {
	SchemaVersion string               `json:"schema_version"`
	TaskID        string               `json:"task_id"`
	RunID         string               `json:"run_id"`
	OK            bool                 `json:"ok"`
	Blocked       bool                 `json:"blocked"`
	Blockers      []string             `json:"blockers"`
	Nodes         []WorkflowNodeResult `json:"nodes"`
	CreatedAt     string               `json:"created_at"`
}

type SimDoctorResult struct {
	SchemaVersion string               `json:"schema_version"`
	TaskID        string               `json:"task_id"`
	RunID         string               `json:"run_id"`
	OK            bool                 `json:"ok"`
	Blocked       bool                 `json:"blocked"`
	Blockers      []string             `json:"blockers"`
	NodeResults   []WorkflowNodeResult `json:"node_results"`
	CreatedAt     string               `json:"created_at"`
}

func BuildSimWorkflowBundle(
	project config.ProjectConfig,
	taskConfig config.TaskConfig,
	runtimeConfig config.TaskRuntimeConfig,
	plan Plan,
	runID string,
	artifactRoot string,
	artifactDir string,
	generatedArtifacts []GeneratedRuntimeArtifact,
	runtimeSpecs RuntimeSpecBundle,
	runtimePlanPath string,
) SimWorkflowBundle {
	return BuildSimWorkflowBundleWithOptions(project, taskConfig, runtimeConfig, plan, runID, artifactRoot, artifactDir, generatedArtifacts, runtimeSpecs, runtimePlanPath, SimWorkflowOptions{})
}

func BuildSimWorkflowBundleWithOptions(
	project config.ProjectConfig,
	taskConfig config.TaskConfig,
	runtimeConfig config.TaskRuntimeConfig,
	plan Plan,
	runID string,
	artifactRoot string,
	artifactDir string,
	generatedArtifacts []GeneratedRuntimeArtifact,
	runtimeSpecs RuntimeSpecBundle,
	runtimePlanPath string,
	options SimWorkflowOptions,
) SimWorkflowBundle {
	liveProbe := BuildLiveResourceProbeSummary(runtimeSpecs, options)
	preflight := buildSimPreflightSummary(project, taskConfig, plan, runID, artifactRoot, artifactDir, runtimeSpecs, liveProbe)
	prepare := buildSimPrepareSummary(project, plan, runID, artifactDir, generatedArtifacts, runtimeSpecs, runtimePlanPath, liveProbe)
	commonDoctor := BuildSimCommonDoctorSummary(project, plan, runID, prepare.ForbiddenInputAudit)
	taskDoctor := BuildDefaultSimTaskDoctorSummary(project, taskConfig, runtimeConfig, plan, runID, artifactDir, runtimePlanPath)
	workflow := BuildSimWorkflowSummary(plan.TaskID, runID, []WorkflowNodeResult{
		preflight.NodeResult,
		prepare.NodeResult,
		commonDoctor.NodeResult,
		taskDoctor.NodeResult,
		skippedWorkflowNode("runtime-execute", "runtime-execute", "dry_run_or_prepare_runtime_execute_not_started"),
		skippedWorkflowNode("gate-evaluate", "gate-evaluate", "dry_run_or_prepare_gate_evaluate_not_started"),
	})
	doctorResult := BuildSimDoctorResult(plan.TaskID, runID, workflow.Nodes)
	return SimWorkflowBundle{
		Preflight:    preflight,
		Prepare:      prepare,
		CommonDoctor: commonDoctor,
		TaskDoctor:   taskDoctor,
		Workflow:     workflow,
		DoctorResult: doctorResult,
	}
}

func BuildSimPreflightSummary(
	project config.ProjectConfig,
	taskConfig config.TaskConfig,
	plan Plan,
	runID string,
	artifactRoot string,
	artifactDir string,
	runtimeSpecs RuntimeSpecBundle,
) SimPreflightSummary {
	return buildSimPreflightSummary(project, taskConfig, plan, runID, artifactRoot, artifactDir, runtimeSpecs, staticLiveResourceProbe())
}

func buildSimPreflightSummary(
	project config.ProjectConfig,
	taskConfig config.TaskConfig,
	plan Plan,
	runID string,
	artifactRoot string,
	artifactDir string,
	runtimeSpecs RuntimeSpecBundle,
	liveProbe LiveResourceProbeSummary,
) SimPreflightSummary {
	images := imageRefsFromSpecs(runtimeSpecs)
	hostCommands := map[string]HostCommandRef{}
	dockerInfoCheck := deferred("docker daemon liveness is checked at runtime-execute/live prepare boundary")
	dockerUserCheck := deferred("docker user permission is checked at runtime-execute/live prepare boundary")
	imageAvailabilityCheck := deferred("docker image availability is checked at runtime-execute/live prepare boundary")
	networkAvailabilityCheck := deferred("port/network conflict requires live host socket inspection")
	if liveProbe.Enabled {
		dockerInfoCheck = liveProbe.DockerInfo
		dockerUserCheck = liveProbe.DockerUser
		imageAvailabilityCheck = combinedImageAvailabilityCheck(liveProbe.ImageChecks)
		networkAvailabilityCheck = combinedNetworkAvailabilityCheck(liveProbe.NetworkChecks)
	}
	checks := map[string]CheckResult{
		"runtime_mode_simulation":    passRequired(project.Runtime.Mode == "simulation", "runtime.mode="+project.Runtime.Mode),
		"runtime_backend_docker":     passRequired(project.Runtime.Backend == "docker", "runtime.backend="+project.Runtime.Backend),
		"task_config_loaded":         passRequired(strings.TrimSpace(taskConfig.ID) != "", "task_id="+taskConfig.ID),
		"task_yaml_parsed":           passRequired(strings.TrimSpace(taskConfig.ID) != "", "task_id="+taskConfig.ID),
		"simulation_profile_present": passRequired(strings.TrimSpace(plan.SimulationProfile) != "", "simulation_profile="+plan.SimulationProfile),
		"artifact_root_resolved":     passRequired(strings.TrimSpace(artifactRoot) != "", "artifact_root="+artifactRoot),
		"artifact_dir_allocated":     passRequired(strings.TrimSpace(artifactDir) != "", "artifact_dir="+artifactDir),
		"docker_sdk_client_available": passRequired(true,
			"Docker resource preflight uses github.com/docker/docker SDK client; docker CLI binary is not required"),
		"docker_daemon_alive":     dockerInfoCheck,
		"docker_user_permission":  dockerUserCheck,
		"images_resolved":         passRequired(len(images) > 0, "image_refs="+itoa(len(images))),
		"image_tags_resolved":     passRequired(allImageRefsTagged(images), "image tags resolved from config/catalog"),
		"images_available":        imageAvailabilityCheck,
		"host_ros2_command":       optionalDeferred("host ros2 is not required for Docker-backed dry-run prepare"),
		"mcap_or_foxglove_tools":  optionalDeferred("review tools are consumed from generated artifacts or Docker images"),
		"forbidden_config_static": passRequired(!forbiddenConfigEnabled(project), "no explicit gazebo truth input config enabled"),
		"port_network_conflict":   networkAvailabilityCheck,
	}
	node := nodeFromChecks("preflight", "preflight", checks, []string{"project_config", "task_yaml"}, []string{artifactlayout.DAGRel("preflight_summary.json")})
	return SimPreflightSummary{
		SchemaVersion:     simWorkflowSchemaVersion,
		NodeResult:        node,
		TaskID:            plan.TaskID,
		RunID:             runID,
		RuntimeMode:       project.Runtime.Mode,
		Backend:           project.Runtime.Backend,
		ArtifactRoot:      artifactRoot,
		ArtifactDir:       artifactDir,
		Checks:            checks,
		ImageRefs:         images,
		HostCommands:      hostCommands,
		LiveResourceProbe: liveProbe,
	}
}

func BuildSimPrepareSummary(
	project config.ProjectConfig,
	plan Plan,
	runID string,
	artifactDir string,
	generatedArtifacts []GeneratedRuntimeArtifact,
	runtimeSpecs RuntimeSpecBundle,
	runtimePlanPath string,
) SimPrepareSummary {
	return buildSimPrepareSummary(project, plan, runID, artifactDir, generatedArtifacts, runtimeSpecs, runtimePlanPath, staticLiveResourceProbe())
}

func buildSimPrepareSummary(
	project config.ProjectConfig,
	plan Plan,
	runID string,
	artifactDir string,
	generatedArtifacts []GeneratedRuntimeArtifact,
	runtimeSpecs RuntimeSpecBundle,
	runtimePlanPath string,
	liveProbe LiveResourceProbeSummary,
) SimPrepareSummary {
	resource := buildResourceProvenance(project, artifactDir, runtimeSpecs, liveProbe)
	forbiddenAudit := buildForbiddenInputAudit(runtimeSpecs)
	checks := map[string]CheckResult{
		"artifact_layout_generated":     passRequired(artifactDir != "", "artifact layout root="+artifactDir),
		"runtime_plan_generated":        passRequired(runtimePlanPath != "", "runtime_plan="+runtimePlanPath),
		"runtime_artifacts_generated":   passRequired(len(generatedArtifacts) > 0, "generated_artifacts="+itoa(len(generatedArtifacts))),
		"service_plan_generated":        passRequired(len(runtimeSpecs.Services) > 0, "services="+itoa(len(runtimeSpecs.Services))),
		"probe_plan_generated":          passRequired(len(runtimeSpecs.Probes) > 0 || runtimeSpecs.StartupReadinessProbe != nil, "probes="+itoa(len(runtimeSpecs.Probes))),
		"rosbag_plan_generated":         passRequired(len(runtimeSpecs.Rosbags) > 0, "rosbags="+itoa(len(runtimeSpecs.Rosbags))),
		"resource_provenance_generated": passRequired(len(resource.Images) > 0, "images="+itoa(len(resource.Images))),
		"forbidden_input_audit_ok":      passRequired(forbiddenAudit.OK, "forbidden input audit completed"),
		"runtime_side_effects_deferred": passRequired(true, "prepare generated plans/artifacts only"),
	}
	node := nodeFromChecks("prepare", "prepare", checks, []string{artifactlayout.DAGRel("preflight_summary.json"), "task_plan.json"}, []string{artifactlayout.DAGRel("prepare_summary.json"), "runtime_plan.json"})
	return SimPrepareSummary{
		SchemaVersion:        simWorkflowSchemaVersion,
		NodeResult:           node,
		TaskID:               plan.TaskID,
		RunID:                runID,
		PrepareClaim:         "planned_service_probe_resource_artifacts_no_runtime_start",
		ArtifactDir:          artifactDir,
		ContainerArtifactDir: resource.ContainerArtifactDir,
		ContainerLogDir:      filepath.ToSlash(filepath.Join(resource.ContainerArtifactDir, artifactlayout.RuntimeLogsDir)),
		RuntimePlanPath:      runtimePlanPath,
		GeneratedArtifacts:   append([]GeneratedRuntimeArtifact(nil), generatedArtifacts...),
		ServicePlan:          servicePlanEntries(runtimeSpecs.Services),
		ProbePlan:            probePlanEntries(runtimeSpecs),
		RosbagPlan:           rosbagPlanEntries(runtimeSpecs.Rosbags),
		ResourceProvenance:   resource,
		ForbiddenInputAudit:  forbiddenAudit,
		RuntimeSideEffects: RuntimeSideEffects{
			StartedServices: false,
			StartedProbes:   false,
			StartedRosbags:  false,
			Policy:          "runtime-execute owns Gazebo/SITL/SLAM/companion/rosbag/probe start",
		},
	}
}

func BuildSimCommonDoctorSummary(project config.ProjectConfig, plan Plan, runID string, audit ForbiddenInputAudit) SimCommonDoctorSummary {
	topics := requiredCommonTopics(plan)
	checks := map[string]CheckResult{
		"runtime_mode_simulation":             passRequired(project.Runtime.Mode == "simulation", "runtime.mode="+project.Runtime.Mode),
		"source_claims_present":               passRequired(plan.SimulationProfile != "", "simulation_profile="+plan.SimulationProfile),
		"no_gazebo_truth_input_plan":          passRequired(audit.OK, "forbidden input matches="+itoa(len(audit.Matches))),
		"official_overlay_review_only":        passRequired(true, "official maze overlay is modeled as review-only service/probe artifact"),
		"scan_topic_planned":                  plannedTopic("/scan", topics),
		"tf_topic_planned":                    plannedTopic("/tf", topics),
		"tf_static_topic_planned":             plannedTopic("/tf_static", topics),
		"slam_odom_topic_planned":             plannedTopic("/slam/odom", topics),
		"external_nav_status_planned":         plannedTopic("/external_nav/status", topics),
		"mavlink_external_nav_status_planned": plannedTopic("/mavlink_external_nav/status", topics),
		"fcu_status_planned":                  plannedTopic("/navlab/fcu/status", topics),
		"rosbag_profile_planned":              passRequired(len(plan.Execution.RosbagRecords) > 0, "rosbag_records="+itoa(len(plan.Execution.RosbagRecords))),
		"artifact_layout_planned":             passRequired(true, "artifact layout generated during prepare"),
		"runtime_events_live_only":            optionalDeferred("runtime timeout/blocker events require runtime-execute"),
		"frame_contract_planned":              plannedHelper(plan, "frame-contract"),
	}
	node := nodeFromChecks("common-doctor", "common-doctor", checks, []string{artifactlayout.DAGRel("prepare_summary.json")}, []string{artifactlayout.DAGRel("common_doctor_summary.json")})
	return SimCommonDoctorSummary{
		SchemaVersion:        simWorkflowSchemaVersion,
		NodeResult:           node,
		TaskID:               plan.TaskID,
		RunID:                runID,
		DoctorStage:          "sim_common_doctor_static_prepare",
		Checks:               checks,
		LiveObservationClaim: "not_sampled_in_prepare; live freshness is runtime-execute evidence",
		RequiredTopics:       topics,
	}
}

func BuildSimLiveCommonDoctorSummary(
	project config.ProjectConfig,
	plan Plan,
	runID string,
	runtimeSpecs RuntimeSpecBundle,
	execution RuntimeExecutionResult,
	executionErr error,
	fsmArtifacts ...FSMArtifactRef,
) SimLiveCommonDoctorSummary {
	runtimeError := ""
	if executionErr != nil {
		runtimeError = executionErr.Error()
	}
	topicFreshness := map[string]CheckResult{}
	for _, topic := range []string{
		"/scan",
		"/tf",
		"/tf_static",
		"/slam/odom",
		"/external_nav/status",
		"/mavlink_external_nav/status",
		"/navlab/fcu/status",
	} {
		topicFreshness[topic] = liveTopicFreshnessCheck(topic, plan, execution)
	}
	checks := map[string]CheckResult{
		"runtime_mode_simulation":        passRequired(project.Runtime.Mode == "simulation", "runtime.mode="+project.Runtime.Mode),
		"runtime_execution_completed":    passRequired(executionErr == nil, "runtime_error="+runtimeError),
		"runtime_services_observed":      passRequired(len(execution.ServiceHandles) > 0, "service_handles="+itoa(len(execution.ServiceHandles))),
		"runtime_probes_observed":        passRequired(len(execution.ProbeResults) > 0 || len(runtimeSpecs.Probes) == 0, "probe_results="+itoa(len(execution.ProbeResults))),
		"runtime_rosbags_observed":       passRequired(len(execution.RosbagHandles) > 0 || len(runtimeSpecs.Rosbags) == 0, "rosbag_handles="+itoa(len(execution.RosbagHandles))),
		"runtime_rosbag_finalize_ok":     runtimeRosbagFinalizeOK(runtimeSpecs, execution),
		"runtime_stop_errors_absent":     passRequired(len(execution.StopErrors) == 0, "stop_errors="+itoa(len(execution.StopErrors))),
		"probe_required_results_ok":      requiredProbeResultsOK(runtimeSpecs, execution),
		"rosbag_profile_runtime_planned": passRequired(len(runtimeSpecs.Rosbags) > 0, "rosbags="+itoa(len(runtimeSpecs.Rosbags))),
	}
	for topic, check := range topicFreshness {
		checks["topic_freshness:"+topic] = check
	}
	node := nodeFromChecks("common-doctor-live", "common-doctor-live", checks, []string{artifactlayout.DAGRel("common_doctor_summary.json"), "summary.json"}, []string{artifactlayout.DAGRel("common_doctor_live_summary.json")})
	return SimLiveCommonDoctorSummary{
		SchemaVersion:        simWorkflowSchemaVersion,
		NodeResult:           node,
		TaskID:               plan.TaskID,
		RunID:                runID,
		DoctorStage:          "sim_common_doctor_live_runtime_evidence",
		Checks:               checks,
		TopicFreshness:       topicFreshness,
		FSMArtifacts:         append([]FSMArtifactRef(nil), fsmArtifacts...),
		RuntimeError:         runtimeError,
		LiveObservationClaim: "derived_from_runtime_execute_probe_results_service_handles_rosbag_finalize_evidence",
	}
}

func runtimeRosbagFinalizeOK(runtimeSpecs RuntimeSpecBundle, execution RuntimeExecutionResult) CheckResult {
	if len(runtimeSpecs.Rosbags) == 0 {
		return CheckResult{Status: "not_planned", Required: false, Evidence: []string{"rosbags=0"}}
	}
	if len(execution.RosbagHandles) == 0 {
		return CheckResult{Status: "missing", Required: true, Evidence: []string{"rosbag_handles=0"}, Blockers: []string{"rosbag finalize evidence missing"}}
	}
	evidence := []string{}
	blockers := []string{}
	for _, handle := range execution.RosbagHandles {
		status := handle.ServiceName + ":finalize_ok=" + strconv.FormatBool(handle.FinalizeOK)
		if handle.FinalizeStatus != "" {
			status += ":status=" + handle.FinalizeStatus
		}
		if handle.MetadataPath != "" {
			status += ":metadata"
		}
		if len(handle.MCAPPaths) > 0 {
			status += ":mcap_paths=" + itoa(len(handle.MCAPPaths))
		}
		evidence = append(evidence, status)
		if !handle.FinalizeOK {
			blockers = append(blockers, "rosbag finalize not ok: "+handle.ServiceName)
		}
	}
	if len(blockers) > 0 {
		return CheckResult{Status: "blocked", Required: true, Evidence: evidence, Blockers: blockers}
	}
	return CheckResult{Status: "ok", Required: true, Evidence: evidence}
}

func liveTopicFreshnessCheck(topic string, plan Plan, execution RuntimeExecutionResult) CheckResult {
	probes := probesForTopic(plan, topic)
	if len(probes) == 0 {
		return CheckResult{Status: "not_planned", Required: false, Evidence: []string{"topic=" + topic}}
	}
	results := map[string]simruntime.ProbeResult{}
	for _, result := range execution.ProbeResults {
		results[result.Name] = result
	}
	evidence := []string{}
	for _, probe := range probes {
		result, ok := results[probe]
		if !ok {
			evidence = append(evidence, probe+":missing")
			continue
		}
		if result.OK() {
			return CheckResult{Status: "fresh_by_probe", Required: true, Evidence: []string{probe + ":return_code=0"}}
		}
		evidence = append(evidence, probe+":return_code="+itoa(result.ReturnCode))
	}
	return CheckResult{Status: "stale_or_missing", Required: true, Evidence: evidence, Blockers: []string{"no passing probe observed for topic " + topic}}
}

func probesForTopic(plan Plan, topic string) []string {
	probes := []string{}
	for _, probe := range plan.Execution.ROSProbes {
		for _, plannedTopic := range probe.Topics {
			if plannedTopic == topic {
				probes = append(probes, probe.Name)
				break
			}
		}
	}
	sort.Strings(probes)
	return probes
}

func requiredProbeResultsOK(runtimeSpecs RuntimeSpecBundle, execution RuntimeExecutionResult) CheckResult {
	required := map[string]bool{}
	for _, probe := range runtimeSpecs.Probes {
		if probe.Required {
			required[probe.Name] = true
		}
	}
	if len(required) == 0 {
		return CheckResult{Status: "not_applicable", Required: false, Evidence: []string{"no required runtime probes"}}
	}
	blockers := []string{}
	evidence := []string{}
	seen := map[string]bool{}
	for _, result := range execution.ProbeResults {
		if !required[result.Name] {
			continue
		}
		seen[result.Name] = true
		evidence = append(evidence, result.Name+":return_code="+itoa(result.ReturnCode))
		if !result.OK() {
			blockers = append(blockers, result.Name+":return_code="+itoa(result.ReturnCode))
		}
	}
	for name := range required {
		if !seen[name] {
			blockers = append(blockers, name+":missing")
		}
	}
	sort.Strings(blockers)
	sort.Strings(evidence)
	if len(blockers) > 0 {
		return CheckResult{Status: "fail", Required: true, Evidence: evidence, Blockers: blockers}
	}
	return CheckResult{Status: "pass", Required: true, Evidence: evidence}
}

func BuildDefaultSimTaskDoctorSummary(
	project config.ProjectConfig,
	taskConfig config.TaskConfig,
	runtimeConfig config.TaskRuntimeConfig,
	plan Plan,
	runID string,
	artifactDir string,
	runtimePlanPath string,
) SimTaskDoctorSummary {
	checks := map[string]CheckResult{
		"task_config_valid":        passRequired(strings.TrimSpace(taskConfig.ID) == strings.TrimSpace(plan.TaskID), "task_id="+plan.TaskID),
		"task_duration_valid":      passRequired(plan.DurationSec > 0, "duration_sec="+formatFloat(plan.DurationSec)),
		"simulation_profile_valid": passRequired(strings.TrimSpace(plan.SimulationProfile) != "", "simulation_profile="+plan.SimulationProfile),
		"artifact_path_valid":      passRequired(strings.TrimSpace(artifactDir) != "", "artifact_dir="+artifactDir),
		"runtime_plan_generated":   passRequired(strings.TrimSpace(runtimePlanPath) != "", "runtime_plan="+runtimePlanPath),
		"required_helpers_present": passRequired(len(plan.Helpers) > 0, "helpers="+itoa(len(plan.Helpers))),
		"task_specific_doctor": {
			Status:   "not_applicable",
			Required: false,
			Evidence: []string{"task has no registered task-specific doctor hook in WF1 first slice"},
		},
		"runtime_mode_simulation": passRequired(project.Runtime.Mode == "simulation", "runtime.mode="+project.Runtime.Mode),
	}
	taskSpecificClaim, taskSpecificChecks := taskSpecificDoctorChecks(runtimeConfig, plan)
	checks["task_specific_doctor"] = CheckResult{
		Status:   taskSpecificClaim,
		Required: false,
		Evidence: []string{"task_id=" + plan.TaskID},
	}
	for name, check := range taskSpecificChecks {
		checks[name] = check
	}
	node := nodeFromChecks("task-doctor", "task-doctor", checks, []string{artifactlayout.DAGRel("prepare_summary.json"), artifactlayout.DAGRel("common_doctor_summary.json")}, []string{artifactlayout.DAGRel("task_doctor_summary.json")})
	return SimTaskDoctorSummary{
		SchemaVersion:           simWorkflowSchemaVersion,
		NodeResult:              node,
		TaskID:                  plan.TaskID,
		RunID:                   runID,
		DoctorStage:             "sim_default_task_doctor_static_prepare",
		TaskDoctorClaim:         "default",
		TaskSpecificDoctorClaim: taskSpecificClaim,
		Checks:                  checks,
	}
}

func taskSpecificDoctorChecks(runtimeConfig config.TaskRuntimeConfig, plan Plan) (string, map[string]CheckResult) {
	switch plan.TaskID {
	case "hover":
		return "implemented", hoverTaskDoctorChecks(runtimeConfig, plan)
	case "navigation":
		return "implemented", navigationTaskDoctorChecks(runtimeConfig, plan)
	case "scan-robustness":
		return "implemented", scanRobustnessTaskDoctorChecks(runtimeConfig, plan)
	default:
		return "not_applicable", nil
	}
}

func hoverTaskDoctorChecks(runtimeConfig config.TaskRuntimeConfig, plan Plan) map[string]CheckResult {
	hover := runtimeConfig.SlamHover
	fcu := runtimeConfig.FCUController
	landing := runtimeConfig.Landing
	profile, profileOK := hoverSimulationProfileForTask(plan.TaskID, plan.SimulationProfile)
	return map[string]CheckResult{
		"hover_profile_mainline": passRequired(profileOK && profile.Mainline, "simulation_profile="+plan.SimulationProfile),
		"hover_altitude_reasonable": passRequired(
			fcu.TakeoffAltM > 0 &&
				fcu.TakeoffMinHeightM >= 0 &&
				fcu.TakeoffMinHeightM <= fcu.TakeoffAltM &&
				fcu.TakeoffMinHeightRatio >= 0 &&
				fcu.TakeoffMinHeightRatio <= 1,
			"takeoff_alt_m="+formatFloat(fcu.TakeoffAltM),
		),
		"hover_span_policy": passRequired(
			hover.HoverSpanTargetM > 0 &&
				hover.HoverSpanHardCapM > 0 &&
				hover.HoverSpanTargetM <= hover.HoverSpanHardCapM,
			"target="+formatFloat(hover.HoverSpanTargetM)+" hard_cap="+formatFloat(hover.HoverSpanHardCapM),
		),
		"hover_health_window_policy": hoverHealthWindowCheck(hover),
		"hover_external_nav_required": passRequired(
			strings.TrimSpace(hover.ExternalNavInputOdomTopic) != "" &&
				strings.TrimSpace(hover.ExternalNavStatusTopic) != "" &&
				hover.MinExternalNavRateHz >= 0,
			"external_nav_input="+hover.ExternalNavInputOdomTopic+" status="+hover.ExternalNavStatusTopic,
		),
		"hover_landing_policy": passRequired(
			landing.Enabled &&
				strings.TrimSpace(landing.HoverPolicy) != "" &&
				landing.MaxLandingDurationSec > 0 &&
				landing.RequireDisarm &&
				landing.RequireMotorsSafe,
			"hover_policy="+landing.HoverPolicy,
		),
	}
}

func hoverHealthWindowCheck(hover config.SlamHoverConfig) CheckResult {
	if hover.HoverHealthStableRequiredSec <= 0 && hover.HoverHealthMaxWaitSec <= 0 && hover.HoverHealthMinObservationSec <= 0 {
		return CheckResult{
			Status:   "not_configured_static_prepare",
			Required: false,
			Evidence: []string{"hover-health live/postrun audit remains runtime evidence"},
		}
	}
	return passRequired(
		hover.HoverHealthMinObservationSec >= 0 &&
			hover.HoverHealthStableRequiredSec > 0 &&
			hover.HoverHealthMaxWaitSec >= hover.HoverHealthStableRequiredSec,
		"min_observation="+formatFloat(hover.HoverHealthMinObservationSec)+" stable_required="+formatFloat(hover.HoverHealthStableRequiredSec)+" max_wait="+formatFloat(hover.HoverHealthMaxWaitSec),
	)
}

func navigationTaskDoctorChecks(runtimeConfig config.TaskRuntimeConfig, plan Plan) map[string]CheckResult {
	nav2 := runtimeConfig.Nav2
	costmap := nav2.Costmap
	mission := runtimeConfig.NavigationMission
	adapter := runtimeConfig.NavigationAdapter
	return map[string]CheckResult{
		"navigation_profile_valid": passRequired(strings.TrimSpace(plan.SimulationProfile) != "", "simulation_profile="+plan.SimulationProfile),
		"nav2_enabled":             passRequired(nav2.Enabled, "nav2.enabled="+boolString(nav2.Enabled)),
		"nav2_core_params_present": passRequired(
			strings.TrimSpace(nav2.Profile) != "" &&
				strings.TrimSpace(nav2.GlobalFrame) != "" &&
				strings.TrimSpace(nav2.OdomFrame) != "" &&
				strings.TrimSpace(nav2.BaseFrame) != "" &&
				strings.TrimSpace(nav2.ScanTopic) != "" &&
				strings.TrimSpace(nav2.MapTopic) != "",
			"profile="+nav2.Profile,
		),
		"nav2_costmap_config_present": passRequired(
			len(costmap.RequiredLayers) > 0 &&
				strings.TrimSpace(costmap.GlobalCostmapTopic) != "" &&
				strings.TrimSpace(costmap.LocalCostmapTopic) != "" &&
				strings.TrimSpace(costmap.HealthTopic) != "" &&
				costmap.MaxCostmapAgeSec > 0,
			"required_layers="+itoa(len(costmap.RequiredLayers)),
		),
		"navigation_goal_strategy_valid": passRequired(
			strings.TrimSpace(mission.Strategy) != "" &&
				strings.TrimSpace(mission.GoalFrame) != "" &&
				len(mission.BoundedGoals) >= mission.MinAcceptedGoals &&
				mission.MinAcceptedGoals > 0 &&
				mission.NavigationWindowSec > 0,
			"strategy="+mission.Strategy+" bounded_goals="+itoa(len(mission.BoundedGoals)),
		),
		"navigation_adapter_policy": passRequired(
			adapter.MaxXYSpeedMPS > 0 &&
				adapter.FixedAltitudeM > 0 &&
				adapter.StopOnStaleCostmap &&
				adapter.StopOnStaleSlam,
			"max_xy_speed_mps="+formatFloat(adapter.MaxXYSpeedMPS),
		),
		"navigation_no_truth_input": passRequired(
			!costmap.UsesGazeboTruth && !mission.UsesGazeboTruthAsInput,
			"costmap_uses_gazebo_truth="+boolString(costmap.UsesGazeboTruth)+" mission_uses_gazebo_truth="+boolString(mission.UsesGazeboTruthAsInput),
		),
	}
}

func scanRobustnessTaskDoctorChecks(runtimeConfig config.TaskRuntimeConfig, plan Plan) map[string]CheckResult {
	disturbance := runtimeConfig.AirframeDisturbance
	gate := runtimeConfig.AirframeDisturbanceGate
	stabilization := runtimeConfig.ScanStabilization
	return map[string]CheckResult{
		"scan_robustness_profile_valid": passRequired(
			strings.TrimSpace(disturbance.Profile) != "" &&
				stringInSlice(disturbance.Profile, gate.ProfileSet),
			"profile="+disturbance.Profile,
		),
		"scan_robustness_required_profiles": passRequired(
			len(gate.RequiredProfiles) > 0 &&
				stringsInSlice(gate.RequiredProfiles, gate.ProfileSet),
			"required_profiles="+strings.Join(gate.RequiredProfiles, ","),
		),
		"scan_robustness_helpers_present": passRequired(
			hasPlanHelper(plan, "scan-stabilization") && hasPlanHelper(plan, "scan-robustness-workflow"),
			"helpers=scan-stabilization,scan-robustness-workflow",
		),
		"scan_stabilization_config": scanStabilizationConfigCheck(stabilization, plan),
		"scan_robustness_no_forbidden_map_input": passRequired(
			!gate.UsesOfficialMazeAsInput && !stabilization.UsesGazeboTruthAsInput,
			"official_maze_input="+boolString(gate.UsesOfficialMazeAsInput)+" stabilization_truth="+boolString(stabilization.UsesGazeboTruthAsInput),
		),
	}
}

func scanStabilizationConfigCheck(stabilization config.ScanStabilizationConfig, plan Plan) CheckResult {
	if !hasPlanHelper(plan, "scan-stabilization") {
		return CheckResult{Status: "not_applicable", Required: false, Evidence: []string{"scan-stabilization helper not planned"}}
	}
	if !stabilization.Enabled && strings.TrimSpace(stabilization.InputScanTopic) == "" && strings.TrimSpace(stabilization.OutputScanTopic) == "" {
		return CheckResult{
			Status:   "planned_from_helper_defaults",
			Required: false,
			Evidence: []string{"scan stabilization runtime spec is generated from helper defaults"},
		}
	}
	return passRequired(
		stabilization.Enabled &&
			strings.TrimSpace(stabilization.Mode) != "" &&
			strings.TrimSpace(stabilization.InputScanTopic) != "" &&
			strings.TrimSpace(stabilization.OutputScanTopic) != "",
		"mode="+stabilization.Mode+" input="+stabilization.InputScanTopic+" output="+stabilization.OutputScanTopic,
	)
}

func hasPlanHelper(plan Plan, helperID string) bool {
	for _, helper := range plan.Helpers {
		if helper.ID == helperID {
			return true
		}
	}
	return false
}

func stringsInSlice(values []string, candidates []string) bool {
	for _, value := range values {
		if !stringInSlice(value, candidates) {
			return false
		}
	}
	return true
}

func boolString(value bool) string {
	if value {
		return "true"
	}
	return "false"
}

func BuildSimWorkflowSummary(taskID string, runID string, nodes []WorkflowNodeResult) SimWorkflowSummary {
	nodes = applyWorkflowDependencies(nodes)
	blockers := blockersFromNodes(nodes)
	return SimWorkflowSummary{
		SchemaVersion: simWorkflowSchemaVersion,
		TaskID:        taskID,
		RunID:         runID,
		OK:            len(blockers) == 0,
		Blocked:       len(blockers) > 0,
		Blockers:      blockers,
		Nodes:         append([]WorkflowNodeResult(nil), nodes...),
		CreatedAt:     time.Now().UTC().Format(time.RFC3339),
	}
}

func BuildSimLiveWorkflowSummary(base SimWorkflowSummary, summary LiveRunSummary) SimWorkflowSummary {
	nodes := append([]WorkflowNodeResult(nil), base.Nodes...)
	nodes = replaceWorkflowNode(nodes, runtimeExecuteNodeFromLiveSummary(summary))
	nodes = replaceWorkflowNode(nodes, gateEvaluateNodeFromLiveSummary(summary))
	return BuildSimWorkflowSummary(summary.TaskID, summary.RunID, nodes)
}

func BuildSimDoctorResult(taskID string, runID string, nodes []WorkflowNodeResult) SimDoctorResult {
	nodes = applyWorkflowDependencies(nodes)
	blockers := blockersFromNodes(nodes)
	return SimDoctorResult{
		SchemaVersion: simWorkflowSchemaVersion,
		TaskID:        taskID,
		RunID:         runID,
		OK:            len(blockers) == 0,
		Blocked:       len(blockers) > 0,
		Blockers:      blockers,
		NodeResults:   append([]WorkflowNodeResult(nil), nodes...),
		CreatedAt:     time.Now().UTC().Format(time.RFC3339),
	}
}

func runtimeExecuteNodeFromLiveSummary(summary LiveRunSummary) WorkflowNodeResult {
	blockers := []string{}
	if strings.TrimSpace(summary.RuntimeError) != "" {
		blockers = append(blockers, "runtime_execution_failed:"+summary.RuntimeError)
	}
	warnings := append([]string(nil), summary.RuntimeExecution.StopErrors...)
	evidence := map[string]interface{}{
		"claim":                  "runtime_execute_completed_from_live_run",
		"runtime_error":          summary.RuntimeError,
		"service_handle_count":   len(summary.RuntimeExecution.ServiceHandles),
		"probe_result_count":     len(summary.RuntimeExecution.ProbeResults),
		"rosbag_handle_count":    len(summary.RuntimeExecution.RosbagHandles),
		"runtime_service_count":  summary.RuntimeSpecCounts.Services,
		"runtime_probe_count":    summary.RuntimeSpecCounts.Probes,
		"runtime_rosbag_count":   summary.RuntimeSpecCounts.Rosbags,
		"summary_path":           "summary.json",
		"runtime_artifact_count": len(summary.GeneratedRuntimeArtifacts),
	}
	return workflowNode("runtime-execute", "runtime-execute", workflowNodeOptions{
		Mode:             "live",
		SideEffectPolicy: "runtime_start",
		Inputs:           []string{artifactlayout.DAGRel("task_doctor_summary.json"), "runtime_plan.json"},
		Outputs:          []string{"summary.json", "runtime/logs"},
		Artifacts:        map[string]string{"summary": "summary.json"},
		Evidence:         evidence,
		Blockers:         blockers,
		Warnings:         warnings,
	})
}

func gateEvaluateNodeFromLiveSummary(summary LiveRunSummary) WorkflowNodeResult {
	evidence := map[string]interface{}{
		"claim":                "gate_evaluate_completed_from_live_summary",
		"probe_output_count":   len(summary.GateEvaluation.ProbeOutputs),
		"rosbag_profile_count": len(summary.GateEvaluation.RosbagProfiles),
		"landing_ok":           summary.GateEvaluation.Landing.OK,
		"landing_blocked":      summary.GateEvaluation.Landing.Blocked,
		"cohort_hover_health":  summary.CohortHoverHealth != nil,
		"hover_health_band":    summary.HoverHealthBand,
	}
	return workflowNode("gate-evaluate", "gate-evaluate", workflowNodeOptions{
		Mode:             "live",
		SideEffectPolicy: "none",
		Inputs:           []string{"summary.json", "runtime_plan.json", "probes", "rosbag"},
		Outputs:          []string{"summary.json"},
		Artifacts:        map[string]string{"summary": "summary.json"},
		Evidence:         evidence,
		Blockers:         append([]string(nil), summary.GateEvaluation.Blockers...),
	})
}

func BuildLiveResourceProbeSummary(bundle RuntimeSpecBundle, options SimWorkflowOptions) LiveResourceProbeSummary {
	if !options.LiveResourceCheck {
		return staticLiveResourceProbe()
	}
	timeout := options.ResourceCheckTimeout
	if timeout <= 0 {
		timeout = 10 * time.Second
	}
	resourceClient := options.DockerResourceClient
	closeClient := false
	if resourceClient == nil {
		client, err := simruntime.NewSDKDockerResourceProbeClient()
		if err != nil {
			failed := CheckResult{
				Status:   "fail",
				Required: true,
				Evidence: []string{"docker sdk client initialization"},
				Blockers: []string{err.Error()},
			}
			return LiveResourceProbeSummary{
				Enabled:    true,
				Claim:      "sdk_probe_blocked_before_runtime_services",
				Provenance: DockerResourceProvenance{Client: "docker-sdk"},
				DockerInfo: failed,
				DockerUser: failed,
			}
		}
		resourceClient = client
		closeClient = true
	}
	if closeClient {
		defer func() {
			if closer, ok := resourceClient.(simruntime.DockerResourceProbeCloser); ok {
				_ = closer.Close()
			}
		}()
	}
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	daemon, err := resourceClient.ProbeDaemon(ctx)
	provenance := dockerResourceProvenanceFromProbe(daemon)
	dockerInfo := daemonCheckResult(daemon, err)
	dockerUser := dockerUserCheckResult(daemon, err)
	images := imageRefsFromSpecs(bundle)
	imageChecks := make([]ImageAvailabilityCheck, 0, len(images))
	for _, image := range images {
		inspect, err := resourceClient.InspectImage(ctx, image.Image)
		imageChecks = append(imageChecks, ImageAvailabilityCheck{
			Image: image.Image,
			Check: imageInspectCheckResult(image.Image, inspect, err),
		})
	}
	networks := sortedNetworks(bundle)
	networkChecks := make([]NetworkAvailabilityCheck, 0, len(networks))
	for _, network := range networks {
		if network == "host" || network == "none" || network == "bridge" {
			networkChecks = append(networkChecks, NetworkAvailabilityCheck{
				Network: network,
				Check:   CheckResult{Status: "pass", Required: true, Evidence: []string{"built-in docker network " + network}},
			})
			continue
		}
		inspect, err := resourceClient.InspectNetwork(ctx, network)
		networkChecks = append(networkChecks, NetworkAvailabilityCheck{
			Network: network,
			Check:   networkInspectCheckResult(network, inspect, err),
		})
	}
	return LiveResourceProbeSummary{
		Enabled:       true,
		Claim:         "checked_by_docker_sdk_without_starting_runtime_services",
		Provenance:    provenance,
		DockerInfo:    dockerInfo,
		DockerUser:    dockerUser,
		ImageChecks:   imageChecks,
		NetworkChecks: networkChecks,
	}
}

func staticLiveResourceProbe() LiveResourceProbeSummary {
	notRequested := CheckResult{Status: "not_requested", Required: false, Evidence: []string{"static prepare does not probe live Docker resources"}}
	return LiveResourceProbeSummary{
		Enabled:    false,
		Claim:      "not_requested",
		DockerInfo: notRequested,
		DockerUser: notRequested,
	}
}

func dockerResourceProvenanceFromProbe(probe simruntime.DockerDaemonProbe) DockerResourceProvenance {
	rootlessClaim := "unknown"
	if len(probe.SecurityOptions) > 0 {
		rootlessClaim = "false"
		if probe.Rootless {
			rootlessClaim = "true"
		}
	}
	remoteEvidence := "local_or_default_docker_host"
	if strings.TrimSpace(probe.Host) != "" && !strings.HasPrefix(probe.Host, "unix://") {
		remoteEvidence = "non_unix_docker_host"
	}
	return DockerResourceProvenance{
		Client:                "docker-sdk",
		Host:                  probe.Host,
		ServerVersion:         probe.ServerVersion,
		APIVersion:            probe.APIVersion,
		MinAPIVersion:         probe.MinAPIVersion,
		OSType:                probe.OSType,
		OperatingSystem:       probe.OperatingSystem,
		Architecture:          probe.Architecture,
		DockerRootDir:         probe.DockerRootDir,
		Rootless:              probe.Rootless,
		RootlessClaim:         rootlessClaim,
		SecurityOptions:       append([]string(nil), probe.SecurityOptions...),
		RemoteContextEvidence: remoteEvidence,
	}
}

func daemonCheckResult(probe simruntime.DockerDaemonProbe, err error) CheckResult {
	evidence := []string{"docker sdk daemon ping/version"}
	if probe.Host != "" {
		evidence = append(evidence, "host="+probe.Host)
	}
	if probe.ServerVersion != "" {
		evidence = append(evidence, "server_version="+probe.ServerVersion)
	}
	if probe.APIVersion != "" {
		evidence = append(evidence, "api_version="+probe.APIVersion)
	}
	if probe.OSType != "" {
		evidence = append(evidence, "os_type="+probe.OSType)
	}
	warnings := append([]string(nil), probe.Warnings...)
	if err != nil {
		return CheckResult{Status: "fail", Required: true, Evidence: evidence, Warnings: warnings, Blockers: []string{err.Error()}}
	}
	return CheckResult{Status: "pass", Required: true, Evidence: evidence, Warnings: warnings}
}

func dockerUserCheckResult(probe simruntime.DockerDaemonProbe, err error) CheckResult {
	evidence := []string{"docker sdk daemon reachable with current process credentials"}
	if probe.Host != "" {
		evidence = append(evidence, "host="+probe.Host)
	}
	if err != nil {
		return CheckResult{Status: "fail", Required: true, Evidence: evidence, Blockers: []string{err.Error()}}
	}
	return CheckResult{Status: "pass", Required: true, Evidence: evidence}
}

func imageInspectCheckResult(imageRef string, inspect simruntime.DockerImageProbe, err error) CheckResult {
	evidence := []string{"docker sdk image inspect " + imageRef}
	if inspect.ID != "" {
		evidence = append(evidence, "id="+shortDockerID(inspect.ID))
	}
	if inspect.OS != "" || inspect.Arch != "" {
		evidence = append(evidence, strings.Trim(strings.Join([]string{inspect.OS, inspect.Arch}, "/"), "/"))
	}
	if len(inspect.RepoTags) > 0 {
		evidence = append(evidence, "repo_tags="+strings.Join(inspect.RepoTags, ","))
	}
	if err != nil {
		return CheckResult{Status: "fail", Required: true, Evidence: evidence, Blockers: []string{err.Error()}}
	}
	return CheckResult{Status: "pass", Required: true, Evidence: evidence}
}

func networkInspectCheckResult(networkName string, inspect simruntime.DockerNetworkProbe, err error) CheckResult {
	evidence := []string{"docker sdk network inspect " + networkName}
	if inspect.ID != "" {
		evidence = append(evidence, "id="+shortDockerID(inspect.ID))
	}
	if inspect.Driver != "" {
		evidence = append(evidence, "driver="+inspect.Driver)
	}
	if inspect.Scope != "" {
		evidence = append(evidence, "scope="+inspect.Scope)
	}
	if err != nil {
		return CheckResult{Status: "fail", Required: true, Evidence: evidence, Blockers: []string{err.Error()}}
	}
	return CheckResult{Status: "pass", Required: true, Evidence: evidence}
}

func shortDockerID(id string) string {
	id = strings.TrimPrefix(strings.TrimSpace(id), "sha256:")
	if len(id) > 12 {
		return id[:12]
	}
	return id
}

func combinedImageAvailabilityCheck(checks []ImageAvailabilityCheck) CheckResult {
	if len(checks) == 0 {
		return passRequired(false, "no image refs found")
	}
	blockers := []string{}
	evidence := []string{}
	for _, check := range checks {
		evidence = append(evidence, check.Image+":"+check.Check.Status)
		for _, blocker := range check.Check.Blockers {
			blockers = append(blockers, check.Image+":"+blocker)
		}
	}
	if len(blockers) > 0 {
		return CheckResult{Status: "fail", Required: true, Evidence: evidence, Blockers: blockers}
	}
	return CheckResult{Status: "pass", Required: true, Evidence: evidence}
}

func combinedNetworkAvailabilityCheck(checks []NetworkAvailabilityCheck) CheckResult {
	if len(checks) == 0 {
		return CheckResult{Status: "pass", Required: true, Evidence: []string{"no explicit docker networks in service plan"}}
	}
	blockers := []string{}
	evidence := []string{}
	for _, check := range checks {
		evidence = append(evidence, check.Network+":"+check.Check.Status)
		for _, blocker := range check.Check.Blockers {
			blockers = append(blockers, check.Network+":"+blocker)
		}
	}
	if len(blockers) > 0 {
		return CheckResult{Status: "fail", Required: true, Evidence: evidence, Blockers: blockers}
	}
	return CheckResult{Status: "pass", Required: true, Evidence: evidence}
}

type workflowNodeOptions struct {
	Mode             string
	SideEffectPolicy string
	Inputs           []string
	Outputs          []string
	Artifacts        map[string]string
	Evidence         map[string]interface{}
	Blockers         []string
	Warnings         []string
	Skipped          bool
	SkipReason       string
}

func nodeFromChecks(nodeID string, stage string, checks map[string]CheckResult, inputs []string, outputs []string) WorkflowNodeResult {
	blockers := []string{}
	warnings := []string{}
	for name, check := range checks {
		for _, blocker := range check.Blockers {
			blockers = append(blockers, name+":"+blocker)
		}
		for _, warning := range check.Warnings {
			warnings = append(warnings, name+":"+warning)
		}
	}
	sort.Strings(blockers)
	sort.Strings(warnings)
	status := "ok"
	if len(blockers) > 0 {
		status = "blocked"
	}
	artifacts := artifactsFromOutputs(outputs)
	evidence := map[string]interface{}{"check_count": len(checks)}
	return WorkflowNodeResult{
		ID:               nodeID,
		Kind:             stage,
		Deps:             workflowDeps(nodeID),
		Required:         true,
		Mode:             "dry_run",
		Domain:           "sim",
		SideEffectPolicy: sideEffectPolicy(stage),
		SummaryPath:      summaryPathFromArtifacts(artifacts, outputs),
		ArtifactPaths:    append([]string(nil), outputs...),
		Status:           status,
		OK:               len(blockers) == 0,
		Blocked:          len(blockers) > 0,
		Blockers:         blockers,
		Warnings:         warnings,
		Inputs:           append([]string(nil), inputs...),
		Outputs:          append([]string(nil), outputs...),
		Artifacts:        artifacts,
		Evidence:         evidence,
		StartedAt:        time.Now().UTC().Format(time.RFC3339),
		FinishedAt:       time.Now().UTC().Format(time.RFC3339),
		CreatedAt:        time.Now().UTC().Format(time.RFC3339),
	}
}

func workflowNode(nodeID string, stage string, options workflowNodeOptions) WorkflowNodeResult {
	status := "ok"
	if options.Skipped {
		status = "skipped"
	} else if len(options.Blockers) > 0 {
		status = "blocked"
	}
	mode := options.Mode
	if mode == "" {
		mode = "dry_run"
	}
	evidence := options.Evidence
	if evidence == nil {
		evidence = map[string]interface{}{}
	}
	artifacts := options.Artifacts
	if artifacts == nil {
		artifacts = artifactsFromOutputs(options.Outputs)
	}
	now := time.Now().UTC().Format(time.RFC3339)
	return WorkflowNodeResult{
		ID:               nodeID,
		Kind:             stage,
		Deps:             workflowDeps(nodeID),
		Required:         true,
		Mode:             mode,
		Domain:           "sim",
		SideEffectPolicy: options.SideEffectPolicy,
		SummaryPath:      summaryPathFromArtifacts(artifacts, options.Outputs),
		ArtifactPaths:    append([]string(nil), options.Outputs...),
		Status:           status,
		OK:               !options.Skipped && len(options.Blockers) == 0,
		Blocked:          !options.Skipped && len(options.Blockers) > 0,
		Skipped:          options.Skipped,
		SkipReason:       options.SkipReason,
		Blockers:         append([]string(nil), options.Blockers...),
		Warnings:         append([]string(nil), options.Warnings...),
		Inputs:           append([]string(nil), options.Inputs...),
		Outputs:          append([]string(nil), options.Outputs...),
		Artifacts:        artifacts,
		Evidence:         evidence,
		StartedAt:        now,
		FinishedAt:       now,
		CreatedAt:        now,
	}
}

func skippedWorkflowNode(nodeID string, stage string, reason string) WorkflowNodeResult {
	return workflowNode(nodeID, stage, workflowNodeOptions{
		Mode:             "dry_run",
		SideEffectPolicy: sideEffectPolicy(stage),
		Inputs:           workflowSkippedInputs(nodeID),
		Outputs:          workflowSkippedOutputs(nodeID),
		Artifacts:        artifactsFromOutputs(workflowSkippedOutputs(nodeID)),
		Evidence:         map[string]interface{}{"claim": reason},
		Skipped:          true,
		SkipReason:       reason,
	})
}

func replaceWorkflowNode(nodes []WorkflowNodeResult, replacement WorkflowNodeResult) []WorkflowNodeResult {
	for index, node := range nodes {
		if node.ID == replacement.ID {
			nodes[index] = replacement
			return nodes
		}
	}
	return append(nodes, replacement)
}

func applyWorkflowDependencies(nodes []WorkflowNodeResult) []WorkflowNodeResult {
	result := append([]WorkflowNodeResult(nil), nodes...)
	blocked := map[string]bool{}
	for index, node := range result {
		if node.Required {
			for _, dep := range node.Deps {
				if blocked[dep] {
					result[index] = skippedByDependency(node, dep)
					break
				}
			}
		}
		if result[index].Blocked {
			id := result[index].ID
			blocked[id] = true
		}
	}
	return result
}

func skippedByDependency(node WorkflowNodeResult, dep string) WorkflowNodeResult {
	node.Status = "skipped"
	node.OK = false
	node.Blocked = false
	node.Skipped = true
	node.SkipReason = "blocked_by_dependency:" + dep
	node.Blockers = nil
	if node.Evidence == nil {
		node.Evidence = map[string]interface{}{}
	}
	node.Evidence["skip_reason"] = node.SkipReason
	node.FinishedAt = time.Now().UTC().Format(time.RFC3339)
	return node
}

func workflowDeps(nodeID string) []string {
	switch nodeID {
	case "prepare":
		return []string{"preflight"}
	case "common-doctor":
		return []string{"prepare"}
	case "task-doctor":
		return []string{"common-doctor"}
	case "runtime-execute":
		return []string{"task-doctor"}
	case "gate-evaluate":
		return []string{"runtime-execute"}
	default:
		return nil
	}
}

func sideEffectPolicy(stage string) string {
	switch stage {
	case "preflight", "common-doctor", "task-doctor", "gate-evaluate":
		return "none"
	case "prepare":
		return "plan_only"
	case "runtime-execute":
		return "runtime_start"
	default:
		return "none"
	}
}

func workflowSkippedInputs(nodeID string) []string {
	switch nodeID {
	case "runtime-execute":
		return []string{artifactlayout.DAGRel("task_doctor_summary.json"), "runtime_plan.json"}
	case "gate-evaluate":
		return []string{"summary.json", "runtime_plan.json", "probes", "rosbag"}
	default:
		return nil
	}
}

func workflowSkippedOutputs(nodeID string) []string {
	switch nodeID {
	case "runtime-execute":
		return []string{"summary.json", "runtime/logs"}
	case "gate-evaluate":
		return []string{"summary.json"}
	default:
		return nil
	}
}

func artifactsFromOutputs(outputs []string) map[string]string {
	artifacts := map[string]string{}
	for _, output := range outputs {
		base := filepath.Base(output)
		switch base {
		case "preflight_summary.json":
			artifacts["summary"] = output
		case "prepare_summary.json":
			artifacts["summary"] = output
		case "common_doctor_summary.json", "common_doctor_live_summary.json":
			artifacts["summary"] = output
		case "task_doctor_summary.json":
			artifacts["summary"] = output
		case "workflow_summary.json":
			artifacts["summary"] = output
		case "doctor_result.json":
			artifacts["doctor_result"] = output
		case "runtime_plan.json":
			artifacts["runtime_plan"] = output
		case "summary.json":
			artifacts["summary"] = output
		}
	}
	if len(artifacts) == 0 {
		return nil
	}
	return artifacts
}

func summaryPathFromArtifacts(artifacts map[string]string, outputs []string) string {
	if artifacts != nil {
		if summary := artifacts["summary"]; summary != "" {
			return summary
		}
	}
	if len(outputs) > 0 {
		return outputs[0]
	}
	return ""
}

func passRequired(ok bool, evidence string) CheckResult {
	if ok {
		return CheckResult{Status: "pass", Required: true, Evidence: []string{evidence}}
	}
	return CheckResult{Status: "fail", Required: true, Evidence: []string{evidence}, Blockers: []string{"required check failed"}}
}

func deferred(evidence string) CheckResult {
	return CheckResult{Status: "deferred_to_runtime", Required: true, Evidence: []string{evidence}}
}

func optionalDeferred(evidence string) CheckResult {
	return CheckResult{Status: "not_required_for_static_prepare", Required: false, Evidence: []string{evidence}}
}

func imageRefsFromSpecs(bundle RuntimeSpecBundle) []ImageRefSummary {
	seen := map[string]bool{}
	add := func(image string) {
		image = strings.TrimSpace(image)
		if image == "" || seen[image] {
			return
		}
		seen[image] = true
	}
	for _, spec := range bundle.Services {
		add(spec.Image)
	}
	for _, spec := range bundle.Probes {
		add(spec.Image)
	}
	if bundle.StartupReadinessProbe != nil {
		add(bundle.StartupReadinessProbe.Image)
	}
	for _, spec := range bundle.Rosbags {
		add(spec.Image)
	}
	images := make([]ImageRefSummary, 0, len(seen))
	for image := range seen {
		images = append(images, ImageRefSummary{Image: image, Tag: imageTag(image), RefOK: imageHasTagOrDigest(image)})
	}
	sort.Slice(images, func(i, j int) bool { return images[i].Image < images[j].Image })
	return images
}

func imageTag(image string) string {
	if strings.Contains(image, "@") {
		return strings.TrimSpace(strings.SplitN(image, "@", 2)[1])
	}
	lastSlash := strings.LastIndex(image, "/")
	lastColon := strings.LastIndex(image, ":")
	if lastColon > lastSlash {
		return image[lastColon+1:]
	}
	return ""
}

func imageHasTagOrDigest(image string) bool {
	return strings.Contains(image, "@") || imageTag(image) != ""
}

func allImageRefsTagged(images []ImageRefSummary) bool {
	if len(images) == 0 {
		return false
	}
	for _, image := range images {
		if !image.RefOK {
			return false
		}
	}
	return true
}

func forbiddenConfigEnabled(project config.ProjectConfig) bool {
	return project.SlamBackend.UsesGazeboTruthAsInput || project.Landing.UsesGazeboTruthAsInput
}

func buildResourceProvenance(project config.ProjectConfig, artifactDir string, bundle RuntimeSpecBundle, liveProbe LiveResourceProbeSummary) ResourceProvenance {
	networks := sortedNetworks(bundle)
	liveClaim := "not_requested"
	daemonClaim := "not_started_in_prepare; runtime-execute validates daemon before start"
	if liveProbe.Enabled {
		liveClaim = liveProbe.Claim
		if liveProbe.DockerInfo.Status == "pass" {
			daemonClaim = "live_checked_ok"
		} else {
			daemonClaim = "live_checked_blocked"
		}
	}
	return ResourceProvenance{
		RuntimeMode:            project.Runtime.Mode,
		Backend:                project.Runtime.Backend,
		DockerDaemonClaim:      daemonClaim,
		DockerNetworkClaim:     "planned_from_service_specs",
		DockerHost:             liveProbe.Provenance.Host,
		DockerServerVersion:    liveProbe.Provenance.ServerVersion,
		DockerAPIVersion:       liveProbe.Provenance.APIVersion,
		DockerOSType:           liveProbe.Provenance.OSType,
		DockerRootDir:          liveProbe.Provenance.DockerRootDir,
		DockerRootlessClaim:    liveProbe.Provenance.RootlessClaim,
		LiveResourceProbeClaim: liveClaim,
		DockerNetworks:         networks,
		Images:                 imageRefsFromSpecs(bundle),
		WorkspaceMounts:        workspaceMounts(bundle),
		ContainerWorkspace:     containerWorkspace(project),
		ContainerArtifactDir:   inferContainerArtifactDir(project, artifactDir, bundle),
		SimulationSourceClaim:  "docker_sitl_gazebo_sources_only; no real serial or real FCU evidence consumed",
	}
}

func servicePlanEntries(specs []simruntime.ServiceSpec) []ServicePlanEntry {
	entries := make([]ServicePlanEntry, 0, len(specs))
	for _, spec := range specs {
		entries = append(entries, ServicePlanEntry{
			Name:          spec.Name,
			Role:          spec.ServiceRole,
			Backend:       "docker",
			Image:         spec.Image,
			ContainerName: spec.ContainerName,
			Command:       append([]string(nil), spec.Command...),
			Networks:      append([]string(nil), spec.Networks...),
			Required:      spec.Required,
			Restartable:   spec.Restartable,
			LogPath:       spec.LogPath,
		})
	}
	return entries
}

func probePlanEntries(bundle RuntimeSpecBundle) []ProbePlanEntry {
	specs := append([]simruntime.ProbeSpec(nil), bundle.Probes...)
	if bundle.StartupReadinessProbe != nil {
		specs = append(specs, *bundle.StartupReadinessProbe)
	}
	entries := make([]ProbePlanEntry, 0, len(specs))
	for _, spec := range specs {
		entries = append(entries, ProbePlanEntry{
			Name:       spec.Name,
			Role:       spec.ServiceRole,
			Backend:    "docker",
			Image:      spec.Image,
			Command:    append([]string(nil), spec.Command...),
			OutputPath: spec.OutputPath,
			TimeoutSec: spec.TimeoutSec,
			Required:   spec.Required,
			LogPath:    spec.LogPath,
		})
	}
	return entries
}

func rosbagPlanEntries(specs []simruntime.RosbagSpec) []RosbagPlanEntry {
	entries := make([]RosbagPlanEntry, 0, len(specs))
	for _, spec := range specs {
		entries = append(entries, RosbagPlanEntry{
			Name:          spec.Name,
			Role:          spec.ServiceRole,
			Backend:       "docker",
			Image:         spec.Image,
			TopicsProfile: spec.TopicsProfile,
			OutputPath:    spec.OutputPath,
			DurationSec:   spec.DurationSec,
			Storage:       spec.Storage,
			Networks:      append([]string(nil), spec.Networks...),
			Required:      spec.Required,
			LogPath:       spec.LogPath,
		})
	}
	return entries
}

func buildForbiddenInputAudit(bundle RuntimeSpecBundle) ForbiddenInputAudit {
	tokens := []string{
		"/gazebo/model/odometry",
		"/gazebo/tf",
		"/scan_ideal",
		"/truth/odom",
		"ground_truth",
		"truth_diagnostic",
		"diagnostic_odom",
	}
	matches := []ForbiddenMatch{}
	contexts := 0
	scan := func(kind string, name string, values []string) {
		for _, value := range values {
			contexts++
			for _, token := range tokens {
				if strings.Contains(value, token) {
					matches = append(matches, ForbiddenMatch{Kind: kind, Name: name, Token: token, Context: value})
				}
			}
		}
	}
	for _, spec := range bundle.Services {
		if spec.Name == "official_maze_overlay" {
			continue
		}
		scan("service_command", spec.Name, spec.Command)
		scan("service_env", spec.Name, envValues(spec.Env))
	}
	for _, spec := range bundle.Probes {
		scan("probe_command", spec.Name, spec.Command)
	}
	if bundle.StartupReadinessProbe != nil {
		scan("probe_command", bundle.StartupReadinessProbe.Name, bundle.StartupReadinessProbe.Command)
	}
	for _, spec := range bundle.Rosbags {
		scan("rosbag_output", spec.Name, []string{spec.OutputPath, spec.TopicsProfile})
	}
	return ForbiddenInputAudit{
		OK:              len(matches) == 0,
		Claim:           "static service/probe/rosbag command and env audit; live topic flow checked by runtime probes",
		ForbiddenTokens: tokens,
		ScannedContexts: contexts,
		Matches:         matches,
		ReviewOnly: map[string]string{
			"/navlab/official_maze/map": "official maze overlay may be published for review, but is not accepted as SLAM/ExternalNav/controller/gate input",
		},
	}
}

func envValues(env map[string]string) []string {
	values := make([]string, 0, len(env))
	for key, value := range env {
		values = append(values, key+"="+value)
	}
	sort.Strings(values)
	return values
}

func sortedNetworks(bundle RuntimeSpecBundle) []string {
	seen := map[string]bool{}
	for _, spec := range bundle.Services {
		for _, network := range spec.Networks {
			seen[network] = true
		}
	}
	for _, spec := range bundle.Probes {
		for _, network := range spec.Networks {
			seen[network] = true
		}
	}
	if bundle.StartupReadinessProbe != nil {
		for _, network := range bundle.StartupReadinessProbe.Networks {
			seen[network] = true
		}
	}
	for _, spec := range bundle.Rosbags {
		for _, network := range spec.Networks {
			seen[network] = true
		}
	}
	networks := make([]string, 0, len(seen))
	for network := range seen {
		networks = append(networks, network)
	}
	sort.Strings(networks)
	return networks
}

func workspaceMounts(bundle RuntimeSpecBundle) []VolumeMountSummary {
	seen := map[string]VolumeMountSummary{}
	add := func(mount simruntime.VolumeMount) {
		key := mount.Source + "=>" + mount.Target + ":" + mount.Mode
		if key == "=>:" {
			return
		}
		seen[key] = VolumeMountSummary{Source: mount.Source, Target: mount.Target, Mode: mount.Mode}
	}
	for _, spec := range bundle.Services {
		for _, mount := range spec.Volumes {
			add(mount)
		}
	}
	for _, spec := range bundle.Probes {
		for _, mount := range spec.Volumes {
			add(mount)
		}
	}
	if bundle.StartupReadinessProbe != nil {
		for _, mount := range bundle.StartupReadinessProbe.Volumes {
			add(mount)
		}
	}
	for _, spec := range bundle.Rosbags {
		for _, mount := range spec.Volumes {
			add(mount)
		}
	}
	mounts := make([]VolumeMountSummary, 0, len(seen))
	for _, mount := range seen {
		mounts = append(mounts, mount)
	}
	sort.Slice(mounts, func(i, j int) bool {
		if mounts[i].Source == mounts[j].Source {
			return mounts[i].Target < mounts[j].Target
		}
		return mounts[i].Source < mounts[j].Source
	})
	return mounts
}

func containerWorkspace(project config.ProjectConfig) string {
	if strings.TrimSpace(project.Orchestration.Runtime.Docker.WorkspaceContainerPath) != "" {
		return project.Orchestration.Runtime.Docker.WorkspaceContainerPath
	}
	return "/workspace"
}

func inferContainerArtifactDir(project config.ProjectConfig, artifactDir string, bundle RuntimeSpecBundle) string {
	for _, spec := range bundle.Services {
		if strings.TrimSpace(spec.CWD) != "" {
			for _, mount := range spec.Volumes {
				if strings.TrimSpace(mount.Target) != "" && strings.HasPrefix(artifactDir, mount.Source) {
					rel, err := filepath.Rel(mount.Source, artifactDir)
					if err == nil {
						return filepath.ToSlash(filepath.Join(mount.Target, rel))
					}
				}
			}
		}
	}
	workspace := containerWorkspace(project)
	return filepath.ToSlash(filepath.Join(workspace, "artifacts", "sim"))
}

func requiredCommonTopics(plan Plan) []string {
	seen := map[string]bool{}
	for _, rosbag := range plan.Execution.RosbagRecords {
		for _, topic := range rosbag.Topics {
			seen[topic] = true
		}
	}
	topics := make([]string, 0, len(seen))
	for topic := range seen {
		topics = append(topics, topic)
	}
	sort.Strings(topics)
	return topics
}

func plannedTopic(topic string, topics []string) CheckResult {
	for _, planned := range topics {
		if planned == topic {
			return CheckResult{Status: "planned", Required: false, Evidence: []string{"topic=" + topic}}
		}
	}
	return CheckResult{Status: "not_planned_or_live_only", Required: false, Evidence: []string{"topic=" + topic}}
}

func plannedHelper(plan Plan, helperID string) CheckResult {
	for _, helper := range plan.Helpers {
		if helper.ID == helperID {
			return CheckResult{Status: "planned", Required: false, Evidence: []string{"helper=" + helperID}}
		}
	}
	return CheckResult{Status: "not_applicable", Required: false, Evidence: []string{"helper=" + helperID}}
}

func blockersFromNodes(nodes []WorkflowNodeResult) []string {
	blockers := []string{}
	for _, node := range nodes {
		for _, blocker := range node.Blockers {
			blockers = append(blockers, node.ID+":"+blocker)
		}
	}
	sort.Strings(blockers)
	return blockers
}

func itoa(value int) string {
	if value == 0 {
		return "0"
	}
	digits := []byte{}
	for value > 0 {
		digits = append([]byte{byte('0' + value%10)}, digits...)
		value /= 10
	}
	return string(digits)
}

func formatFloat(value float64) string {
	return strconv.FormatFloat(value, 'f', -1, 64)
}
