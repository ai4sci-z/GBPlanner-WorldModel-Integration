package helpers

import (
	"fmt"
	"sort"
	"strings"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
	"navlab/orchestration-sim/internal/config"
)

type ExecutionPlan struct {
	Status             string                 `json:"status"`
	TaskID             string                 `json:"task_id"`
	DurationSec        float64                `json:"duration_sec"`
	SimulationProfile  string                 `json:"simulation_profile"`
	RuntimeMode        string                 `json:"runtime_mode"`
	GeneratedArtifacts []ArtifactPlan         `json:"generated_artifacts"`
	RuntimeServices    []RuntimeServicePlan   `json:"runtime_services"`
	ROSProbes          []ROSProbePlan         `json:"ros_probes"`
	RosbagRecords      []RosbagRecordPlan     `json:"rosbag_records"`
	ResultGates        []ResultGatePlan       `json:"result_gates"`
	TaskParameters     map[string]interface{} `json:"task_parameters,omitempty"`
	Notes              []string               `json:"notes,omitempty"`
}

type ArtifactPlan struct {
	HelperID string   `json:"helper_id"`
	Kind     string   `json:"kind"`
	Path     string   `json:"path"`
	Inputs   []string `json:"inputs,omitempty"`
}

type RuntimeServicePlan struct {
	HelperID      string            `json:"helper_id"`
	ServiceName   string            `json:"service_name"`
	ContainerName string            `json:"container_name,omitempty"`
	ImageRef      string            `json:"image_ref,omitempty"`
	Network       string            `json:"network,omitempty"`
	Command       []string          `json:"command,omitempty"`
	Env           map[string]string `json:"env,omitempty"`
	SideEffect    bool              `json:"side_effect"`
	Status        string            `json:"status"`
}

type ROSProbePlan struct {
	HelperID     string   `json:"helper_id"`
	Name         string   `json:"name"`
	ScriptPath   string   `json:"script_path"`
	OutputPath   string   `json:"output_path"`
	Topics       []string `json:"topics"`
	RuntimeImage string   `json:"runtime_image,omitempty"`
	Status       string   `json:"status"`
}

type RosbagRecordPlan struct {
	HelperID       string   `json:"helper_id"`
	Name           string   `json:"name"`
	ProfilePath    string   `json:"profile_path"`
	OutputDir      string   `json:"output_dir"`
	Topics         []string `json:"topics"`
	RequiredTopics []string `json:"required_topics,omitempty"`
	Command        string   `json:"command,omitempty"`
	Status         string   `json:"status"`
}

type ResultGatePlan struct {
	HelperID string   `json:"helper_id"`
	Name     string   `json:"name"`
	Inputs   []string `json:"inputs"`
	Outputs  []string `json:"outputs"`
	Status   string   `json:"status"`
}

func BuildExecutionPlan(
	task config.TaskConfig,
	durationSec float64,
	simulationProfile string,
	helperDefinitions []Definition,
) (ExecutionPlan, error) {
	plan := ExecutionPlan{
		Status:            "dry_run_only",
		TaskID:            task.ID,
		DurationSec:       durationSec,
		SimulationProfile: simulationProfile,
		RuntimeMode:       "planned_simulation",
		TaskParameters: map[string]interface{}{
			"task":             task.Task,
			"configured_parts": sectionNames(task.Sections),
		},
		Notes: []string{
			"Go orchestration now owns runtime/probe/task execution planning; live Docker and ROS side effects stay disabled until the runner is wired.",
			"Generated runtime scripts may execute Python inside ROS containers because navlab runtime nodes are still Python, but orchestration no longer depends on Python helpers.",
		},
	}
	helperSet := map[string]bool{}
	for _, helper := range helperDefinitions {
		helperSet[helper.ID] = true
	}

	if helperSet["sensors"] {
		addSensorsExecution(&plan, task)
	}
	if helperSet["slam"] {
		addSlamExecution(&plan)
	}
	if helperSet["fcu-controller"] {
		addFCUExecution(&plan, task)
	}
	if helperSet["frame-contract"] {
		addFrameContractExecution(&plan, task)
	}
	if helperSet["slam-hover"] {
		addSlamHoverExecution(&plan, task, durationSec)
	}
	if helperSet["slam-only"] {
		addSlamOnlyExecution(&plan, task, durationSec)
	}
	if helperSet["scan-stabilization"] {
		addScanStabilizationExecution(&plan, task, durationSec)
	}
	if helperSet["exploration-workflow"] {
		addExplorationWorkflowExecution(&plan, task, durationSec, simulationProfile)
	}
	if helperSet["nav2-navigation-workflow"] {
		addNav2NavigationWorkflowExecution(&plan, task, durationSec)
	}
	if helperSet["scan-robustness-workflow"] {
		addScanRobustnessWorkflowExecution(&plan, task, durationSec)
	}
	if helperSet["landing"] {
		inputs := []string{"summary.json", "controller_summary.json"}
		if plan.TaskID == "hover" {
			inputs = []string{"summary.json", "mission_summary.json"}
		}
		plan.ResultGates = append(plan.ResultGates, ResultGatePlan{
			HelperID: "landing",
			Name:     "landing_acceptance",
			Inputs:   inputs,
			Outputs:  []string{"landing acceptance blockers"},
			Status:   "ported_basic",
		})
	}
	if plan.TaskID == "hover" {
		moveRuntimeServiceBefore(&plan, "external_nav_source_selector", "slam_backend")
	}
	applyArtifactLayout(&plan)
	return plan, nil
}

func applyArtifactLayout(plan *ExecutionPlan) {
	for index := range plan.GeneratedArtifacts {
		artifact := &plan.GeneratedArtifacts[index]
		switch {
		case strings.Contains(artifact.Kind, "probe_script"):
			artifact.Path = artifactlayout.ProbeRel(artifact.Path)
		case strings.Contains(artifact.Kind, "script"):
			artifact.Path = artifactlayout.RuntimeScriptRel(artifact.Path)
		case artifact.Kind == "foxglove_notes":
			artifact.Path = artifactlayout.AuditRel(artifact.Path)
		default:
			artifact.Path = artifactlayout.RuntimeConfigRel(artifact.Path)
		}
	}
	for index := range plan.ROSProbes {
		probe := &plan.ROSProbes[index]
		probe.ScriptPath = artifactlayout.ProbeRel(probe.ScriptPath)
		probe.OutputPath = artifactlayout.ProbeRel(probe.OutputPath)
	}
}

func moveRuntimeServiceBefore(plan *ExecutionPlan, serviceName string, beforeServiceName string) {
	sourceIndex := -1
	targetIndex := -1
	for idx, service := range plan.RuntimeServices {
		if service.ServiceName == serviceName {
			sourceIndex = idx
		}
		if service.ServiceName == beforeServiceName {
			targetIndex = idx
		}
	}
	if sourceIndex < 0 || targetIndex < 0 || sourceIndex < targetIndex {
		return
	}
	service := plan.RuntimeServices[sourceIndex]
	plan.RuntimeServices = append(plan.RuntimeServices[:sourceIndex], plan.RuntimeServices[sourceIndex+1:]...)
	plan.RuntimeServices = append(plan.RuntimeServices[:targetIndex], append([]RuntimeServicePlan{service}, plan.RuntimeServices[targetIndex:]...)...)
}

func addSensorsExecution(plan *ExecutionPlan, task config.TaskConfig) {
	spec := DefaultSensorRuntimeSpec()
	plan.GeneratedArtifacts = append(plan.GeneratedArtifacts,
		ArtifactPlan{HelperID: "sensors", Kind: "sdf_model_overlay", Path: "model_overlay.sdf", Inputs: []string{OfficialIrisWithLidarModel}},
		ArtifactPlan{HelperID: "sensors", Kind: "ardupilot_param_overlay", Path: "gazebo-iris-rangefinder.parm", Inputs: []string{OfficialGazeboIrisParams}},
		ArtifactPlan{HelperID: "sensors", Kind: "gazebo_sensor_runtime_toml", Path: "gazebo_sensor_runtime.toml", Inputs: []string{"vendor_profile.yaml"}},
	)
	plan.RuntimeServices = append(plan.RuntimeServices, RuntimeServicePlan{
		HelperID:      "sensors",
		ServiceName:   "gazebo_sensor",
		ContainerName: GazeboSensorContainer,
		ImageRef:      "images.gazebo_sensor",
		Network:       "host",
		Command:       []string{"bash", "-lc", "source /opt/ros/${ROS_DISTRO:-humble}/setup.bash && source /opt/navlab_sensor_ws/install/setup.bash && exec /opt/gazebo-sensor-venv/bin/python -m navlab.sim.gazebo_sensor.cli --runtime --log-file artifacts/runtime/logs/gazebo_sensor.runtime.log"},
		Env: map[string]string{
			"NAVLAB_CONFIG": spec.RuntimeConfigPath,
			"ROS_DOMAIN_ID": "from config.toml",
		},
		SideEffect: true,
		Status:     "planned_runtime",
	})
	plan.ROSProbes = append(plan.ROSProbes,
		ROSProbePlan{HelperID: "sensors", Name: "rangefinder_probe", ScriptPath: "rangefinder_probe.py", OutputPath: "rangefinder_probe.txt", Topics: []string{spec.RangefinderRangeTopic, spec.RangefinderStatusTopic}, RuntimeImage: "images.runtime", Status: "ported_script_generation"},
		ROSProbePlan{HelperID: "sensors", Name: "imu_probe", ScriptPath: "imu_probe.py", OutputPath: "imu_probe.txt", Topics: []string{spec.IMUOutputTopic}, RuntimeImage: "images.runtime", Status: "ported_script_generation"},
	)
	_ = task
}

func addSlamExecution(plan *ExecutionPlan) {
	spec := DefaultSlamRuntimeSpec()
	plan.GeneratedArtifacts = append(plan.GeneratedArtifacts, ArtifactPlan{
		HelperID: "slam",
		Kind:     "slam_runtime_toml",
		Path:     "slam_runtime.toml",
		Inputs:   []string{spec.ScanTopic, spec.IMUTopic, spec.MapFrameID + "->" + spec.BaseFrameID + " Cartographer TF"},
	}, ArtifactPlan{
		HelperID: "slam",
		Kind:     "external_nav_bridge_params_override",
		Path:     "external_nav_bridge_params.yaml",
		Inputs:   []string{spec.SlamOdomTopic, spec.MapFrameID + "->" + spec.BaseFrameID},
	})
	plan.RuntimeServices = append(plan.RuntimeServices, RuntimeServicePlan{
		HelperID:      "slam",
		ServiceName:   "slam_backend",
		ContainerName: SlamBackendContainer,
		ImageRef:      "images.slam",
		Network:       "host",
		Command:       []string{"bash", "-lc", "source /opt/ros/${ROS_DISTRO:-humble}/setup.bash && source /opt/navlab_ws/install/setup.bash && exec python3 -m navlab.common.slam.cli launch --config artifacts/runtime/config/slam_runtime.toml --backend cartographer > artifacts/runtime/logs/slam_backend.runtime.log 2>&1"},
		Env:           BaselineROSEnv(),
		SideEffect:    true,
		Status:        "ported_command_planning",
	})
}

func addFCUExecution(plan *ExecutionPlan, task config.TaskConfig) {
	spec := DefaultFCUControllerSpec()
	if value, ok := floatSectionValue(task.Sections, "fcu_controller", "takeoff_alt_m"); ok {
		spec.TakeoffAltM = value
	}
	if value, ok := floatSectionValue(task.Sections, "fcu_controller", "readiness_timeout_sec"); ok {
		spec.ReadinessTimeoutSec = value
	}
	plan.GeneratedArtifacts = append(plan.GeneratedArtifacts,
		ArtifactPlan{HelperID: "fcu-controller", Kind: "fcu_runtime_toml", Path: "fcu_controller_runtime.toml"},
		ArtifactPlan{HelperID: "fcu-controller", Kind: "controller_runtime_script", Path: "fcu_controller_runtime.py"},
	)
	plan.RuntimeServices = append(plan.RuntimeServices, RuntimeServicePlan{
		HelperID:      "fcu-controller",
		ServiceName:   "fcu_controller",
		ContainerName: FCUControllerContainer,
		ImageRef:      "images.runtime",
		Network:       "host",
		Command:       []string{"bash", "-lc", "source /opt/ros/${ROS_DISTRO:-humble}/setup.bash && source ${OFFICIAL_WS:-/opt/navlab_official_ws}/install/setup.bash && python3 artifacts/runtime/scripts/fcu_controller_runtime.py > artifacts/runtime/logs/fcu_controller.runtime.log 2>&1"},
		Env:           BaselineROSEnv(),
		SideEffect:    true,
		Status:        "ported_script_generation",
	})
	plan.ResultGates = append(plan.ResultGates, ResultGatePlan{
		HelperID: "fcu-controller",
		Name:     "controller_summary",
		Inputs:   []string{spec.ControllerStatusTopic, spec.OwnerStatusTopic, spec.FCUStateTopic},
		Outputs:  []string{"controller_summary.json", "controller blockers"},
		Status:   "ported_partial",
	})
}

func addFrameContractExecution(plan *ExecutionPlan, task config.TaskConfig) {
	spec := DefaultFrameContractSpec()
	plan.GeneratedArtifacts = append(plan.GeneratedArtifacts,
		ArtifactPlan{HelperID: "frame-contract", Kind: "frame_contract_runtime_toml", Path: "frame_contract_runtime.toml"},
		ArtifactPlan{HelperID: "frame-contract", Kind: "frame_probe_script", Path: "frame_contract_probe.py"},
	)
	plan.ROSProbes = append(plan.ROSProbes, ROSProbePlan{
		HelperID:   "frame-contract",
		Name:       "frame_contract_probe",
		ScriptPath: "frame_contract_probe.py",
		OutputPath: "frame_contract_probe.json",
		Topics: []string{
			"/tf", "/tf_static", spec.ScanTopic, spec.IMUTopic, spec.RangefinderRangeTopic,
			spec.FCUPoseTopic, spec.SlamOdomTopic, spec.ControllerStatusTopic,
		},
		RuntimeImage: "images.runtime",
		Status:       "ported_script_generation",
	})
	plan.ResultGates = append(plan.ResultGates, ResultGatePlan{
		HelperID: "frame-contract",
		Name:     "frame_contract_doctor",
		Inputs:   []string{"frame_contract_probe.json", "rosbag/metadata.yaml"},
		Outputs:  []string{"frame contract blockers"},
		Status:   "ported_partial",
	})
	_ = task
}

func addSlamHoverExecution(plan *ExecutionPlan, task config.TaskConfig, durationSec float64) {
	spec := DefaultSlamHoverSpec()
	scanReferenceSpec := DefaultScanReferenceDriftSpec()
	scanCorrectionSpec := DefaultScanReferenceCorrectionSpec()
	sourceSelectorSpec := DefaultExternalNavSourceSelectorSpec()
	if value, ok := floatSectionValue(task.Sections, "slam_hover", "hover_window_sec"); ok {
		spec.HoverWindowSec = value
	}
	plan.GeneratedArtifacts = append(plan.GeneratedArtifacts,
		ArtifactPlan{HelperID: "slam-hover", Kind: "slam_hover_runtime_toml", Path: "slam_hover_runtime.toml"},
		ArtifactPlan{HelperID: "slam-hover", Kind: "scan_reference_drift_runtime_script", Path: "scan_reference_drift_runtime.py", Inputs: []string{"navlab.sim.companion.nodes.scan_reference_drift"}},
		ArtifactPlan{HelperID: "slam-hover", Kind: "scan_reference_cartographer_odom_runtime_script", Path: "scan_reference_cartographer_odom_runtime.py", Inputs: []string{"navlab.sim.companion.nodes.scan_reference_drift"}},
		ArtifactPlan{HelperID: "slam-hover", Kind: "scan_reference_correction_runtime_script", Path: "scan_reference_correction_runtime.py", Inputs: []string{"navlab.sim.companion.nodes.scan_reference_correction"}},
		ArtifactPlan{HelperID: "slam-hover", Kind: "external_nav_source_selector_runtime_script", Path: "external_nav_source_selector_runtime.py", Inputs: []string{"navlab.sim.companion.nodes.external_nav_source_selector"}},
		ArtifactPlan{HelperID: "slam-hover", Kind: "hover_mission_runtime_script", Path: "hover_mission_runtime.py", Inputs: []string{"navlab.sim.companion.nodes.hover_mission"}},
		ArtifactPlan{HelperID: "slam-hover", Kind: "hover_probe_script", Path: "slam_hover_probe.py"},
		ArtifactPlan{HelperID: "slam-hover", Kind: "foxglove_notes", Path: "foxglove_notes.md"},
	)
	plan.RuntimeServices = append(plan.RuntimeServices,
		RuntimeServicePlan{
			HelperID:      "slam-hover",
			ServiceName:   "scan_reference_drift",
			ContainerName: "navlab-scan-reference-drift",
			ImageRef:      "images.runtime",
			Network:       "host",
			Command:       []string{"bash", "-lc", "source /opt/ros/${ROS_DISTRO:-humble}/setup.bash && source ${OFFICIAL_WS:-/opt/navlab_official_ws}/install/setup.bash && python3 artifacts/runtime/scripts/scan_reference_drift_runtime.py > artifacts/runtime/logs/scan_reference_drift.runtime.log 2>&1"},
			Env:           BaselineROSEnv(),
			SideEffect:    true,
			Status:        "diagnostic_only_no_control_output",
		},
		RuntimeServicePlan{
			HelperID:      "slam-hover",
			ServiceName:   "scan_reference_cartographer_odom",
			ContainerName: "navlab-scan-reference-cartographer-odom",
			ImageRef:      "images.runtime",
			Network:       "host",
			Command:       []string{"bash", "-lc", "source /opt/ros/${ROS_DISTRO:-humble}/setup.bash && source ${OFFICIAL_WS:-/opt/navlab_official_ws}/install/setup.bash && python3 artifacts/runtime/scripts/scan_reference_cartographer_odom_runtime.py > artifacts/runtime/logs/scan_reference_cartographer_odom.runtime.log 2>&1"},
			Env:           BaselineROSEnv(),
			SideEffect:    true,
			Status:        "scan_only_cartographer_odometry_prior_no_truth_input",
		},
		RuntimeServicePlan{
			HelperID:      "slam-hover",
			ServiceName:   "scan_reference_correction",
			ContainerName: "navlab-scan-reference-correction",
			ImageRef:      "images.runtime",
			Network:       "host",
			Command:       []string{"bash", "-lc", "source /opt/ros/${ROS_DISTRO:-humble}/setup.bash && source ${OFFICIAL_WS:-/opt/navlab_official_ws}/install/setup.bash && python3 artifacts/runtime/scripts/scan_reference_correction_runtime.py > artifacts/runtime/logs/scan_reference_correction.runtime.log 2>&1"},
			Env:           BaselineROSEnv(),
			SideEffect:    true,
			Status:        "fail_closed_external_nav_input_correction",
		},
		RuntimeServicePlan{
			HelperID:      "slam-hover",
			ServiceName:   "external_nav_source_selector",
			ContainerName: "navlab-external-nav-source-selector",
			ImageRef:      "images.runtime",
			Network:       "host",
			Command:       []string{"bash", "-lc", "source /opt/ros/${ROS_DISTRO:-humble}/setup.bash && source ${OFFICIAL_WS:-/opt/navlab_official_ws}/install/setup.bash && python3 artifacts/runtime/scripts/external_nav_source_selector_runtime.py > artifacts/runtime/logs/external_nav_source_selector.runtime.log 2>&1"},
			Env:           BaselineROSEnv(),
			SideEffect:    true,
			Status:        "fail_closed_external_nav_source_selector",
		},
		RuntimeServicePlan{
			HelperID:      "slam-hover",
			ServiceName:   "hover_mission",
			ContainerName: "navlab-hover-mission",
			ImageRef:      "images.runtime",
			Network:       "host",
			Command:       []string{"bash", "-lc", "source /opt/ros/${ROS_DISTRO:-humble}/setup.bash && source ${OFFICIAL_WS:-/opt/navlab_official_ws}/install/setup.bash && python3 artifacts/runtime/scripts/hover_mission_runtime.py > artifacts/runtime/logs/hover_mission.runtime.log 2>&1"},
			Env:           BaselineROSEnv(),
			SideEffect:    true,
			Status:        "planned_python_runtime",
		},
	)
	plan.ROSProbes = append(plan.ROSProbes, ROSProbePlan{
		HelperID:     "slam-hover",
		Name:         "slam_hover_probe",
		ScriptPath:   "slam_hover_probe.py",
		OutputPath:   "slam_hover_probe.json",
		Topics:       []string{spec.FCUPoseTopic, spec.SlamOdomTopic, scanCorrectionSpec.OutputOdomTopic, scanCorrectionSpec.StatusTopic, sourceSelectorSpec.OutputOdomTopic, sourceSelectorSpec.StatusTopic, spec.SlamStatusTopic, spec.ExternalNavStatusTopic, scanReferenceSpec.OdomTopic, scanReferenceSpec.StatusTopic, CartographerOdometryInputTopic, "/navlab/scan_reference_cartographer_odom/status", "/mavlink_external_nav/status", "/sim/x2/status", spec.HoverStatusTopic, "/navlab/landing/status"},
		RuntimeImage: "images.runtime",
		Status:       "ported_script_generation",
	})
	plan.RosbagRecords = append(plan.RosbagRecords, BuildRosbagRecordPlanWithRequired(
		"slam-hover",
		"hover_rosbag",
		"configs/rosbag/hover.yaml",
		durationSec,
		appendUniqueTopics(
			MatureWorldSLAMReviewTopics(),
			scanCorrectionSpec.OutputOdomTopic,
			scanCorrectionSpec.StatusTopic,
			CartographerOdometryInputTopic,
			CartographerTFTopic,
			"/navlab/scan_reference_cartographer_odom/status",
			DiagnosticGazeboModelOdometryTopic,
			DiagnosticGazeboTFTopic,
			DiagnosticGazeboTFStaticTopic,
		),
		appendUniqueTopics(HoverTaskRequiredTopics(spec), scanCorrectionSpec.OutputOdomTopic, scanCorrectionSpec.StatusTopic, CartographerOdometryInputTopic, "/navlab/scan_reference_cartographer_odom/status"),
	))
	plan.ResultGates = append(plan.ResultGates, ResultGatePlan{
		HelperID: "slam-hover",
		Name:     "slam_hover_acceptance",
		Inputs:   []string{"mission_summary.json", "slam_hover_probe.json", "rosbag_profile_summary.json"},
		Outputs:  []string{"hover blockers", "summary.json"},
		Status:   "ported_partial",
	})
}

func addSlamOnlyExecution(plan *ExecutionPlan, task config.TaskConfig, durationSec float64) {
	spec := DefaultSlamOnlySpec()
	plan.ROSProbes = removeROSProbes(plan.ROSProbes, "rangefinder_probe", "imu_probe", "frame_contract_probe")
	plan.GeneratedArtifacts = append(plan.GeneratedArtifacts,
		ArtifactPlan{HelperID: "slam-only", Kind: "slam_only_probe_script", Path: "slam_only_probe.py"},
	)
	plan.ROSProbes = append(plan.ROSProbes, ROSProbePlan{
		HelperID:     "slam-only",
		Name:         "slam_only_probe",
		ScriptPath:   "slam_only_probe.py",
		OutputPath:   "slam_only_probe.json",
		Topics:       []string{spec.ScanTopic, spec.IMUTopic, spec.SlamOdomTopic, spec.SlamStatusTopic},
		RuntimeImage: "images.runtime",
		Status:       "ported_script_generation",
	})
	plan.RosbagRecords = append(plan.RosbagRecords, BuildRosbagRecordPlanWithRequired(
		"slam-only",
		"slam_only_rosbag",
		"configs/rosbag/hover_slam_only.yaml",
		durationSec,
		spec.RosbagTopics(),
		spec.RequiredTopics(),
	))
	plan.ResultGates = append(plan.ResultGates, ResultGatePlan{
		HelperID: "slam-only",
		Name:     "slam_only_acceptance",
		Inputs:   []string{"slam_only_probe.json", "rosbag_profile_summary.json", "slam_backend.runtime.log"},
		Outputs:  []string{"slam-only blockers", "summary.json"},
		Status:   "ported_partial",
	})
	_ = task
}

func removeROSProbes(probes []ROSProbePlan, names ...string) []ROSProbePlan {
	remove := map[string]bool{}
	for _, name := range names {
		remove[name] = true
	}
	out := probes[:0]
	for _, probe := range probes {
		if !remove[probe.Name] {
			out = append(out, probe)
		}
	}
	return out
}

func addScanStabilizationExecution(plan *ExecutionPlan, task config.TaskConfig, durationSec float64) {
	spec := DefaultScanStabilizationSpec()
	plan.GeneratedArtifacts = append(plan.GeneratedArtifacts,
		ArtifactPlan{HelperID: "scan-stabilization", Kind: "scan_stabilization_sensor_runtime_toml", Path: "scan_stabilization_gazebo_sensor_runtime.toml"},
		ArtifactPlan{HelperID: "scan-stabilization", Kind: "scan_stabilization_runtime_toml", Path: "scan_stabilization_runtime.toml"},
	)
	plan.ROSProbes = append(plan.ROSProbes, ROSProbePlan{
		HelperID:     "scan-stabilization",
		Name:         "stabilization_status_probe",
		ScriptPath:   "stabilization_status_probe.py",
		OutputPath:   "stabilization_status_latest.json",
		Topics:       []string{spec.StatusTopic, spec.InputScanTopic, spec.OutputScanTopic, spec.AttitudeSourceTopic},
		RuntimeImage: "images.runtime",
		Status:       "ported_script_generation",
	})
	plan.RosbagRecords = append(plan.RosbagRecords, BuildRosbagRecordPlan("scan-stabilization", "scan_stabilization_rosbag", "configs/rosbag/scan_stabilization.yaml", durationSec, []string{spec.InputScanTopic, spec.OutputScanTopic, spec.StatusTopic}))
	plan.ResultGates = append(plan.ResultGates, ResultGatePlan{
		HelperID: "scan-stabilization",
		Name:     "scan_stabilization_gate",
		Inputs:   []string{"stabilization_status_latest.json", "rosbag_profile_summary.json"},
		Outputs:  []string{"scan stabilization blockers", "summary.json"},
		Status:   "ported_partial",
	})
	_ = task
}

func addExplorationWorkflowExecution(plan *ExecutionPlan, task config.TaskConfig, durationSec float64, simulationProfile string) {
	spec := DefaultExplorationWorkflowSpec()
	if value, ok := floatSectionValue(task.Sections, "exploration_gate", "exploration_window_sec"); ok {
		spec.ExplorationWindowSec = value
	}
	if value, ok := floatSectionValue(task.Sections, "exploration_gate", "motion_speed_mps"); ok {
		spec.MotionSpeedMPS = value
	}
	plan.GeneratedArtifacts = append(plan.GeneratedArtifacts,
		ArtifactPlan{HelperID: "exploration-workflow", Kind: "exploration_runtime_toml", Path: "exploration_runtime.toml"},
		ArtifactPlan{HelperID: "exploration-workflow", Kind: "exploration_runtime_script", Path: "exploration_workflow_runtime.py"},
		ArtifactPlan{HelperID: "exploration-workflow", Kind: "exploration_probe_script", Path: "exploration_probe.py"},
	)
	plan.RuntimeServices = append(plan.RuntimeServices, RuntimeServicePlan{
		HelperID:      "exploration-workflow",
		ServiceName:   "exploration_workflow",
		ContainerName: "navlab-exploration-workflow",
		ImageRef:      "images.runtime",
		Network:       "host",
		Command:       []string{"bash", "-lc", "source /opt/ros/${ROS_DISTRO:-humble}/setup.bash && python3 artifacts/runtime/scripts/exploration_workflow_runtime.py > artifacts/runtime/logs/exploration_workflow.runtime.log 2>&1"},
		Env:           BaselineROSEnv(),
		SideEffect:    true,
		Status:        "planned_runtime",
	})
	plan.ROSProbes = append(plan.ROSProbes, ROSProbePlan{
		HelperID:     "exploration-workflow",
		Name:         "exploration_probe",
		ScriptPath:   "exploration_probe.py",
		OutputPath:   "exploration_probe.json",
		Topics:       []string{spec.ControllerStatusTopic, spec.SetpointOutputTopic, spec.ExplorationStatusTopic, spec.SlamOdomTopic, "/navlab/landing/status"},
		RuntimeImage: "images.runtime",
		Status:       "ported_script_generation",
	})
	plan.RosbagRecords = append(plan.RosbagRecords, BuildRosbagRecordPlanWithRequired(
		"exploration-workflow",
		"exploration_rosbag",
		"configs/rosbag/exploration.yaml",
		durationSec,
		ExplorationTaskReviewTopics(spec),
		ExplorationTaskRequiredTopics(spec),
	))
	if simulationProfile == "realistic" {
		plan.GeneratedArtifacts = append(plan.GeneratedArtifacts, ArtifactPlan{HelperID: "exploration-workflow", Kind: "airframe_disturbance_runtime", Path: "exploration_airframe_disturbance.toml"})
	}
	plan.ResultGates = append(plan.ResultGates, ResultGatePlan{
		HelperID: "exploration-workflow",
		Name:     "exploration_acceptance",
		Inputs:   []string{"exploration_probe.json", "controller_summary.json", "landing acceptance summary"},
		Outputs:  []string{"exploration blockers", "summary.json"},
		Status:   "ported_partial",
	})
}

func addNav2NavigationWorkflowExecution(plan *ExecutionPlan, task config.TaskConfig, durationSec float64) {
	spec := DefaultNav2NavigationSpec()
	if value, ok := floatSectionValue(task.Sections, "navigation_mission", "navigation_window_sec"); ok {
		spec.NavigationWindowSec = value
	}
	if value, ok := floatSectionValue(task.Sections, "navigation_adapter", "max_xy_speed_mps"); ok {
		spec.MaxXYSpeedMPS = value
	}
	plan.GeneratedArtifacts = append(plan.GeneratedArtifacts,
		ArtifactPlan{HelperID: "nav2-navigation-workflow", Kind: "nav2_params_yaml", Path: "nav2_params.yaml"},
		ArtifactPlan{HelperID: "nav2-navigation-workflow", Kind: "navigation_adapter_runtime_toml", Path: "navigation_adapter_runtime.toml"},
		ArtifactPlan{HelperID: "nav2-navigation-workflow", Kind: "navigation_adapter_runtime_script", Path: "navigation_adapter_runtime.py"},
		ArtifactPlan{HelperID: "nav2-navigation-workflow", Kind: "navigation_mission_runtime_script", Path: "navigation_mission_runtime.py"},
		ArtifactPlan{HelperID: "nav2-navigation-workflow", Kind: "nav2_lifecycle_probe_script", Path: "nav2_lifecycle_probe.py"},
		ArtifactPlan{HelperID: "nav2-navigation-workflow", Kind: "costmap_health_probe_script", Path: "costmap_health_probe.py"},
		ArtifactPlan{HelperID: "nav2-navigation-workflow", Kind: "navigation_status_probe_script", Path: "navigation_status_probe.py"},
	)
	plan.RuntimeServices = append(plan.RuntimeServices, RuntimeServicePlan{
		HelperID:      "nav2-navigation-workflow",
		ServiceName:   "nav2_navigation",
		ContainerName: "navlab-nav2-navigation",
		ImageRef:      "images.runtime",
		Network:       "host",
		Command:       []string{"bash", "-lc", "source /opt/ros/${ROS_DISTRO:-humble}/setup.bash && ros2 launch nav2_bringup navigation_launch.py use_sim_time:=true params_file:=artifacts/runtime/config/nav2_params.yaml"},
		Env:           BaselineROSEnv(),
		SideEffect:    true,
		Status:        "planned_runtime",
	})
	plan.RuntimeServices = append(plan.RuntimeServices, RuntimeServicePlan{
		HelperID:      "nav2-navigation-workflow",
		ServiceName:   "navigation_adapter",
		ContainerName: "navlab-navigation-adapter",
		ImageRef:      "images.runtime",
		Network:       "host",
		Command:       []string{"bash", "-lc", "source /opt/ros/${ROS_DISTRO:-humble}/setup.bash && python3 artifacts/runtime/scripts/navigation_adapter_runtime.py > artifacts/runtime/logs/navigation_adapter.runtime.log 2>&1"},
		Env:           BaselineROSEnv(),
		SideEffect:    true,
		Status:        "planned_runtime",
	})
	plan.RuntimeServices = append(plan.RuntimeServices, RuntimeServicePlan{
		HelperID:      "nav2-navigation-workflow",
		ServiceName:   "navigation_mission",
		ContainerName: "navlab-navigation-mission",
		ImageRef:      "images.runtime",
		Network:       "host",
		Command:       []string{"bash", "-lc", "source /opt/ros/${ROS_DISTRO:-humble}/setup.bash && python3 artifacts/runtime/scripts/navigation_mission_runtime.py > artifacts/runtime/logs/navigation_mission.runtime.log 2>&1"},
		Env:           BaselineROSEnv(),
		SideEffect:    true,
		Status:        "planned_runtime",
	})
	plan.ROSProbes = append(plan.ROSProbes,
		ROSProbePlan{HelperID: "nav2-navigation-workflow", Name: "nav2_lifecycle_probe", ScriptPath: "nav2_lifecycle_probe.py", OutputPath: "nav2_lifecycle_probe.json", Topics: []string{spec.MapTopic, spec.SlamOdomTopic}, RuntimeImage: "images.runtime", Status: "ported_script_generation"},
		ROSProbePlan{HelperID: "nav2-navigation-workflow", Name: "costmap_health_probe", ScriptPath: "costmap_health_probe.py", OutputPath: "costmap_health_probe.json", Topics: []string{spec.CostmapHealthTopic, spec.GlobalCostmapTopic, spec.LocalCostmapTopic}, RuntimeImage: "images.runtime", Status: "ported_script_generation"},
		ROSProbePlan{HelperID: "nav2-navigation-workflow", Name: "navigation_status_probe", ScriptPath: "navigation_status_probe.py", OutputPath: "navigation_status_probe.json", Topics: []string{spec.NavigationStatusTopic, spec.AdapterStatusTopic, spec.ControllerStatusTopic, spec.LandingStatusTopic}, RuntimeImage: "images.runtime", Status: "ported_script_generation"},
	)
	plan.RosbagRecords = append(plan.RosbagRecords, BuildRosbagRecordPlanWithRequired(
		"nav2-navigation-workflow",
		"navigation_rosbag",
		"configs/rosbag/navigation.yaml",
		durationSec,
		NavigationTaskReviewTopics(spec),
		NavigationTaskRequiredTopics(spec),
	))
	plan.ResultGates = append(plan.ResultGates, ResultGatePlan{
		HelperID: "nav2-navigation-workflow",
		Name:     "navigation_acceptance",
		Inputs:   []string{"navigation_status_probe.json", "costmap_health_probe.json", "controller_summary.json", "landing acceptance summary"},
		Outputs:  []string{"navigation blockers", "summary.json"},
		Status:   "ported_partial",
	})
}

func addScanRobustnessWorkflowExecution(plan *ExecutionPlan, task config.TaskConfig, durationSec float64) {
	spec := DefaultScanRobustnessWorkflowSpec()
	plan.GeneratedArtifacts = append(plan.GeneratedArtifacts,
		ArtifactPlan{HelperID: "scan-robustness-workflow", Kind: "scan_robustness_runtime_toml", Path: "scan_robustness_runtime.toml"},
		ArtifactPlan{HelperID: "scan-robustness-workflow", Kind: "scan_robustness_sensor_runtime_toml", Path: "scan_robustness_gazebo_sensor_runtime.toml"},
		ArtifactPlan{HelperID: "scan-robustness-workflow", Kind: "scan_robustness_bridge_override", Path: "scan_robustness_bridge_override.yaml"},
		ArtifactPlan{HelperID: "scan-robustness-workflow", Kind: "airframe_disturbance_probe_script", Path: "airframe_disturbance_probe.py"},
	)
	plan.ROSProbes = append(plan.ROSProbes, ROSProbePlan{
		HelperID:     "scan-robustness-workflow",
		Name:         "airframe_disturbance_probe",
		ScriptPath:   "airframe_disturbance_probe.py",
		OutputPath:   "airframe_disturbance_probe.json",
		Topics:       []string{spec.DisturbanceStatusTopic},
		RuntimeImage: "images.runtime",
		Status:       "ported_script_generation",
	})
	plan.RosbagRecords = append(plan.RosbagRecords, BuildRosbagRecordPlan("scan-robustness-workflow", "scan_robustness_rosbag", "configs/rosbag/scan_robustness.yaml", durationSec, []string{spec.FCUStatusTopic, spec.StabilizedScanTopic, spec.DisturbanceStatusTopic}))
	plan.ResultGates = append(plan.ResultGates, ResultGatePlan{
		HelperID: "scan-robustness-workflow",
		Name:     "airframe_disturbance_gate",
		Inputs:   []string{"airframe_disturbance_probe.json", "profile_sweep_summary.json", "rosbag_profile_summary.json", "summary.json"},
		Outputs:  []string{"airframe disturbance blockers", "scan robustness summary"},
		Status:   "ported_partial",
	})
	_ = task
}

func BuildRosbagRecordPlan(helperID string, name string, profilePath string, durationSec float64, topics []string) RosbagRecordPlan {
	return BuildRosbagRecordPlanWithRequired(helperID, name, profilePath, durationSec, topics, topics)
}

func BuildRosbagRecordPlanWithRequired(helperID string, name string, profilePath string, durationSec float64, topics []string, requiredTopics []string) RosbagRecordPlan {
	quotedTopics := make([]string, 0, len(topics))
	for _, topic := range topics {
		quotedTopics = append(quotedTopics, shellQuote(topic))
	}
	outputDir := "rosbag/" + name
	return RosbagRecordPlan{
		HelperID:       helperID,
		Name:           name,
		ProfilePath:    profilePath,
		OutputDir:      outputDir,
		Topics:         append([]string(nil), topics...),
		RequiredTopics: append([]string(nil), requiredTopics...),
		Command:        fmt.Sprintf("ros2 bag record -s mcap -o %s --topics %s # runtime_owned_stop=SIGINT duration_sec=%.1f", outputDir, strings.Join(quotedTopics, " "), durationSec),
		Status:         "ported_command_planning",
	}
}

func sectionNames(sections map[string]any) []string {
	names := make([]string, 0, len(sections))
	for name := range sections {
		names = append(names, name)
	}
	sort.Strings(names)
	return names
}

func floatSectionValue(sections map[string]any, section string, key string) (float64, bool) {
	rawSection, ok := sections[section]
	if !ok {
		return 0, false
	}
	values, ok := rawSection.(map[string]interface{})
	if !ok {
		return 0, false
	}
	switch value := values[key].(type) {
	case float64:
		return value, true
	case int:
		return float64(value), true
	case int64:
		return float64(value), true
	default:
		return 0, false
	}
}
