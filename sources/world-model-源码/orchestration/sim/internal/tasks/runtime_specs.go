package tasks

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
	"navlab/orchestration-sim/internal/config"
	simimages "navlab/orchestration-sim/internal/images"
	simruntime "navlab/orchestration-sim/internal/runtime"
	"navlab/orchestration-sim/internal/tasks/helpers"
)

type RuntimeSpecBundle struct {
	Services              []simruntime.ServiceSpec `json:"services"`
	Probes                []simruntime.ProbeSpec   `json:"probes"`
	Rosbags               []simruntime.RosbagSpec  `json:"rosbags"`
	StartupReadinessProbe *simruntime.ProbeSpec    `json:"startup_readiness_probe,omitempty"`
}

func BuildRuntimeSpecs(project config.ProjectConfig, plan helpers.ExecutionPlan, artifactDir string) (RuntimeSpecBundle, error) {
	var bundle RuntimeSpecBundle
	workspaceRoot := project.Paths.WorkspaceRoot
	if workspaceRoot == "" {
		workspaceRoot = "."
	}
	absoluteWorkspaceRoot, err := filepath.Abs(workspaceRoot)
	if err != nil {
		return RuntimeSpecBundle{}, err
	}
	containerWorkspace := project.Orchestration.Runtime.Docker.WorkspaceContainerPath
	if containerWorkspace == "" {
		containerWorkspace = "/workspace"
	}
	workspaceMount := simruntime.VolumeMount{
		Source: absoluteWorkspaceRoot,
		Target: containerWorkspace,
	}
	containerArtifactDir, err := containerPath(absoluteWorkspaceRoot, containerWorkspace, artifactDir)
	if err != nil {
		return RuntimeSpecBundle{}, err
	}

	if usesOfficialBaseline(plan) {
		routerSpec, err := mavlinkRouterServiceSpec(project, workspaceMount, containerWorkspace, artifactDir)
		if err != nil {
			return RuntimeSpecBundle{}, err
		}
		if err := routerSpec.ValidateDocker(); err != nil {
			return RuntimeSpecBundle{}, err
		}
		bundle.Services = append(bundle.Services, routerSpec)
		spec, err := officialBaselineServiceSpec(project, workspaceMount, containerWorkspace, containerArtifactDir, artifactDir)
		if err != nil {
			return RuntimeSpecBundle{}, err
		}
		if err := spec.ValidateDocker(); err != nil {
			return RuntimeSpecBundle{}, err
		}
		bundle.Services = append(bundle.Services, spec)
		overlaySpec, ok, err := officialMazeOverlayServiceSpec(project, workspaceMount, containerWorkspace, containerArtifactDir, artifactDir)
		if err != nil {
			return RuntimeSpecBundle{}, err
		}
		if ok {
			if err := overlaySpec.ValidateDocker(); err != nil {
				return RuntimeSpecBundle{}, err
			}
			bundle.Services = append(bundle.Services, overlaySpec)
		}
	}

	for _, service := range plan.RuntimeServices {
		image, err := resolveImageRef(project, service.ImageRef)
		if err != nil {
			return RuntimeSpecBundle{}, err
		}
		command := rewriteArtifactReferences(service.Command, containerArtifactDir)
		env := rewriteArtifactEnv(resolveEnv(project, service.Env), containerArtifactDir)
		volumes := []simruntime.VolumeMount{workspaceMount}
		if service.ServiceName == "slam_backend" {
			volumes, err = appendArtifactVolumeIfPresent(volumes, artifactDir, artifactlayout.RuntimeConfigRel("external_nav_bridge_params.yaml"), helpers.OfficialExternalNavBridgeParams)
			if err != nil {
				return RuntimeSpecBundle{}, err
			}
			volumes, err = appendArtifactVolumeIfPresent(
				volumes,
				artifactDir,
				artifactlayout.RuntimeConfigRel(helpers.HoverCartographerConfigBasename),
				helpers.OfficialCartographerConfigDir+"/"+helpers.HoverCartographerConfigBasename,
			)
			if err != nil {
				return RuntimeSpecBundle{}, err
			}
		}
		spec := simruntime.ServiceSpec{
			Name:          service.ServiceName,
			Image:         image,
			ContainerName: service.ContainerName,
			Command:       command,
			Env:           env,
			CWD:           containerWorkspace,
			Volumes:       volumes,
			Networks:      networks(service.Network),
			Detach:        true,
			Required:      true,
			Restartable:   startupReadinessRestartableService(service.ServiceName),
			LogPath:       artifactlayout.RuntimeLog(artifactDir, service.ServiceName+".start.log"),
			ServiceRole:   service.HelperID,
		}
		if err := spec.ValidateDocker(); err != nil {
			return RuntimeSpecBundle{}, err
		}
		bundle.Services = append(bundle.Services, spec)
	}
	if usesOfficialBaseline(plan) && plan.TaskID != "hover-slam-only" {
		spec, err := mavlinkExternalNavSenderServiceSpec(project, workspaceMount, containerWorkspace, containerArtifactDir, artifactDir)
		if err != nil {
			return RuntimeSpecBundle{}, err
		}
		if err := spec.ValidateDocker(); err != nil {
			return RuntimeSpecBundle{}, err
		}
		bundle.Services = append(bundle.Services, spec)
		heightSpec, err := heightEstimatorServiceSpec(project, workspaceMount, containerWorkspace, containerArtifactDir, artifactDir)
		if err != nil {
			return RuntimeSpecBundle{}, err
		}
		if err := heightSpec.ValidateDocker(); err != nil {
			return RuntimeSpecBundle{}, err
		}
		bundle.Services = append(bundle.Services, heightSpec)
	}

	for _, probe := range plan.ROSProbes {
		image, err := resolveImageRef(project, probe.RuntimeImage)
		if err != nil {
			return RuntimeSpecBundle{}, err
		}
		scriptPath := filepath.Join(artifactDir, probe.ScriptPath)
		outputPath := filepath.Join(artifactDir, probe.OutputPath)
		containerScriptPath, err := containerPath(absoluteWorkspaceRoot, containerWorkspace, scriptPath)
		if err != nil {
			return RuntimeSpecBundle{}, err
		}
		containerOutputPath, err := containerPath(absoluteWorkspaceRoot, containerWorkspace, outputPath)
		if err != nil {
			return RuntimeSpecBundle{}, err
		}
		spec := simruntime.ProbeSpec{
			Name:       probe.Name,
			Image:      image,
			Command:    []string{"bash", "-lc", "python3 " + shellQuote(containerScriptPath) + " > " + shellQuote(containerOutputPath)},
			Env:        baselineEnv(project),
			CWD:        containerWorkspace,
			Volumes:    []simruntime.VolumeMount{workspaceMount},
			OutputPath: outputPath,
			Networks: []string{
				"host",
			},
			TimeoutSec:  probeTimeoutSec(probe.Name, plan.DurationSec),
			LogPath:     artifactlayout.Probe(artifactDir, probe.Name+".log"),
			Required:    probeRequiredForRuntime(probe.Name),
			ServiceRole: probe.HelperID,
		}
		if err := spec.ValidateDocker(); err != nil {
			return RuntimeSpecBundle{}, err
		}
		bundle.Probes = append(bundle.Probes, spec)
	}
	if plan.TaskID == "hover" {
		spec, err := startupReadinessProbeSpec(project, absoluteWorkspaceRoot, containerWorkspace, artifactDir)
		if err != nil {
			return RuntimeSpecBundle{}, err
		}
		if err := spec.ValidateDocker(); err != nil {
			return RuntimeSpecBundle{}, err
		}
		bundle.StartupReadinessProbe = &spec
	}

	for _, rosbag := range plan.RosbagRecords {
		image, err := resolveImageRef(project, "images.runtime")
		if err != nil {
			return RuntimeSpecBundle{}, err
		}
		profilePath, err := writeRosbagTopicsProfile(artifactDir, rosbag.Name, rosbag.Topics)
		if err != nil {
			return RuntimeSpecBundle{}, err
		}
		outputPath, err := containerPath(absoluteWorkspaceRoot, containerWorkspace, filepath.Join(artifactDir, rosbag.OutputDir))
		if err != nil {
			return RuntimeSpecBundle{}, err
		}
		spec := simruntime.RosbagSpec{
			Name:          rosbag.Name,
			Image:         image,
			ContainerName: rosbag.Name,
			TopicsProfile: profilePath,
			OutputPath:    outputPath,
			DurationSec:   plan.DurationSec,
			Storage:       "mcap",
			Env:           baselineEnv(project),
			CWD:           containerWorkspace,
			Volumes:       []simruntime.VolumeMount{workspaceMount},
			Networks:      []string{"host"},
			LogPath:       artifactlayout.RuntimeLog(artifactDir, rosbag.Name+".log"),
			Required:      true,
			ServiceRole:   rosbag.HelperID,
		}
		if _, err := simruntime.RosbagServiceSpec(spec); err != nil {
			return RuntimeSpecBundle{}, err
		}
		bundle.Rosbags = append(bundle.Rosbags, spec)
	}
	return bundle, nil
}

func startupReadinessRestartableService(name string) bool {
	switch name {
	case "gazebo_sensor", "height_estimator":
		return true
	default:
		return false
	}
}

func startupReadinessProbeSpec(
	project config.ProjectConfig,
	absoluteWorkspaceRoot string,
	containerWorkspace string,
	artifactDir string,
) (simruntime.ProbeSpec, error) {
	image, err := resolveImageRef(project, "images.runtime")
	if err != nil {
		return simruntime.ProbeSpec{}, err
	}
	scriptPath := artifactlayout.Probe(artifactDir, "startup_readiness_probe.py")
	outputPath := artifactlayout.Audit(artifactDir, "startup_readiness_probe.json")
	containerScriptPath, err := containerPath(absoluteWorkspaceRoot, containerWorkspace, scriptPath)
	if err != nil {
		return simruntime.ProbeSpec{}, err
	}
	containerOutputPath, err := containerPath(absoluteWorkspaceRoot, containerWorkspace, outputPath)
	if err != nil {
		return simruntime.ProbeSpec{}, err
	}
	return simruntime.ProbeSpec{
		Name:        "startup_readiness_probe",
		Image:       image,
		Command:     []string{"bash", "-lc", "python3 " + shellQuote(containerScriptPath) + " > " + shellQuote(containerOutputPath)},
		Env:         baselineEnv(project),
		CWD:         containerWorkspace,
		Volumes:     []simruntime.VolumeMount{{Source: absoluteWorkspaceRoot, Target: containerWorkspace}},
		OutputPath:  outputPath,
		Networks:    []string{"host"},
		TimeoutSec:  8,
		LogPath:     artifactlayout.RuntimeLog(artifactDir, "startup_readiness_probe.log"),
		Required:    false,
		ServiceRole: "startup-readiness",
	}, nil
}

func probeRequiredForRuntime(name string) bool {
	return name != "slam_hover_probe"
}

func probeTimeoutSec(name string, durationSec float64) float64 {
	if name == "navigation_status_probe" {
		if durationSec > 90 {
			return durationSec
		}
		return 90
	}
	if name == "exploration_probe" {
		return 90
	}
	if name == "slam_hover_probe" {
		if durationSec+30 > 120 {
			return durationSec + 30
		}
		return 120
	}
	return 30
}

func resolveImageRef(project config.ProjectConfig, ref string) (string, error) {
	key := strings.TrimPrefix(strings.TrimSpace(ref), "images.")
	if key == "" {
		return "", fmt.Errorf("image ref is required")
	}
	if key == "runtime" {
		key = "official_baseline"
	}
	image, ok := project.Images[key]
	if !ok || strings.TrimSpace(image.Repository) == "" {
		return "", fmt.Errorf("image %q is not configured", key)
	}
	repository := image.Repository
	if strings.Contains(repository, ":") {
		return repository, nil
	}
	tag, err := simimages.ResolveImageTag(project, image, runtimeImageTagOverride(), "")
	if err != nil {
		return "", err
	}
	return repository + ":" + tag, nil
}

func runtimeImageTagOverride() string {
	if tag := strings.TrimSpace(os.Getenv("NAVLAB_SIM_RUNTIME_IMAGE_TAG")); tag != "" {
		return tag
	}
	if tag := strings.TrimSpace(os.Getenv("NAVLAB_SIM_IMAGE_TAG")); tag != "" {
		return tag
	}
	return ""
}

func resolveEnv(project config.ProjectConfig, values map[string]string) map[string]string {
	resolved := map[string]string{}
	for key, value := range values {
		switch value {
		case "from config.toml":
			switch key {
			case "ROS_DOMAIN_ID", "DDS_DOMAIN_ID":
				resolved[key] = runtimeRosDomain(project)
			case "ROS_DISTRO":
				resolved[key] = runtimeRosDistro(project)
			case "RMW_IMPLEMENTATION":
				resolved[key] = "rmw_cyclonedds_cpp"
			case "DDS_ENABLE":
				resolved[key] = "1"
			default:
				resolved[key] = value
			}
		default:
			resolved[key] = value
		}
	}
	return resolved
}

func baselineEnv(project config.ProjectConfig) map[string]string {
	return map[string]string{
		"CYCLONEDDS_URI":     cycloneDDSParticipantEnv(),
		"DDS_ENABLE":         "1",
		"DDS_DOMAIN_ID":      runtimeRosDomain(project),
		"ROS_DOMAIN_ID":      runtimeRosDomain(project),
		"ROS_DISTRO":         runtimeRosDistro(project),
		"RMW_IMPLEMENTATION": "rmw_cyclonedds_cpp",
	}
}

func cycloneDDSParticipantEnv() string {
	return "<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>"
}

func runtimeRosDomain(project config.ProjectConfig) string {
	if strings.TrimSpace(project.Official.DDSDomainID) != "" {
		return project.Official.DDSDomainID
	}
	return project.RosDomainID
}

func runtimeRosDistro(project config.ProjectConfig) string {
	if envDistro := strings.TrimSpace(os.Getenv("NAVLAB_SIM_DISTRO")); envDistro != "" {
		return envDistro
	}
	if distro := strings.TrimSpace(project.Navlab.Images.Distro); distro != "" {
		return distro
	}
	return "humble"
}

func usesOfficialBaseline(plan helpers.ExecutionPlan) bool {
	switch plan.TaskID {
	case "hover", "hover-slam-only", "exploration", "navigation", "scan-robustness":
		return true
	default:
		return false
	}
}

func mavlinkRouterServiceSpec(
	project config.ProjectConfig,
	workspaceMount simruntime.VolumeMount,
	containerWorkspace string,
	artifactDir string,
) (simruntime.ServiceSpec, error) {
	image, err := resolveImageRef(project, "images.mavlink_router")
	if err != nil {
		return simruntime.ServiceSpec{}, err
	}
	sessionID := strings.TrimSpace(project.SessionID)
	if sessionID == "" {
		sessionID = "navlab_companion_sitl_gazebo"
	}
	env := map[string]string{
		"ARTIFACT_ROOT":               containerWorkspace + "/artifacts/sim",
		"ROUTER_DOWNSTREAM_ENDPOINTS": project.Router.DownstreamEndpoints,
		"ROUTER_LISTEN":               project.Router.Listen,
		"ROUTER_TCP_PORT":             project.Router.TCPPort,
		"SESSION_ID":                  sessionID,
	}
	if strings.TrimSpace(env["ROUTER_DOWNSTREAM_ENDPOINTS"]) == "" {
		env["ROUTER_DOWNSTREAM_ENDPOINTS"] = "127.0.0.1:14551,127.0.0.1:14552,127.0.0.1:14553"
	}
	if strings.TrimSpace(env["ROUTER_LISTEN"]) == "" {
		env["ROUTER_LISTEN"] = "0.0.0.0:14550"
	}
	if strings.TrimSpace(env["ROUTER_TCP_PORT"]) == "" {
		env["ROUTER_TCP_PORT"] = "0"
	}
	return simruntime.ServiceSpec{
		Name:          "mavlink_router",
		Image:         image,
		ContainerName: "navlab-mavlink-router",
		Command:       []string{"bash", "-lc", "exec /workspace/docker/entrypoints/start-mavlink-router.sh"},
		Env:           env,
		CWD:           containerWorkspace,
		Volumes:       []simruntime.VolumeMount{workspaceMount},
		Networks:      []string{"host"},
		Detach:        true,
		Required:      true,
		LogPath:       artifactlayout.RuntimeLog(artifactDir, "mavlink_router.start.log"),
		ServiceRole:   "mavlink-router",
	}, nil
}

func mavlinkExternalNavSenderServiceSpec(
	project config.ProjectConfig,
	workspaceMount simruntime.VolumeMount,
	containerWorkspace string,
	containerArtifactDir string,
	artifactDir string,
) (simruntime.ServiceSpec, error) {
	image, err := resolveImageRef(project, "images.runtime")
	if err != nil {
		return simruntime.ServiceSpec{}, err
	}
	launchCommand := strings.Join([]string{
		"exec python3 -m navlab.real.companion.nodes.external_nav",
		"--endpoint udpin:0.0.0.0:14553",
		"--odom-topic /external_nav/odom",
		"--status-topic /mavlink_external_nav/status",
		"--rate-hz 20",
		"--quality 100",
		"--source-system 191",
		"--use-fcu-roll-pitch",
		"--align-yaw-to-fcu",
		"--local-position-pose-topic /navlab/fcu/local_position_pose",
		"--max-local-position-age-ms 1000",
		"--max-horizontal-speed-mps 0.25",
		"--max-yaw-rate-radps 0.6",
		"> " + shellQuote(containerArtifactDir+"/"+artifactlayout.RuntimeLogRel("mavlink_external_nav.runtime.log")) + " 2>&1",
	}, " ")
	command := strings.Join([]string{
		"source /opt/ros/${ROS_DISTRO:-" + runtimeRosDistro(project) + "}/setup.bash",
		"source ${OFFICIAL_WS:-/opt/navlab_official_ws}/install/setup.bash",
		launchCommand,
	}, " && ")
	env := baselineEnv(project)
	env["PYTHONPATH"] = containerWorkspace
	return simruntime.ServiceSpec{
		Name:          "mavlink_external_nav",
		Image:         image,
		ContainerName: helpers.MAVLinkExternalNavContainer,
		Command:       []string{"bash", "-lc", command},
		Env:           env,
		CWD:           containerWorkspace,
		Volumes:       []simruntime.VolumeMount{workspaceMount},
		Networks:      []string{"host"},
		Detach:        true,
		Required:      true,
		LogPath:       artifactlayout.RuntimeLog(artifactDir, "mavlink_external_nav.start.log"),
		ServiceRole:   "mavlink-external-nav",
	}, nil
}

func heightEstimatorServiceSpec(
	project config.ProjectConfig,
	workspaceMount simruntime.VolumeMount,
	containerWorkspace string,
	containerArtifactDir string,
	artifactDir string,
) (simruntime.ServiceSpec, error) {
	image, err := resolveImageRef(project, "images.runtime")
	if err != nil {
		return simruntime.ServiceSpec{}, err
	}
	launchCommand := strings.Join([]string{
		"exec python3 -m navlab.real.companion.nodes.height_estimator",
		"--range-topic /rangefinder/down/range",
		"--height-topic /height/estimate",
		"--status-topic /height/status",
		"--source-type rangefinder_down_relative",
		"--max-vertical-speed-mps 0.5",
		"--max-vertical-velocity-output-mps 0.25",
		"--velocity-smoothing-alpha 0.25",
		"--max-filter-dt-sec 0.1",
		"> " + shellQuote(containerArtifactDir+"/"+artifactlayout.RuntimeLogRel("height_estimator.runtime.log")) + " 2>&1",
	}, " ")
	command := strings.Join([]string{
		"source /opt/ros/${ROS_DISTRO:-" + runtimeRosDistro(project) + "}/setup.bash",
		"source ${OFFICIAL_WS:-/opt/navlab_official_ws}/install/setup.bash",
		launchCommand,
	}, " && ")
	env := baselineEnv(project)
	env["PYTHONPATH"] = containerWorkspace
	return simruntime.ServiceSpec{
		Name:          "height_estimator",
		Image:         image,
		ContainerName: "navlab-height-estimator",
		Command:       []string{"bash", "-lc", command},
		Env:           env,
		CWD:           containerWorkspace,
		Volumes:       []simruntime.VolumeMount{workspaceMount},
		Networks:      []string{"host"},
		Detach:        true,
		Required:      true,
		Restartable:   true,
		LogPath:       artifactlayout.RuntimeLog(artifactDir, "height_estimator.start.log"),
		ServiceRole:   "height-estimator",
	}, nil
}

func officialBaselineServiceSpec(
	project config.ProjectConfig,
	workspaceMount simruntime.VolumeMount,
	containerWorkspace string,
	containerArtifactDir string,
	artifactDir string,
) (simruntime.ServiceSpec, error) {
	image, err := resolveImageRef(project, "images.official_baseline")
	if err != nil {
		return simruntime.ServiceSpec{}, err
	}
	launch := strings.TrimSpace(project.Official.GazeboLaunch)
	if launch == "" {
		launch = "ros2 launch ardupilot_gz_bringup iris_maze.launch.py"
	}
	launch = ensureBenewakeSerialLaunchArg(launch)
	benewakeSerialLink := "/tmp/navlab_benewake_tfmini"
	command := strings.Join([]string{
		"set -eo pipefail",
		"source /opt/ros/${ROS_DISTRO:-" + runtimeRosDistro(project) + "}/setup.bash",
		"source /opt/navlab_official_ws/install/setup.bash",
		"export PYTHONPATH=" + shellQuote(containerWorkspace) + ":${PYTHONPATH:-}",
		"export NAVLAB_OFFICIAL_SDF_ROOTS=/opt/navlab_official_ws/install/ardupilot_gazebo/share:/opt/navlab_official_ws/install/ardupilot_gz_description/share",
		"export SDF_PATH=${NAVLAB_OFFICIAL_SDF_ROOTS}:${SDF_PATH:-}",
		"export GZ_SIM_RESOURCE_PATH=${NAVLAB_OFFICIAL_SDF_ROOTS}:${GZ_SIM_RESOURCE_PATH:-}",
		"mkdir -p " + shellQuote(containerArtifactDir+"/"+artifactlayout.SITLRel("scripts")),
		"cp " + shellQuote(containerWorkspace+"/docker/profiles/ahrs-set-origin.lua") + " " + shellQuote(containerArtifactDir+"/"+artifactlayout.SITLRel("scripts", "ahrs-set-origin.lua")),
		"test -s " + shellQuote(containerArtifactDir+"/"+artifactlayout.SITLRel("scripts", "ahrs-set-origin.lua")),
		"cd " + shellQuote(containerArtifactDir+"/"+artifactlayout.SITLRel()),
		"python3 -m navlab.sim.gazebo_sensor.benewake_tfmini_serial --virtual-serial-link " + shellQuote(benewakeSerialLink) + " --log-file " + shellQuote(containerArtifactDir+"/"+artifactlayout.RuntimeLogRel("benewake_tfmini_serial.runtime.log")) + " &",
		"benewake_pid=$!",
		"trap 'kill ${benewake_pid:-} 2>/dev/null || true' EXIT",
		"for _ in $(seq 1 200); do [ -e " + shellQuote(benewakeSerialLink) + " ] && break; sleep 0.05; done",
		"test -e " + shellQuote(benewakeSerialLink),
		launch + " use_gz_sim_gui:=false rviz:=false use_dds_agent:=true use_gz_sim_server:=true spawn_robot:=true",
	}, "\n")
	volumes := []simruntime.VolumeMount{workspaceMount}
	volumes, err = appendArtifactVolumeIfPresent(volumes, artifactDir, artifactlayout.RuntimeConfigRel("model_overlay.sdf"), helpers.OfficialIrisWithLidarModel)
	if err != nil {
		return simruntime.ServiceSpec{}, err
	}
	volumes, err = appendArtifactVolumeIfPresent(volumes, artifactDir, artifactlayout.RuntimeConfigRel("gazebo-iris-rangefinder.parm"), helpers.OfficialGazeboIrisParams)
	if err != nil {
		return simruntime.ServiceSpec{}, err
	}
	scanRobustnessBridgeOverride := artifactlayout.RuntimeConfig(artifactDir, "scan_robustness_bridge_override.yaml")
	if _, err := os.Stat(scanRobustnessBridgeOverride); err == nil {
		absoluteScanRobustnessBridgeOverride, err := filepath.Abs(scanRobustnessBridgeOverride)
		if err != nil {
			return simruntime.ServiceSpec{}, err
		}
		volumes = append(volumes, simruntime.VolumeMount{
			Source: absoluteScanRobustnessBridgeOverride,
			Target: helpers.OfficialIris3DBridgeConfig,
		})
	} else {
		bridgeOverride := artifactlayout.RuntimeConfig(artifactDir, "bridge_override.yaml")
		if _, err := os.Stat(bridgeOverride); err == nil {
			absoluteBridgeOverride, err := filepath.Abs(bridgeOverride)
			if err != nil {
				return simruntime.ServiceSpec{}, err
			}
			volumes = append(volumes, simruntime.VolumeMount{
				Source: absoluteBridgeOverride,
				Target: helpers.OfficialIris3DBridgeConfig,
			})
		}
	}
	return simruntime.ServiceSpec{
		Name:          "official_baseline",
		Image:         image,
		ContainerName: "navlab-official-baseline",
		Command:       []string{"bash", "-lc", command},
		Env: map[string]string{
			"SESSION_ID":         project.SessionID,
			"ROS_DOMAIN_ID":      runtimeRosDomain(project),
			"DDS_DOMAIN_ID":      runtimeRosDomain(project),
			"ROS_DISTRO":         runtimeRosDistro(project),
			"DDS_ENABLE":         "1",
			"RMW_IMPLEMENTATION": "rmw_cyclonedds_cpp",
			"PYTHONPATH":         containerWorkspace,
		},
		CWD:         containerWorkspace,
		Volumes:     volumes,
		Networks:    []string{"host"},
		Detach:      true,
		Required:    true,
		LogPath:     artifactlayout.RuntimeLog(artifactDir, "official_baseline.start.log"),
		ServiceRole: "official-baseline",
	}, nil
}

func ensureBenewakeSerialLaunchArg(launch string) string {
	if strings.Contains(launch, "serial7:=") || strings.Contains(launch, "--serial7") {
		return launch
	}
	return strings.TrimSpace(launch) + " serial7:=uart:/tmp/navlab_benewake_tfmini:115200"
}

func officialMazeOverlayServiceSpec(
	project config.ProjectConfig,
	workspaceMount simruntime.VolumeMount,
	containerWorkspace string,
	containerArtifactDir string,
	artifactDir string,
) (simruntime.ServiceSpec, bool, error) {
	script := artifactlayout.RuntimeScript(artifactDir, "official_maze_overlay_runtime.py")
	if _, err := os.Stat(script); err != nil {
		if os.IsNotExist(err) {
			return simruntime.ServiceSpec{}, false, nil
		}
		return simruntime.ServiceSpec{}, false, err
	}
	image, err := resolveImageRef(project, "images.runtime")
	if err != nil {
		return simruntime.ServiceSpec{}, false, err
	}
	command := strings.Join([]string{
		"source /opt/ros/${ROS_DISTRO:-" + runtimeRosDistro(project) + "}/setup.bash",
		"exec python3 " + shellQuote(containerArtifactDir+"/"+artifactlayout.RuntimeScriptRel("official_maze_overlay_runtime.py")) + " > " + shellQuote(containerArtifactDir+"/"+artifactlayout.RuntimeLogRel("official_maze_overlay.runtime.log")) + " 2>&1",
	}, " && ")
	return simruntime.ServiceSpec{
		Name:          "official_maze_overlay",
		Image:         image,
		ContainerName: "navlab-official-maze-overlay",
		Command:       []string{"bash", "-lc", command},
		Env:           baselineEnv(project),
		CWD:           containerWorkspace,
		Volumes:       []simruntime.VolumeMount{workspaceMount},
		Networks:      []string{"host"},
		Detach:        true,
		Required:      true,
		LogPath:       artifactlayout.RuntimeLog(artifactDir, "official_maze_overlay.start.log"),
		ServiceRole:   "foxglove-official-maze-overlay",
	}, true, nil
}

func appendArtifactVolumeIfPresent(volumes []simruntime.VolumeMount, artifactDir string, name string, target string) ([]simruntime.VolumeMount, error) {
	path := filepath.Join(artifactDir, name)
	if _, err := os.Stat(path); err != nil {
		return volumes, nil
	}
	absolutePath, err := filepath.Abs(path)
	if err != nil {
		return nil, err
	}
	return append(volumes, simruntime.VolumeMount{
		Source: absolutePath,
		Target: target,
		Mode:   "ro",
	}), nil
}

func networks(network string) []string {
	if strings.TrimSpace(network) == "" {
		return nil
	}
	return []string{network}
}

func rewriteArtifactReferences(values []string, containerArtifactDir string) []string {
	rewritten := make([]string, 0, len(values))
	for _, value := range values {
		rewritten = append(rewritten, strings.ReplaceAll(value, "artifacts/", containerArtifactDir+"/"))
	}
	return rewritten
}

func rewriteArtifactEnv(values map[string]string, containerArtifactDir string) map[string]string {
	if len(values) == 0 {
		return values
	}
	rewritten := make(map[string]string, len(values))
	for key, value := range values {
		rewritten[key] = strings.ReplaceAll(value, "artifacts/", containerArtifactDir+"/")
	}
	return rewritten
}

func writeRosbagTopicsProfile(artifactDir string, name string, topics []string) (string, error) {
	if len(topics) == 0 {
		return "", fmt.Errorf("rosbag %s has no topics", name)
	}
	path := artifactlayout.Profile(artifactDir, name+".txt")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return "", err
	}
	return path, os.WriteFile(path, []byte(strings.Join(topics, "\n")+"\n"), 0o644)
}

func containerPath(workspaceRoot string, containerWorkspace string, hostPath string) (string, error) {
	cleaned := filepath.Clean(hostPath)
	absoluteHostPath, err := filepath.Abs(cleaned)
	if err != nil {
		return "", err
	}
	relativePath, err := filepath.Rel(workspaceRoot, absoluteHostPath)
	if err == nil && relativePath != "." && !strings.HasPrefix(relativePath, "..") && !filepath.IsAbs(relativePath) {
		return filepath.ToSlash(filepath.Join(containerWorkspace, relativePath)), nil
	}
	if err == nil && relativePath == "." {
		return filepath.ToSlash(containerWorkspace), nil
	}
	if strings.HasPrefix(absoluteHostPath, string(filepath.Separator)) {
		absoluteHostPath = strings.TrimPrefix(absoluteHostPath, string(filepath.Separator))
	}
	return filepath.ToSlash(filepath.Join(containerWorkspace, absoluteHostPath)), nil
}

func shellQuote(value string) string {
	if value == "" {
		return "''"
	}
	return "'" + strings.ReplaceAll(value, "'", "'\"'\"'") + "'"
}
