package helpers

import (
	"os"
	"path/filepath"

	toml "github.com/pelletier/go-toml/v2"
)

const (
	SlamBackendContainer                 = "navlab-slam-backend"
	OfficialExternalNavBridgeParams      = "/opt/navlab_ws/install/navlab_external_nav_bridge/share/navlab_external_nav_bridge/config/navlab_external_nav_bridge.params.yaml"
	OfficialIrisLidarZM                  = "0.075077"
	CartographerOdometryInputTopic       = "/cartographer/odometry_input"
	CartographerTFTopic                  = "/navlab/slam/tf"
	DiagnosticTruthOdometryTopic         = "/odometry"
	DiagnosticGazeboModelOdometryTopic   = "/gazebo/model/odometry"
	DiagnosticGazeboTFTopic              = "/gazebo/tf"
	DiagnosticGazeboTFStaticTopic        = "/gazebo/tf_static"
	DiagnosticCartographerConfigBasename = "navlab_cartographer_2d_diagnostic_odom.lua"
	HoverCartographerConfigBasename      = "navlab_cartographer_2d_hover.lua"
	HoverNoOdomPriorConfigBasename       = "navlab_cartographer_2d_hover_no_odom_prior.lua"
	OfficialCartographerConfigDir        = "/opt/navlab_ws/install/navlab_cartographer_adapter/share/navlab_cartographer_adapter/config"
)

type SlamRuntimeSpec struct {
	Backend                            string
	UseSimTime                         bool
	LaunchPackage                      string
	LaunchFile                         string
	LaunchCartographerBackend          bool
	CartographerConfigurationDirectory string
	CartographerConfigurationBasename  string
	ScanTopic                          string
	IMUSourceTopic                     string
	IMUTopic                           string
	OdometryTopic                      string
	CartographerTFTopic                string
	PublishGlobalTF                    bool
	GlobalTFTopic                      string
	OdomSourceMode                     string
	SlamOdomTopic                      string
	ExternalNavInputOdomTopic          string
	SlamStatusTopic                    string
	ExternalNavStatusTopic             string
	MapFrameID                         string
	OdomFrameID                        string
	BaseFrameID                        string
	IMUFrameID                         string
	LaserFrameID                       string
	RequireIMUForQuality               bool
	RequireScanForQuality              bool
	LowObservabilityMode               bool
}

func ExternalNavBridgeParamsOverride(spec SlamRuntimeSpec) string {
	if spec.Backend == "" {
		spec = DefaultSlamRuntimeSpec()
	}
	externalNavInputOdomTopic := spec.ExternalNavInputOdomTopic
	if externalNavInputOdomTopic == "" {
		externalNavInputOdomTopic = spec.SlamOdomTopic
	}
	return mustRenderHelperTemplate("yaml/external_nav_bridge_params.yaml.tmpl", map[string]any{
		"RequireIMUForQuality":  spec.RequireIMUForQuality,
		"RequireScanForQuality": spec.RequireScanForQuality,
		"LowObservabilityMode":  spec.LowObservabilityMode,
		"InputOdomTopic":        externalNavInputOdomTopic,
		"IMUTopic":              spec.IMUTopic,
		"ScanTopic":             spec.ScanTopic,
		"StatusTopic":           spec.ExternalNavStatusTopic,
		"BaseFrameID":           spec.BaseFrameID,
		"OdomFrameID":           spec.OdomFrameID,
		"MapFrameID":            spec.MapFrameID,
	})
}

func DefaultSlamRuntimeSpec() SlamRuntimeSpec {
	return SlamRuntimeSpec{
		Backend:                            "cartographer",
		UseSimTime:                         true,
		LaunchPackage:                      "navlab_slam_bringup",
		LaunchFile:                         "navlab_slam_bringup.launch.py",
		LaunchCartographerBackend:          true,
		CartographerConfigurationDirectory: "",
		CartographerConfigurationBasename:  "navlab_cartographer_2d_real.lua",
		ScanTopic:                          "/scan",
		IMUSourceTopic:                     "/imu",
		IMUTopic:                           "/imu",
		OdometryTopic:                      CartographerOdometryInputTopic,
		CartographerTFTopic:                CartographerTFTopic,
		PublishGlobalTF:                    true,
		GlobalTFTopic:                      "/tf",
		OdomSourceMode:                     "slam_tf",
		SlamOdomTopic:                      "/slam/odom",
		ExternalNavInputOdomTopic:          "/slam/odom",
		SlamStatusTopic:                    "/navlab/slam/status",
		ExternalNavStatusTopic:             "/external_nav/status",
		MapFrameID:                         "map",
		OdomFrameID:                        "odom",
		BaseFrameID:                        "base_link",
		IMUFrameID:                         "imu_link",
		LaserFrameID:                       "base_scan",
	}
}

func WriteSlamRuntimeConfig(path string, spec SlamRuntimeSpec) error {
	if spec.Backend == "" {
		spec = DefaultSlamRuntimeSpec()
	}
	externalNavInputOdomTopic := spec.ExternalNavInputOdomTopic
	if externalNavInputOdomTopic == "" {
		externalNavInputOdomTopic = spec.SlamOdomTopic
	}
	imuSourceTopic := spec.IMUSourceTopic
	if imuSourceTopic == "" {
		imuSourceTopic = spec.IMUTopic
	}
	data := map[string]any{
		"slam": map[string]any{
			"runtime": map[string]any{
				"backend":                                   spec.Backend,
				"use_sim_time":                              spec.UseSimTime,
				"launch_package":                            spec.LaunchPackage,
				"launch_file":                               spec.LaunchFile,
				"launch_fake_odom":                          false,
				"launch_cartographer_backend":               spec.LaunchCartographerBackend,
				"publish_placeholder_odom":                  false,
				"cartographer_configuration_directory":      spec.CartographerConfigurationDirectory,
				"cartographer_configuration_basename":       spec.CartographerConfigurationBasename,
				"imu_source_mode":                           "topic",
				"imu_source_topic":                          imuSourceTopic,
				"imu_source_label":                          "official_gazebo_imu_bridge",
				"imu_min_input_rate_hz":                     "4.0",
				"require_imu_for_external_nav":              false,
				"require_height_for_external_nav":           true,
				"external_nav_input_odom_topic":             externalNavInputOdomTopic,
				"external_nav_expected_odom_frame_id":       spec.MapFrameID,
				"external_nav_expected_odom_child_frame_id": spec.BaseFrameID,
				"external_nav_output_topic":                 "/external_nav/odom",
				"external_nav_status_topic":                 spec.ExternalNavStatusTopic,
				"scan_topic":                                spec.ScanTopic,
				"imu_topic":                                 spec.IMUTopic,
				"cartographer_odometry_topic":               spec.OdometryTopic,
				"cartographer_tf_topic":                     spec.CartographerTFTopic,
				"publish_global_tf":                         spec.PublishGlobalTF,
				"global_tf_topic":                           spec.GlobalTFTopic,
				"cached_odom_publish_rate_hz":               "10.0",
				"odom_source_mode":                          spec.OdomSourceMode,
				"odom_topic":                                spec.SlamOdomTopic,
				"slam_status_topic":                         spec.SlamStatusTopic,
				"map_frame_id":                              spec.MapFrameID,
				"odom_frame_id":                             spec.OdomFrameID,
				"base_frame_id":                             spec.BaseFrameID,
				"imu_frame_id":                              spec.IMUFrameID,
				"laser_frame_id":                            spec.LaserFrameID,
				"base_frame":                                spec.BaseFrameID,
				"imu_frame":                                 spec.IMUFrameID,
				"laser_frame":                               spec.LaserFrameID,
				"laser_x":                                   "0",
				"laser_y":                                   "0",
				"laser_z":                                   OfficialIrisLidarZM,
				"laser_roll":                                "0",
				"laser_pitch":                               "0",
				"laser_yaw":                                 "0",
			},
		},
	}
	encoded, err := toml.Marshal(data)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, encoded, 0o644)
}
