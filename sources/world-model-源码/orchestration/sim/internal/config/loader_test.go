package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLoaderReadsProjectAndYAMLTasks(t *testing.T) {
	configPath := filepath.Join("..", "..", "config.toml")
	loader := NewLoader(configPath)

	project, err := loader.LoadProject()
	if err != nil {
		t.Fatalf("LoadProject() error = %v", err)
	}
	if project.Orchestration.Family != "sim" {
		t.Fatalf("family = %q, want sim", project.Orchestration.Family)
	}
	if project.Runtime.Mode != "simulation" || project.Orchestration.Runtime.Backend != "docker" {
		t.Fatalf("runtime = %#v orchestration.runtime = %#v, want simulation/docker", project.Runtime, project.Orchestration.Runtime)
	}
	if project.Orchestration.Runtime.Docker.WorkspaceContainerPath != "/workspace" {
		t.Fatalf("workspace container path = %q, want /workspace", project.Orchestration.Runtime.Docker.WorkspaceContainerPath)
	}
	if project.Router.TCPPort != "0" {
		t.Fatalf("router tcp port = %q, want 0", project.Router.TCPPort)
	}
	if project.SessionID != "navlab_companion_sitl_gazebo" {
		t.Fatalf("session id = %q, want navlab_companion_sitl_gazebo", project.SessionID)
	}
	if project.Landing.ExplorationPolicy != "return_home_then_land" {
		t.Fatalf("exploration landing policy = %q, want return_home_then_land", project.Landing.ExplorationPolicy)
	}
	if project.Landing.NavigationPolicy != "land_in_place" {
		t.Fatalf("navigation landing policy = %q, want land_in_place", project.Landing.NavigationPolicy)
	}
	if project.SITL.Image == "" || len(project.SITL.ExtraArgs) == 0 {
		t.Fatalf("sitl config not loaded: %#v", project.SITL)
	}
	if project.Slam.Backend != "cartographer" {
		t.Fatalf("slam backend = %q, want cartographer", project.Slam.Backend)
	}
	if project.Official.ExternalNavRoute != "official_dds" {
		t.Fatalf("official external nav route = %q, want official_dds", project.Official.ExternalNavRoute)
	}
	if project.RangefinderIMU.RangefinderRangeTopic != "/rangefinder/down/range" {
		t.Fatalf("rangefinder range topic = %q", project.RangefinderIMU.RangefinderRangeTopic)
	}
	if project.RangefinderIMU.RangefinderVirtualSerialLink != "/tmp/navlab_benewake_tfmini" ||
		project.RangefinderIMU.RangefinderSerialBaud != 115200 {
		t.Fatalf("rangefinder serial = %s %d", project.RangefinderIMU.RangefinderVirtualSerialLink, project.RangefinderIMU.RangefinderSerialBaud)
	}
	if project.Router.DownstreamEndpoints != "127.0.0.1:14551,127.0.0.1:14552,127.0.0.1:14553" {
		t.Fatalf("router downstream endpoints = %q", project.Router.DownstreamEndpoints)
	}
	if project.FCUController.MAVLinkBootstrapEndpoint != "udpin:0.0.0.0:14551" {
		t.Fatalf("fcu MAVLink endpoint = %q", project.FCUController.MAVLinkBootstrapEndpoint)
	}
	if project.SlamBackend.SlamOdomTopic != "/slam/odom" {
		t.Fatalf("slam odom topic = %q", project.SlamBackend.SlamOdomTopic)
	}
	if project.SlamBackend.CartographerTFTopic != "/navlab/slam/tf" {
		t.Fatalf("cartographer tf topic = %q", project.SlamBackend.CartographerTFTopic)
	}
	if project.FCUController.CmdVelTopic != "/ap/v1/cmd_vel" {
		t.Fatalf("fcu cmd_vel topic = %q", project.FCUController.CmdVelTopic)
	}
	if project.FrameContract.MapFrameID != "map" || len(project.FrameContract.RequiredFrames) == 0 {
		t.Fatalf("frame contract = %#v", project.FrameContract)
	}
	if project.SlamHover.HoverStatusTopic != "/navlab/hover/status" {
		t.Fatalf("hover status topic = %q", project.SlamHover.HoverStatusTopic)
	}
	if project.MotionGate.MotionStatusTopic != "/navlab/motion/status" {
		t.Fatalf("motion status topic = %q", project.MotionGate.MotionStatusTopic)
	}
	if project.ExplorationGate.ExplorationStatusTopic != "/navlab/exploration/status" {
		t.Fatalf("exploration status topic = %q", project.ExplorationGate.ExplorationStatusTopic)
	}
	if project.Nav2.Profile != "indoor_2d" || project.Nav2.Costmap.GlobalCostmapTopic == "" {
		t.Fatalf("nav2 config = %#v", project.Nav2)
	}
	if project.NavigationAdapter.StatusTopic != "/navlab/navigation/adapter/status" {
		t.Fatalf("navigation adapter status topic = %q", project.NavigationAdapter.StatusTopic)
	}
	if project.NavigationMission.StatusTopic != "/navlab/navigation/status" {
		t.Fatalf("navigation mission status topic = %q", project.NavigationMission.StatusTopic)
	}
	if project.NavigationMission.GoalFrame != "map" || project.NavigationMission.ExitGoal.ID != "maze_exit" || len(project.NavigationMission.BoundedGoals) == 0 {
		t.Fatalf("navigation mission goals = %#v", project.NavigationMission)
	}
	if project.ScanStabilization.Mode != "bounded_2d_projection" || !project.ScanStabilization.Enabled {
		t.Fatalf("scan stabilization = %#v", project.ScanStabilization)
	}
	if project.AirframeDisturbance.Profile != "realistic" {
		t.Fatalf("airframe disturbance profile = %q", project.AirframeDisturbance.Profile)
	}
	if len(project.AirframeDisturbanceGate.RequiredProfiles) != 2 {
		t.Fatalf("airframe required profiles = %#v", project.AirframeDisturbanceGate.RequiredProfiles)
	}
	if project.Navlab.Images.TagPolicy != "distro-latest" {
		t.Fatalf("image tag policy = %q, want distro-latest", project.Navlab.Images.TagPolicy)
	}
	if project.Navlab.Images.Distro != "jazzy" {
		t.Fatalf("image distro = %q, want jazzy", project.Navlab.Images.Distro)
	}
	if project.Images["ros_base"].Repository != "navlab/ros-base" {
		t.Fatalf("ros base image = %#v", project.Images["ros_base"])
	}
	if project.Images["official_baseline"].Repository != "navlab/official-baseline" {
		t.Fatalf("official baseline image = %#v", project.Images["official_baseline"])
	}
	if project.Images["companion"].TagPolicy != "distro-git-commit" {
		t.Fatalf("companion tag policy = %q, want distro-git-commit", project.Images["companion"].TagPolicy)
	}
	if project.Images["companion"].BuildArgs["infra_tag"] != "jazzy-latest" {
		t.Fatalf("companion infra_tag = %q, want jazzy-latest", project.Images["companion"].BuildArgs["infra_tag"])
	}
	if project.Images["official_baseline"].TagPolicy != "" {
		t.Fatalf("official baseline tag policy override = %q, want empty", project.Images["official_baseline"].TagPolicy)
	}

	tasks, err := loader.LoadTasks(project)
	if err != nil {
		t.Fatalf("LoadTasks() error = %v", err)
	}
	if len(tasks) != 5 {
		t.Fatalf("len(tasks) = %d, want 5", len(tasks))
	}
	if tasks[0].ID != "exploration" {
		t.Fatalf("first task = %q, want exploration", tasks[0].ID)
	}
	gotTaskIDs := make([]string, 0, len(tasks))
	for _, task := range tasks {
		gotTaskIDs = append(gotTaskIDs, task.ID)
	}
	wantTaskIDs := []string{"exploration", "hover", "hover-slam-only", "navigation", "scan-robustness"}
	if strings.Join(gotTaskIDs, ",") != strings.Join(wantTaskIDs, ",") {
		t.Fatalf("task IDs = %#v, want %#v", gotTaskIDs, wantTaskIDs)
	}
	for _, task := range tasks {
		if task.ID == "hover" && task.Task.SimulationProfile != "slam-direct-no-odom-prior" {
			t.Fatalf("hover default simulation profile = %q, want slam-direct-no-odom-prior", task.Task.SimulationProfile)
		}
	}
}

func TestLoaderRejectsUnknownTask(t *testing.T) {
	configPath := filepath.Join("..", "..", "config.toml")
	loader := NewLoader(configPath)
	project, err := loader.LoadProject()
	if err != nil {
		t.Fatalf("LoadProject() error = %v", err)
	}

	if _, err := loader.LoadTask(project, "preflight"); err == nil {
		t.Fatal("LoadTask(preflight) error = nil, want error")
	}
}

func TestLoaderRequiresNav2Sections(t *testing.T) {
	source, err := os.ReadFile(filepath.Join("..", "..", "config.toml"))
	if err != nil {
		t.Fatal(err)
	}
	configText := removeSections(string(source), "[nav2]", "[nav2.costmap]")
	path := filepath.Join(t.TempDir(), "config.toml")
	if err := os.WriteFile(path, []byte(configText), 0o644); err != nil {
		t.Fatal(err)
	}

	_, err = NewLoader(path).LoadProject()
	if err == nil {
		t.Fatal("LoadProject() error = nil, want nav2 section error")
	}
	if !strings.Contains(err.Error(), "nav2 section is required") {
		t.Fatalf("LoadProject() error = %v", err)
	}
}

func removeSections(content string, markers ...string) string {
	drop := map[string]bool{}
	for _, marker := range markers {
		drop[marker] = true
	}
	lines := strings.Split(content, "\n")
	out := make([]string, 0, len(lines))
	skipping := false
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if strings.HasPrefix(trimmed, "[") && strings.HasSuffix(trimmed, "]") {
			skipping = drop[trimmed]
		}
		if skipping {
			continue
		}
		out = append(out, line)
	}
	return strings.Join(out, "\n")
}
