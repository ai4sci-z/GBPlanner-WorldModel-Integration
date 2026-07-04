package tasks

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
	"navlab/orchestration-sim/internal/config"
	simruntime "navlab/orchestration-sim/internal/runtime"
	"navlab/orchestration-sim/internal/tasks/helpers"
)

func TestBuildRuntimeSpecsFromExecutionPlan(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	t.Setenv("NAVLAB_SIM_IMAGE_TAG", "")
	t.Setenv("NAVLAB_SIM_RUNTIME_IMAGE_TAG", "")
	project := config.ProjectConfig{
		Orchestration: config.OrchestrationConfig{
			Runtime: config.OrchestrationRuntimeConfig{
				Docker: config.DockerRuntimeConfig{WorkspaceContainerPath: "/workspace"},
			},
		},
		Paths:       config.PathConfig{WorkspaceRoot: "."},
		RosDomainID: "85",
		Navlab: config.NavlabConfig{
			Images: config.ImageCatalog{TagPolicy: "distro-latest"},
		},
		Images: map[string]config.Image{
			"gazebo_sensor":     {Repository: "navlab/gazebo-sensor"},
			"slam":              {Repository: "navlab/slam-cartographer"},
			"mavlink_router":    {Repository: "navlab/mavlink-router"},
			"official_baseline": {Repository: "navlab/official-baseline"},
		},
	}
	plan := helpers.ExecutionPlan{
		TaskID:      "hover",
		DurationSec: 90,
		RuntimeServices: []helpers.RuntimeServicePlan{
			{
				HelperID:      "sensors",
				ServiceName:   "gazebo_sensor",
				ContainerName: "navlab-official-maze-x2-sensor",
				ImageRef:      "images.gazebo_sensor",
				Network:       "host",
				Command:       []string{"bash", "-lc", "run"},
				Env:           map[string]string{"ROS_DOMAIN_ID": "from config.toml"},
			},
		},
		ROSProbes: []helpers.ROSProbePlan{
			{
				HelperID:     "sensors",
				Name:         "rangefinder_probe",
				ScriptPath:   "probes/rangefinder_probe.py",
				OutputPath:   "probes/rangefinder_probe.txt",
				RuntimeImage: "images.runtime",
				Topics:       []string{"/navlab/rangefinder/range"},
			},
		},
		RosbagRecords: []helpers.RosbagRecordPlan{
			{
				HelperID:  "slam-hover",
				Name:      "hover_rosbag",
				OutputDir: "rosbag/hover_rosbag",
				Topics:    []string{"/tf", "/scan"},
			},
		},
	}

	bundle, err := BuildRuntimeSpecs(project, plan, t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	if len(bundle.Services) != 5 {
		t.Fatalf("services = %#v", bundle.Services)
	}
	router := serviceByName(bundle.Services, "mavlink_router")
	if router == nil || router.Image != "navlab/mavlink-router:humble-latest" {
		t.Fatalf("mavlink router service = %#v", bundle.Services)
	}
	if router.Env["SESSION_ID"] != "navlab_companion_sitl_gazebo" || router.Env["ROUTER_TCP_PORT"] != "0" {
		t.Fatalf("router env = %#v", router.Env)
	}
	official := serviceByName(bundle.Services, "official_baseline")
	if official == nil || official.Image != "navlab/official-baseline:humble-latest" {
		t.Fatalf("official baseline service = %#v", bundle.Services)
	}
	officialCommand := strings.Join(official.Command, " ")
	if !strings.Contains(officialCommand, "python3 -m navlab.sim.gazebo_sensor.benewake_tfmini_serial") {
		t.Fatalf("official baseline command missing NavLab Benewake serial emulator: %s", officialCommand)
	}
	if !strings.Contains(officialCommand, "serial7:=uart:/tmp/navlab_benewake_tfmini:115200") {
		t.Fatalf("official baseline command missing Benewake serial rangefinder backend: %s", officialCommand)
	}
	if sensor := serviceByName(bundle.Services, "gazebo_sensor"); sensor == nil || !sensor.Restartable {
		t.Fatalf("gazebo_sensor should be restartable startup leaf, got %#v", sensor)
	}
	if height := serviceByName(bundle.Services, "height_estimator"); height == nil || !height.Restartable {
		t.Fatalf("height_estimator should be restartable startup leaf, got %#v", height)
	}
	if bundle.StartupReadinessProbe == nil ||
		bundle.StartupReadinessProbe.Name != "startup_readiness_probe" ||
		!strings.Contains(bundle.StartupReadinessProbe.OutputPath, "startup_readiness_probe.json") {
		t.Fatalf("startup readiness probe = %#v", bundle.StartupReadinessProbe)
	}
	sensor := serviceByName(bundle.Services, "gazebo_sensor")
	if sensor == nil || sensor.Image != "navlab/gazebo-sensor:humble-latest" {
		t.Fatalf("gazebo sensor service = %#v", bundle.Services)
	}
	if sensor.Env["ROS_DOMAIN_ID"] != "85" {
		t.Fatalf("service env = %#v", sensor.Env)
	}
	externalNav := serviceByName(bundle.Services, "mavlink_external_nav")
	if externalNav == nil || externalNav.Image != "navlab/official-baseline:humble-latest" {
		t.Fatalf("mavlink external nav service = %#v", bundle.Services)
	}
	heightEstimator := serviceByName(bundle.Services, "height_estimator")
	if heightEstimator == nil || heightEstimator.Image != "navlab/official-baseline:humble-latest" {
		t.Fatalf("height estimator service = %#v", bundle.Services)
	}
	heightEstimatorCommand := strings.Join(heightEstimator.Command, " ")
	for _, expected := range []string{
		"navlab.real.companion.nodes.height_estimator",
		"--range-topic /rangefinder/down/range",
		"--height-topic /height/estimate",
		"--status-topic /height/status",
		"--max-vertical-speed-mps 0.5",
		"--max-vertical-velocity-output-mps 0.25",
		"--velocity-smoothing-alpha 0.25",
		"--max-filter-dt-sec 0.1",
	} {
		if !strings.Contains(heightEstimatorCommand, expected) {
			t.Fatalf("height estimator command = %q, want %q", heightEstimatorCommand, expected)
		}
	}
	externalNavCommand := strings.Join(externalNav.Command, " ")
	for _, expected := range []string{
		"navlab.real.companion.nodes.external_nav",
		"--endpoint udpin:0.0.0.0:14553",
		"--odom-topic /external_nav/odom",
		"--status-topic /mavlink_external_nav/status",
		"--local-position-pose-topic /navlab/fcu/local_position_pose",
		"--align-yaw-to-fcu",
		"--max-local-position-age-ms 1000",
		"--max-horizontal-speed-mps 0.25",
		"--max-yaw-rate-radps 0.6",
	} {
		if !strings.Contains(externalNavCommand, expected) {
			t.Fatalf("external nav command = %q, want %q", externalNavCommand, expected)
		}
	}
	if official.Env["ROS_DISTRO"] != "humble" || sensor.Env["ROS_DISTRO"] != "" {
		t.Fatalf("runtime distro env official=%#v sensor=%#v", official.Env, sensor.Env)
	}
	if len(bundle.Probes) != 1 || bundle.Probes[0].Image != "navlab/official-baseline:humble-latest" {
		t.Fatalf("probes = %#v", bundle.Probes)
	}
	if bundle.Probes[0].Env["ROS_DISTRO"] != "humble" || bundle.Rosbags[0].Env["ROS_DISTRO"] != "humble" {
		t.Fatalf("probe/rosbag env = %#v %#v", bundle.Probes[0].Env, bundle.Rosbags[0].Env)
	}
	if !strings.Contains(bundle.Probes[0].Env["CYCLONEDDS_URI"], "MaxAutoParticipantIndex") ||
		!strings.Contains(bundle.Rosbags[0].Env["CYCLONEDDS_URI"], "MaxAutoParticipantIndex") {
		t.Fatalf("probe/rosbag env missing CycloneDDS participant cap override = %#v %#v", bundle.Probes[0].Env, bundle.Rosbags[0].Env)
	}
	if len(bundle.Rosbags) != 1 {
		t.Fatalf("rosbags = %#v", bundle.Rosbags)
	}
	if filepath.Base(bundle.Rosbags[0].TopicsProfile) != "hover_rosbag.txt" {
		t.Fatalf("topics profile = %s", bundle.Rosbags[0].TopicsProfile)
	}
}

func TestProbeTimeoutsAllowExplorationReadinessWindow(t *testing.T) {
	if got := probeTimeoutSec("exploration_probe", 90); got < 90 {
		t.Fatalf("exploration_probe timeout = %v, want at least 90", got)
	}
	if got := probeTimeoutSec("slam_hover_probe", 90); got < 90 {
		t.Fatalf("slam_hover_probe timeout = %v, want at least 90", got)
	}
	if got := probeTimeoutSec("slam_hover_probe", 90); got != 120 {
		t.Fatalf("slam_hover_probe timeout = %v, want 120", got)
	}
	if got := probeTimeoutSec("rangefinder_probe", 90); got != 30 {
		t.Fatalf("rangefinder_probe timeout = %v, want 30", got)
	}
}

func TestBuildRuntimeSpecsMakesSlamHoverProbeDiagnosticOnly(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	t.Setenv("NAVLAB_SIM_IMAGE_TAG", "")
	t.Setenv("NAVLAB_SIM_RUNTIME_IMAGE_TAG", "")
	project := config.ProjectConfig{
		Orchestration: config.OrchestrationConfig{
			Runtime: config.OrchestrationRuntimeConfig{
				Docker: config.DockerRuntimeConfig{WorkspaceContainerPath: "/workspace"},
			},
		},
		Paths:       config.PathConfig{WorkspaceRoot: "."},
		RosDomainID: "85",
		Navlab: config.NavlabConfig{
			Images: config.ImageCatalog{TagPolicy: "distro-latest"},
		},
		Images: map[string]config.Image{
			"mavlink_router":    {Repository: "navlab/mavlink-router"},
			"official_baseline": {Repository: "navlab/official-baseline"},
		},
	}
	plan := helpers.ExecutionPlan{
		TaskID:      "hover",
		DurationSec: 90,
		ROSProbes: []helpers.ROSProbePlan{
			{
				HelperID:     "slam-hover",
				Name:         "slam_hover_probe",
				ScriptPath:   "slam_hover_probe.py",
				OutputPath:   "slam_hover_probe.json",
				RuntimeImage: "images.runtime",
			},
			{
				HelperID:     "frame-contract",
				Name:         "frame_contract_probe",
				ScriptPath:   "frame_contract_probe.py",
				OutputPath:   "frame_contract_probe.json",
				RuntimeImage: "images.runtime",
			},
		},
	}

	bundle, err := BuildRuntimeSpecs(project, plan, t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	hoverProbe := probeByName(bundle.Probes, "slam_hover_probe")
	if hoverProbe == nil || hoverProbe.Required {
		t.Fatalf("slam_hover_probe spec = %#v, want diagnostic-only required=false", hoverProbe)
	}
	frameProbe := probeByName(bundle.Probes, "frame_contract_probe")
	if frameProbe == nil || !frameProbe.Required {
		t.Fatalf("frame_contract_probe spec = %#v, want required=true", frameProbe)
	}
}

func TestBuildRuntimeSpecsUsesRuntimeRosDistroOverride(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "jazzy")
	t.Setenv("NAVLAB_SIM_IMAGE_TAG", "")
	t.Setenv("NAVLAB_SIM_RUNTIME_IMAGE_TAG", "")
	project := config.ProjectConfig{
		Orchestration: config.OrchestrationConfig{
			Runtime: config.OrchestrationRuntimeConfig{
				Docker: config.DockerRuntimeConfig{WorkspaceContainerPath: "/workspace"},
			},
		},
		Paths:       config.PathConfig{WorkspaceRoot: "."},
		RosDomainID: "85",
		Navlab: config.NavlabConfig{
			Images: config.ImageCatalog{TagPolicy: "distro-latest", Distro: "humble"},
		},
		Images: map[string]config.Image{
			"mavlink_router":    {Repository: "navlab/mavlink-router"},
			"official_baseline": {Repository: "navlab/official-baseline"},
		},
	}
	bundle, err := BuildRuntimeSpecs(project, helpers.ExecutionPlan{TaskID: "navigation"}, t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	official := serviceByName(bundle.Services, "official_baseline")
	if official == nil {
		t.Fatalf("services = %#v", bundle.Services)
	}
	if official.Env["ROS_DISTRO"] != "jazzy" {
		t.Fatalf("official env = %#v", official.Env)
	}
	if !strings.Contains(strings.Join(official.Command, " "), "/opt/ros/${ROS_DISTRO:-jazzy}/setup.bash") {
		t.Fatalf("official command = %#v", official.Command)
	}
}

func TestBuildRuntimeSpecsMountsOfficialModelAndParamOverlays(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "jazzy")
	t.Setenv("NAVLAB_SIM_IMAGE_TAG", "")
	t.Setenv("NAVLAB_SIM_RUNTIME_IMAGE_TAG", "")
	workspace := t.TempDir()
	artifactDir := filepath.Join(workspace, "artifacts", "sim", "hover", "run-1")
	if err := os.MkdirAll(artifactDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := artifactlayout.Ensure(artifactDir); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(artifactlayout.RuntimeConfig(artifactDir, "model_overlay.sdf"), []byte("<sdf/>"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(artifactlayout.RuntimeConfig(artifactDir, "gazebo-iris-rangefinder.parm"), []byte("RNGFND1_TYPE 10\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	project := config.ProjectConfig{
		Orchestration: config.OrchestrationConfig{
			Runtime: config.OrchestrationRuntimeConfig{
				Docker: config.DockerRuntimeConfig{WorkspaceContainerPath: "/workspace"},
			},
		},
		Paths:       config.PathConfig{WorkspaceRoot: workspace},
		RosDomainID: "85",
		Navlab: config.NavlabConfig{
			Images: config.ImageCatalog{TagPolicy: "distro-latest", Distro: "jazzy"},
		},
		Images: map[string]config.Image{
			"mavlink_router":    {Repository: "navlab/mavlink-router"},
			"official_baseline": {Repository: "navlab/official-baseline"},
		},
	}

	bundle, err := BuildRuntimeSpecs(project, helpers.ExecutionPlan{TaskID: "hover"}, artifactDir)
	if err != nil {
		t.Fatal(err)
	}
	official := serviceByName(bundle.Services, "official_baseline")
	if official == nil {
		t.Fatalf("services = %#v", bundle.Services)
	}
	assertVolumeTarget(t, official.Volumes, helpers.OfficialIrisWithLidarModel)
	assertVolumeTarget(t, official.Volumes, helpers.OfficialGazeboIrisParams)
	command := strings.Join(official.Command, " ")
	for _, expected := range []string{
		"sitl/scripts",
		"docker/profiles/ahrs-set-origin.lua",
		"sitl/scripts/ahrs-set-origin.lua",
	} {
		if !strings.Contains(command, expected) {
			t.Fatalf("official command = %q, want %q", command, expected)
		}
	}
}

func TestBuildRuntimeSpecsMountsHoverCartographerConfigIntoSlamBackend(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "jazzy")
	t.Setenv("NAVLAB_SIM_IMAGE_TAG", "")
	t.Setenv("NAVLAB_SIM_RUNTIME_IMAGE_TAG", "")
	workspace := t.TempDir()
	artifactDir := filepath.Join(workspace, "artifacts", "sim", "hover", "run-1")
	if err := os.MkdirAll(artifactDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := artifactlayout.Ensure(artifactDir); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(artifactlayout.RuntimeConfig(artifactDir, helpers.HoverCartographerConfigBasename), []byte("return options\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	project := config.ProjectConfig{
		Orchestration: config.OrchestrationConfig{
			Runtime: config.OrchestrationRuntimeConfig{
				Docker: config.DockerRuntimeConfig{WorkspaceContainerPath: "/workspace"},
			},
		},
		Paths:       config.PathConfig{WorkspaceRoot: workspace},
		RosDomainID: "85",
		Navlab: config.NavlabConfig{
			Images: config.ImageCatalog{TagPolicy: "distro-latest", Distro: "jazzy"},
		},
		Images: map[string]config.Image{
			"mavlink_router":    {Repository: "navlab/mavlink-router"},
			"official_baseline": {Repository: "navlab/official-baseline"},
			"slam":              {Repository: "navlab/slam-cartographer"},
		},
	}
	plan := helpers.ExecutionPlan{
		TaskID: "hover",
		RuntimeServices: []helpers.RuntimeServicePlan{
			{
				HelperID:      "slam",
				ServiceName:   "slam_backend",
				ContainerName: "navlab-slam-backend",
				ImageRef:      "images.slam",
				Command:       []string{"bash", "-lc", "run"},
			},
		},
	}

	bundle, err := BuildRuntimeSpecs(project, plan, artifactDir)
	if err != nil {
		t.Fatal(err)
	}
	slam := serviceByName(bundle.Services, "slam_backend")
	if slam == nil {
		t.Fatalf("services = %#v", bundle.Services)
	}
	assertVolumeTarget(t, slam.Volumes, helpers.OfficialCartographerConfigDir+"/"+helpers.HoverCartographerConfigBasename)
}

func TestBuildRuntimeSpecsHoverSlamOnlyDoesNotStartExternalNavInjection(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "jazzy")
	workspace := t.TempDir()
	artifactDir := filepath.Join(workspace, "artifacts", "sim", "hover-slam-only", "run-1")
	if err := os.MkdirAll(artifactDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := artifactlayout.Ensure(artifactDir); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(artifactlayout.RuntimeConfig(artifactDir, helpers.HoverCartographerConfigBasename), []byte("return options\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	project := config.ProjectConfig{
		Orchestration: config.OrchestrationConfig{
			Runtime: config.OrchestrationRuntimeConfig{
				Docker: config.DockerRuntimeConfig{WorkspaceContainerPath: "/workspace"},
			},
		},
		Paths:       config.PathConfig{WorkspaceRoot: workspace},
		RosDomainID: "85",
		Navlab: config.NavlabConfig{
			Images: config.ImageCatalog{TagPolicy: "distro-latest", Distro: "jazzy"},
		},
		Images: map[string]config.Image{
			"mavlink_router":    {Repository: "navlab/mavlink-router"},
			"official_baseline": {Repository: "navlab/official-baseline"},
			"slam":              {Repository: "navlab/slam-cartographer"},
		},
	}
	plan := helpers.ExecutionPlan{
		TaskID: "hover-slam-only",
		RuntimeServices: []helpers.RuntimeServicePlan{
			{
				HelperID:      "slam",
				ServiceName:   "slam_backend",
				ContainerName: "navlab-slam-backend",
				ImageRef:      "images.slam",
				Command:       []string{"bash", "-lc", "run"},
			},
		},
	}

	bundle, err := BuildRuntimeSpecs(project, plan, artifactDir)
	if err != nil {
		t.Fatal(err)
	}
	if serviceByName(bundle.Services, "official_baseline") == nil {
		t.Fatalf("services = %#v", bundle.Services)
	}
	for _, name := range []string{"mavlink_external_nav", "height_estimator", "hover_mission", "fcu_controller", "official_maze_overlay"} {
		if serviceByName(bundle.Services, name) != nil {
			t.Fatalf("hover-slam-only unexpectedly starts %s: %#v", name, bundle.Services)
		}
	}
}

func TestBuildRuntimeSpecsStartsOfficialMazeOverlayPublisherWhenGenerated(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "jazzy")
	workspace := t.TempDir()
	artifactDir := filepath.Join(workspace, "artifacts", "sim", "hover", "run-1")
	if err := os.MkdirAll(artifactDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := artifactlayout.Ensure(artifactDir); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(artifactlayout.RuntimeScript(artifactDir, "official_maze_overlay_runtime.py"), []byte("#!/usr/bin/env python3\n"), 0o755); err != nil {
		t.Fatal(err)
	}
	project := config.ProjectConfig{
		Orchestration: config.OrchestrationConfig{
			Runtime: config.OrchestrationRuntimeConfig{
				Docker: config.DockerRuntimeConfig{WorkspaceContainerPath: "/workspace"},
			},
		},
		Paths:       config.PathConfig{WorkspaceRoot: workspace},
		RosDomainID: "85",
		Navlab: config.NavlabConfig{
			Images: config.ImageCatalog{TagPolicy: "distro-latest", Distro: "jazzy"},
		},
		Images: map[string]config.Image{
			"mavlink_router":    {Repository: "navlab/mavlink-router"},
			"official_baseline": {Repository: "navlab/official-baseline"},
		},
	}

	bundle, err := BuildRuntimeSpecs(project, helpers.ExecutionPlan{TaskID: "hover"}, artifactDir)
	if err != nil {
		t.Fatal(err)
	}
	overlay := serviceByName(bundle.Services, "official_maze_overlay")
	if overlay == nil {
		t.Fatalf("services = %#v", bundle.Services)
	}
	command := strings.Join(overlay.Command, " ")
	if !strings.Contains(command, "official_maze_overlay_runtime.py") || overlay.ServiceRole != "foxglove-official-maze-overlay" {
		t.Fatalf("overlay service = %#v", overlay)
	}
	if overlay.Env["ROS_DISTRO"] != "jazzy" {
		t.Fatalf("overlay env = %#v", overlay.Env)
	}
}

func TestBuildRuntimeSpecsUsesRuntimeImageTagOverride(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	t.Setenv("NAVLAB_SIM_IMAGE_TAG", "humble-latest")
	t.Setenv("NAVLAB_SIM_RUNTIME_IMAGE_TAG", "")
	project := config.ProjectConfig{
		Orchestration: config.OrchestrationConfig{
			Runtime: config.OrchestrationRuntimeConfig{
				Docker: config.DockerRuntimeConfig{WorkspaceContainerPath: "/workspace"},
			},
		},
		Paths:       config.PathConfig{WorkspaceRoot: "."},
		RosDomainID: "85",
		Navlab: config.NavlabConfig{
			Images: config.ImageCatalog{TagPolicy: "distro-git-commit"},
		},
		Images: map[string]config.Image{
			"mavlink_router":    {Repository: "navlab/mavlink-router"},
			"official_baseline": {Repository: "navlab/official-baseline"},
		},
	}
	bundle, err := BuildRuntimeSpecs(project, helpers.ExecutionPlan{TaskID: "navigation"}, t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	official := serviceByName(bundle.Services, "official_baseline")
	if official == nil || official.Image != "navlab/official-baseline:humble-latest" {
		t.Fatalf("official baseline service = %#v", bundle.Services)
	}
}

func TestBuildRuntimeSpecsRejectsDistroPrefixedImageTagMismatch(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "jazzy")
	t.Setenv("NAVLAB_SIM_IMAGE_TAG", "humble-latest")
	t.Setenv("NAVLAB_SIM_RUNTIME_IMAGE_TAG", "")
	project := config.ProjectConfig{
		Orchestration: config.OrchestrationConfig{
			Runtime: config.OrchestrationRuntimeConfig{
				Docker: config.DockerRuntimeConfig{WorkspaceContainerPath: "/workspace"},
			},
		},
		Paths:       config.PathConfig{WorkspaceRoot: "."},
		RosDomainID: "85",
		Navlab: config.NavlabConfig{
			Images: config.ImageCatalog{TagPolicy: "distro-git-commit"},
		},
		Images: map[string]config.Image{
			"mavlink_router":    {Repository: "navlab/mavlink-router"},
			"official_baseline": {Repository: "navlab/official-baseline"},
		},
	}
	_, err := BuildRuntimeSpecs(project, helpers.ExecutionPlan{TaskID: "navigation"}, t.TempDir())
	if err == nil || !strings.Contains(err.Error(), `image tag "humble-latest" targets ROS distro "humble" but selected distro is "jazzy"`) {
		t.Fatalf("err = %v", err)
	}
}

func TestBuildRuntimeSpecsMapsWorkspaceArtifactsToContainerWorkspace(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	t.Setenv("NAVLAB_SIM_IMAGE_TAG", "")
	t.Setenv("NAVLAB_SIM_RUNTIME_IMAGE_TAG", "")
	workspace := t.TempDir()
	artifactDir := filepath.Join(workspace, "artifacts", "sim", "hover", "run-1")
	project := config.ProjectConfig{
		Orchestration: config.OrchestrationConfig{
			Runtime: config.OrchestrationRuntimeConfig{
				Docker: config.DockerRuntimeConfig{WorkspaceContainerPath: "/workspace"},
			},
		},
		Paths:       config.PathConfig{WorkspaceRoot: workspace},
		RosDomainID: "85",
		Navlab: config.NavlabConfig{
			Images: config.ImageCatalog{TagPolicy: "distro-latest"},
		},
		Images: map[string]config.Image{
			"mavlink_router":    {Repository: "navlab/mavlink-router"},
			"official_baseline": {Repository: "navlab/official-baseline"},
		},
	}
	plan := helpers.ExecutionPlan{
		TaskID:      "hover",
		DurationSec: 90,
		RuntimeServices: []helpers.RuntimeServicePlan{
			{
				HelperID:      "sensors",
				ServiceName:   "gazebo_sensor",
				ContainerName: "sensor",
				ImageRef:      "images.official_baseline",
				Command:       []string{"bash", "-lc", "python3 artifacts/runtime/scripts/fcu_controller_runtime.py --log artifacts/runtime/logs/gazebo_sensor.runtime.log"},
				Env:           map[string]string{"NAVLAB_CONFIG": "artifacts/runtime/config/gazebo_sensor_runtime.toml"},
			},
		},
		ROSProbes: []helpers.ROSProbePlan{
			{
				HelperID:     "sensors",
				Name:         "rangefinder_probe",
				ScriptPath:   "probes/rangefinder_probe.py",
				OutputPath:   "probes/rangefinder_probe.txt",
				RuntimeImage: "images.runtime",
				Topics:       []string{"/navlab/rangefinder/range"},
			},
		},
		RosbagRecords: []helpers.RosbagRecordPlan{
			{Name: "hover_rosbag", OutputDir: "rosbag/hover_rosbag", Topics: []string{"/tf"}},
		},
	}

	bundle, err := BuildRuntimeSpecs(project, plan, artifactDir)
	if err != nil {
		t.Fatal(err)
	}
	sensor := serviceByName(bundle.Services, "gazebo_sensor")
	if sensor == nil {
		t.Fatalf("services = %#v", bundle.Services)
		return
	}
	serviceCommand := strings.Join(sensor.Command, " ")
	if !strings.Contains(serviceCommand, "/workspace/artifacts/sim/hover/run-1/runtime/scripts/fcu_controller_runtime.py") {
		t.Fatalf("service command = %q", serviceCommand)
	}
	if sensor.Env["NAVLAB_CONFIG"] != "/workspace/artifacts/sim/hover/run-1/runtime/config/gazebo_sensor_runtime.toml" {
		t.Fatalf("service env = %#v", sensor.Env)
	}
	probeCommand := strings.Join(bundle.Probes[0].Command, " ")
	if !strings.Contains(probeCommand, "/workspace/artifacts/sim/hover/run-1/probes/rangefinder_probe.py") {
		t.Fatalf("probe command = %q", probeCommand)
	}
	if bundle.Rosbags[0].OutputPath != "/workspace/artifacts/sim/hover/run-1/rosbag/hover_rosbag" {
		t.Fatalf("rosbag output = %q", bundle.Rosbags[0].OutputPath)
	}
	if bundle.Probes[0].Volumes[0].Source != workspace {
		t.Fatalf("volume source = %q, want %q", bundle.Probes[0].Volumes[0].Source, workspace)
	}
}

func TestBuildRuntimePlanContract(t *testing.T) {
	artifactDir := t.TempDir()
	topicsProfile := filepath.Join(artifactDir, "hover_rosbag.txt")
	if err := os.WriteFile(topicsProfile, []byte("/tf\n/scan\n"), 0o644); err != nil {
		t.Fatal(err)
	}

	contract, err := BuildRuntimePlanContract(
		Plan{TaskID: "hover", SimulationProfile: ProfileSlamDirectNoOdomPrior},
		"20260613T010203Z",
		RuntimeSpecBundle{
			Services: []simruntime.ServiceSpec{
				{
					Name:        "gazebo_sensor",
					ServiceRole: "sensors",
					Image:       "navlab/gazebo-sensor:latest",
					Command:     []string{"bash", "-lc", "run-sensor"},
					Env:         map[string]string{"ROS_DOMAIN_ID": "85"},
					CWD:         "/workspace",
					Volumes: []simruntime.VolumeMount{
						{Source: "/host/ws", Target: "/workspace", Mode: "ro"},
					},
					Networks: []string{"host"},
					Required: true,
					LogPath:  filepath.Join(artifactDir, "gazebo_sensor.start.log"),
				},
			},
			Probes: []simruntime.ProbeSpec{
				{
					Name:        "rangefinder_probe",
					ServiceRole: "sensors",
					Image:       "navlab/official-baseline:latest",
					Command:     []string{"bash", "-lc", "probe"},
					Env:         map[string]string{"ROS_DOMAIN_ID": "85"},
					TimeoutSec:  30,
					Required:    true,
					LogPath:     filepath.Join(artifactDir, "rangefinder_probe.log"),
				},
			},
			Rosbags: []simruntime.RosbagSpec{
				{
					Name:          "hover_rosbag",
					ServiceRole:   "slam-hover",
					TopicsProfile: topicsProfile,
					OutputPath:    "/workspace/artifacts/rosbag",
					DurationSec:   90,
					Storage:       "mcap",
					Required:      true,
					LogPath:       filepath.Join(artifactDir, "hover_rosbag.log"),
				},
			},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if contract["schemaVersion"] != "navlab.runtime.runtime_plan.v1" {
		t.Fatalf("schemaVersion = %#v", contract["schemaVersion"])
	}
	profile := contract["simulationProfile"].(map[string]any)
	if profile["name"] != ProfileSlamDirectNoOdomPrior || profile["purpose"] != ProfilePurposeMainline || profile["mainline"] != true {
		t.Fatalf("simulation profile contract = %#v", profile)
	}
	services := contract["services"].([]map[string]any)
	if services[0]["backend"] != "RUNTIME_BACKEND_DOCKER" || services[0]["role"] != "sensors" {
		t.Fatalf("service contract = %#v", services[0])
	}
	volumes := services[0]["volumes"].([]map[string]any)
	if volumes[0]["readOnly"] != true {
		t.Fatalf("volume contract = %#v", volumes[0])
	}
	probes := contract["probes"].([]map[string]any)
	if probes[0]["timeoutSec"] != float64(30) {
		t.Fatalf("probe contract = %#v", probes[0])
	}
	rosbags := contract["rosbags"].([]map[string]any)
	topics := rosbags[0]["topics"].([]string)
	if strings.Join(topics, ",") != "/tf,/scan" {
		t.Fatalf("rosbag topics = %#v", topics)
	}
}

func serviceByName(services []simruntime.ServiceSpec, name string) *simruntime.ServiceSpec {
	for index := range services {
		if services[index].Name == name {
			return &services[index]
		}
	}
	return nil
}

func probeByName(probes []simruntime.ProbeSpec, name string) *simruntime.ProbeSpec {
	for index := range probes {
		if probes[index].Name == name {
			return &probes[index]
		}
	}
	return nil
}

func assertVolumeTarget(t *testing.T, volumes []simruntime.VolumeMount, target string) {
	t.Helper()
	for _, volume := range volumes {
		if volume.Target == target {
			if volume.Mode != "ro" {
				t.Fatalf("volume %s mode = %q, want ro", target, volume.Mode)
			}
			return
		}
	}
	t.Fatalf("missing volume target %q in %#v", target, volumes)
}

func TestBuildRuntimeSpecsRejectsMissingImage(t *testing.T) {
	_, err := BuildRuntimeSpecs(
		config.ProjectConfig{},
		helpers.ExecutionPlan{
			RuntimeServices: []helpers.RuntimeServicePlan{
				{HelperID: "slam", ServiceName: "slam_backend", ImageRef: "images.slam", Command: []string{"true"}},
			},
		},
		t.TempDir(),
	)
	if err == nil {
		t.Fatal("BuildRuntimeSpecs error = nil, want missing image error")
	}
}
