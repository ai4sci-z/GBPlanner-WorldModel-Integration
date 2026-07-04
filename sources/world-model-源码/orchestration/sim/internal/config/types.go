package config

type ProjectConfig struct {
	Orchestration           OrchestrationConfig           `mapstructure:"orchestration"`
	Runtime                 RuntimeConfig                 `mapstructure:"runtime"`
	Sections                ProjectConfigSections         `mapstructure:"-"`
	Paths                   PathConfig                    `mapstructure:"paths"`
	Router                  RouterConfig                  `mapstructure:"router"`
	Navlab                  NavlabConfig                  `mapstructure:"navlab"`
	Images                  map[string]Image              `mapstructure:"images"`
	SessionID               string                        `mapstructure:"session_id"`
	RosDomainID             string                        `mapstructure:"ros_domain_id"`
	GazeboWorld             string                        `mapstructure:"gazebo_world"`
	RosbagProfile           string                        `mapstructure:"rosbag_profile"`
	Landing                 LandingConfig                 `mapstructure:"landing"`
	SITL                    SITLConfig                    `mapstructure:"sitl"`
	Sensor                  SensorConfig                  `mapstructure:"sensor"`
	Slam                    SlamConfig                    `mapstructure:"slam"`
	Official                OfficialConfig                `mapstructure:"official_baseline"`
	OfficialMazeX2          OfficialMazeX2Config          `mapstructure:"official_maze_x2"`
	RangefinderIMU          RangefinderIMUConfig          `mapstructure:"rangefinder_imu"`
	SlamBackend             SlamBackendConfig             `mapstructure:"slam_backend"`
	FCUController           FCUControllerConfig           `mapstructure:"fcu_controller"`
	FrameContract           FrameContractConfig           `mapstructure:"frame_contract"`
	SlamHover               SlamHoverConfig               `mapstructure:"slam_hover"`
	MotionGate              MotionGateConfig              `mapstructure:"motion_gate"`
	ExplorationGate         ExplorationGateConfig         `mapstructure:"exploration_gate"`
	Nav2                    Nav2Config                    `mapstructure:"nav2"`
	NavigationAdapter       NavigationAdapterConfig       `mapstructure:"navigation_adapter"`
	NavigationMission       NavigationMissionConfig       `mapstructure:"navigation_mission"`
	ScanIntegrityGate       ScanIntegrityGateConfig       `mapstructure:"scan_integrity_gate"`
	ScanStabilization       ScanStabilizationConfig       `mapstructure:"scan_stabilization"`
	ScanStabilizationGate   ScanStabilizationGateConfig   `mapstructure:"scan_stabilization_gate"`
	AirframeDisturbance     AirframeDisturbanceConfig     `mapstructure:"airframe_disturbance"`
	AirframeDisturbanceGate AirframeDisturbanceGateConfig `mapstructure:"airframe_disturbance_gate"`
}

type ProjectConfigSections struct {
	Nav2              bool
	Nav2Costmap       bool
	NavigationAdapter bool
	NavigationMission bool
}

type OrchestrationConfig struct {
	Family          string                     `mapstructure:"family"`
	Implementation  string                     `mapstructure:"implementation"`
	ContractVersion string                     `mapstructure:"contract_version"`
	Runtime         OrchestrationRuntimeConfig `mapstructure:"runtime"`
}

type RuntimeConfig struct {
	Mode    string `mapstructure:"mode"`
	Backend string `mapstructure:"backend"`
}

type OrchestrationRuntimeConfig struct {
	Mode                       string              `mapstructure:"mode"`
	Backend                    string              `mapstructure:"backend"`
	FailOnMissingBackendConfig bool                `mapstructure:"fail_on_missing_backend_config"`
	FailOnModeViolation        bool                `mapstructure:"fail_on_mode_violation"`
	Docker                     DockerRuntimeConfig `mapstructure:"docker"`
}

type DockerRuntimeConfig struct {
	WorkspaceContainerPath string `mapstructure:"workspace_container_path"`
}

type PathConfig struct {
	WorkspaceRoot string `mapstructure:"workspace_root"`
	ArtifactRoot  string `mapstructure:"artifact_root"`
	TaskConfigDir string `mapstructure:"task_config_dir"`
}

type RouterConfig struct {
	Image               string `mapstructure:"image"`
	DownstreamEndpoints string `mapstructure:"downstream_endpoints"`
	Listen              string `mapstructure:"listen"`
	TCPPort             string `mapstructure:"tcp_port"`
}

type NavlabConfig struct {
	Images ImageCatalog `mapstructure:"images"`
}

type ImageCatalog struct {
	Distro      string           `mapstructure:"distro"`
	TagPolicy   string           `mapstructure:"tag_policy"`
	TagStrategy string           `mapstructure:"tag_strategy"`
	Catalog     map[string]Image `mapstructure:",remain"`
}

type Image struct {
	Group      string            `mapstructure:"group"`
	Distro     string            `mapstructure:"distro"`
	TagPolicy  string            `mapstructure:"tag_policy"`
	Repository string            `mapstructure:"repository"`
	Dockerfile string            `mapstructure:"dockerfile"`
	Context    string            `mapstructure:"context"`
	Target     string            `mapstructure:"target"`
	BuildArgs  map[string]string `mapstructure:"build_args"`
}

type LandingConfig struct {
	Enabled                   bool    `mapstructure:"enabled"`
	DefaultPolicy             string  `mapstructure:"default_policy"`
	HoverPolicy               string  `mapstructure:"hover_policy"`
	ExplorationPolicy         string  `mapstructure:"exploration_policy"`
	NavigationPolicy          string  `mapstructure:"navigation_policy"`
	ScanRobustnessPolicy      string  `mapstructure:"scan_robustness_policy"`
	LandingStatusTopic        string  `mapstructure:"landing_status_topic"`
	LandingIntentTopic        string  `mapstructure:"landing_intent_topic"`
	HomeSource                string  `mapstructure:"home_source"`
	HomeRadiusM               float64 `mapstructure:"home_radius_m"`
	PreLandHoldSec            float64 `mapstructure:"pre_land_hold_sec"`
	CompletionGraceSec        float64 `mapstructure:"completion_grace_sec"`
	MaxReturnHomeDurationSec  float64 `mapstructure:"max_return_home_duration_sec"`
	MaxLandingDurationSec     float64 `mapstructure:"max_landing_duration_sec"`
	MaxDescentRateMPS         float64 `mapstructure:"max_descent_rate_mps"`
	SetpointLookaheadSec      float64 `mapstructure:"landing_setpoint_lookahead_sec"`
	TouchdownAltitudeM        float64 `mapstructure:"touchdown_altitude_m"`
	TouchdownVerticalSpeedMPS float64 `mapstructure:"touchdown_vertical_speed_mps"`
	RequireDisarm             bool    `mapstructure:"require_disarm"`
	RequireMotorsSafe         bool    `mapstructure:"require_motors_safe"`
	UsesGazeboTruthAsInput    bool    `mapstructure:"uses_gazebo_truth_as_input"`
}

type SITLConfig struct {
	Image            string   `mapstructure:"image"`
	Model            string   `mapstructure:"model"`
	Speedup          string   `mapstructure:"speedup"`
	Instance         string   `mapstructure:"instance"`
	Home             string   `mapstructure:"home"`
	UpstreamEndpoint string   `mapstructure:"upstream_endpoint"`
	RouterOnly       string   `mapstructure:"router_only"`
	ExtraArgs        []string `mapstructure:"extra_args"`
}

type SensorConfig struct {
	ScanSource string `mapstructure:"scan_source"`
	Image      string `mapstructure:"image"`
}

type SlamConfig struct {
	Autostart     bool   `mapstructure:"autostart"`
	Image         string `mapstructure:"image"`
	Backend       string `mapstructure:"backend"`
	RuntimeConfig string `mapstructure:"runtime_config"`
}

type OfficialConfig struct {
	RosbagProfile         string   `mapstructure:"rosbag_profile"`
	DDSEnable             string   `mapstructure:"dds_enable"`
	DDSDomainID           string   `mapstructure:"dds_domain_id"`
	RMWImplementation     string   `mapstructure:"rmw_implementation"`
	ExpectedAPNode        string   `mapstructure:"expected_ap_node"`
	RequiredAPTopics      []string `mapstructure:"required_ap_topics"`
	RuntimeImage          string   `mapstructure:"runtime_image"`
	RequiredROSPackages   []string `mapstructure:"required_ros_packages"`
	MicroROSAgentBinaries []string `mapstructure:"micro_ros_agent_binaries"`
	SITLLaunch            string   `mapstructure:"sitl_launch"`
	GazeboLaunch          string   `mapstructure:"gazebo_launch"`
	CartographerLaunch    string   `mapstructure:"cartographer_launch"`
	GazeboBringupMode     string   `mapstructure:"gazebo_bringup_mode"`
	ExternalNavRoute      string   `mapstructure:"external_nav_route"`
}

type OfficialMazeX2Config struct {
	RosbagProfile        string `mapstructure:"rosbag_profile"`
	WorldSource          string `mapstructure:"world_source"`
	VehicleModelSource   string `mapstructure:"vehicle_model_source"`
	GazeboLidarTopic     string `mapstructure:"gazebo_lidar_topic"`
	X2ScanInputTopic     string `mapstructure:"x2_scan_input_topic"`
	X2ScanTopic          string `mapstructure:"x2_scan_topic"`
	X2StatusTopic        string `mapstructure:"x2_status_topic"`
	X2VirtualSerialLink  string `mapstructure:"x2_virtual_serial_link"`
	AltitudeControlClaim string `mapstructure:"altitude_control_claim"`
	HoverClaim           string `mapstructure:"hover_claim"`
	CartographerLaunch   string `mapstructure:"cartographer_launch"`
}

type RangefinderIMUConfig struct {
	RosbagProfile                string  `mapstructure:"rosbag_profile"`
	WorldSource                  string  `mapstructure:"world_source"`
	VehicleModelSource           string  `mapstructure:"vehicle_model_source"`
	ModelOverlaySource           string  `mapstructure:"model_overlay_source"`
	GazeboLidarTopic             string  `mapstructure:"gazebo_lidar_topic"`
	X2ScanInputTopic             string  `mapstructure:"x2_scan_input_topic"`
	X2ScanTopic                  string  `mapstructure:"x2_scan_topic"`
	X2StatusTopic                string  `mapstructure:"x2_status_topic"`
	X2VirtualSerialLink          string  `mapstructure:"x2_virtual_serial_link"`
	RangefinderScanIdealTopic    string  `mapstructure:"rangefinder_scan_ideal_topic"`
	RangefinderRangeTopic        string  `mapstructure:"rangefinder_range_topic"`
	RangefinderStatusTopic       string  `mapstructure:"rangefinder_status_topic"`
	RangefinderFrameID           string  `mapstructure:"rangefinder_frame_id"`
	RangefinderModelPose         string  `mapstructure:"rangefinder_model_pose"`
	RangefinderModelUpdateRateHz float64 `mapstructure:"rangefinder_model_update_rate_hz"`
	RangefinderModelRayCount     string  `mapstructure:"rangefinder_model_ray_count"`
	RangefinderModelNoiseStddevM float64 `mapstructure:"rangefinder_model_noise_stddev_m"`
	RangefinderVirtualSerialLink string  `mapstructure:"rangefinder_virtual_serial_link"`
	RangefinderSerialBaud        int     `mapstructure:"rangefinder_serial_baud"`
	RangefinderFCUProbeEndpoint  string  `mapstructure:"rangefinder_fcu_probe_endpoint"`
	RangefinderRateHz            float64 `mapstructure:"rangefinder_rate_hz"`
	RangefinderMinDistanceM      float64 `mapstructure:"rangefinder_min_distance_m"`
	RangefinderMaxDistanceM      float64 `mapstructure:"rangefinder_max_distance_m"`
	IMUSourceRoute               string  `mapstructure:"imu_source_route"`
	IMUSourceTopic               string  `mapstructure:"imu_source_topic"`
	IMUOutputTopic               string  `mapstructure:"imu_output_topic"`
	IMUStatusTopic               string  `mapstructure:"imu_status_topic"`
	IMUFrameID                   string  `mapstructure:"imu_frame_id"`
	IMUMinRateHz                 float64 `mapstructure:"imu_min_rate_hz"`
	SyntheticFallbackEnabled     bool    `mapstructure:"synthetic_fallback_enabled"`
	AltitudeControlClaim         string  `mapstructure:"altitude_control_claim"`
	HoverClaim                   string  `mapstructure:"hover_claim"`
	CartographerLaunch           string  `mapstructure:"cartographer_launch"`
}

type SlamBackendConfig struct {
	RosbagProfile                     string  `mapstructure:"rosbag_profile"`
	Backend                           string  `mapstructure:"backend"`
	LaunchPackage                     string  `mapstructure:"launch_package"`
	LaunchFile                        string  `mapstructure:"launch_file"`
	CartographerConfigurationBasename string  `mapstructure:"cartographer_configuration_basename"`
	ScanTopic                         string  `mapstructure:"scan_topic"`
	IMUTopic                          string  `mapstructure:"imu_topic"`
	OdometryTopic                     string  `mapstructure:"odometry_topic"`
	CartographerTFTopic               string  `mapstructure:"cartographer_tf_topic"`
	OdomSourceMode                    string  `mapstructure:"odom_source_mode"`
	SlamOdomTopic                     string  `mapstructure:"slam_odom_topic"`
	SlamStatusTopic                   string  `mapstructure:"slam_status_topic"`
	ExternalNavStatusTopic            string  `mapstructure:"external_nav_status_topic"`
	X2ScanInputTopic                  string  `mapstructure:"x2_scan_input_topic"`
	X2VendorScanTopic                 string  `mapstructure:"x2_vendor_scan_topic"`
	X2ScanTopic                       string  `mapstructure:"x2_scan_topic"`
	X2StatusTopic                     string  `mapstructure:"x2_status_topic"`
	RangefinderRangeTopic             string  `mapstructure:"rangefinder_range_topic"`
	RangefinderStatusTopic            string  `mapstructure:"rangefinder_status_topic"`
	IMUFrameID                        string  `mapstructure:"imu_frame_id"`
	LaserFrameID                      string  `mapstructure:"laser_frame_id"`
	MapFrameID                        string  `mapstructure:"map_frame_id"`
	OdomFrameID                       string  `mapstructure:"odom_frame_id"`
	BaseFrameID                       string  `mapstructure:"base_frame_id"`
	MinSlamOdomRateHz                 float64 `mapstructure:"min_slam_odom_rate_hz"`
	MaxLatestAgeSec                   float64 `mapstructure:"max_latest_age_sec"`
	MaxJumpM                          float64 `mapstructure:"max_jump_m"`
	MaxYawJumpRad                     float64 `mapstructure:"max_yaw_jump_rad"`
	MaxStationaryDriftM               float64 `mapstructure:"max_stationary_drift_m"`
	TruthDiagnosticTopic              string  `mapstructure:"truth_diagnostic_topic"`
	UsesGazeboTruthAsInput            bool    `mapstructure:"uses_gazebo_truth_as_input"`
}

type FCUControllerConfig struct {
	RosbagProfile                   string  `mapstructure:"rosbag_profile"`
	ControlRoute                    string  `mapstructure:"control_route"`
	MAVLinkBootstrapEndpoint        string  `mapstructure:"mavlink_bootstrap_endpoint"`
	MAVLinkBootstrapSourceSystem    int     `mapstructure:"mavlink_bootstrap_source_system"`
	MAVLinkBootstrapSourceComponent int     `mapstructure:"mavlink_bootstrap_source_component"`
	OwnerName                       string  `mapstructure:"owner_name"`
	OwnerID                         string  `mapstructure:"owner_id"`
	FCUStateTopic                   string  `mapstructure:"fcu_state_topic"`
	ControllerStatusTopic           string  `mapstructure:"controller_status_topic"`
	SetpointIntentTopic             string  `mapstructure:"setpoint_intent_topic"`
	SetpointOutputTopic             string  `mapstructure:"setpoint_output_topic"`
	OwnerStatusTopic                string  `mapstructure:"owner_status_topic"`
	TimeTopic                       string  `mapstructure:"time_topic"`
	PrearmService                   string  `mapstructure:"prearm_service"`
	ModeSwitchService               string  `mapstructure:"mode_switch_service"`
	ArmService                      string  `mapstructure:"arm_service"`
	TakeoffService                  string  `mapstructure:"takeoff_service"`
	CmdVelTopic                     string  `mapstructure:"cmd_vel_topic"`
	PoseTopic                       string  `mapstructure:"pose_topic"`
	TwistTopic                      string  `mapstructure:"twist_topic"`
	StatusTopic                     string  `mapstructure:"status_topic"`
	RangefinderRangeTopic           string  `mapstructure:"rangefinder_range_topic"`
	RangefinderStatusTopic          string  `mapstructure:"rangefinder_status_topic"`
	IMUTopic                        string  `mapstructure:"imu_topic"`
	SlamOdomTopic                   string  `mapstructure:"slam_odom_topic"`
	SlamStatusTopic                 string  `mapstructure:"slam_status_topic"`
	GuidedMode                      int     `mapstructure:"guided_mode"`
	TakeoffAltM                     float64 `mapstructure:"takeoff_alt_m"`
	TakeoffMinHeightM               float64 `mapstructure:"takeoff_min_height_m"`
	TakeoffMinHeightRatio           float64 `mapstructure:"takeoff_min_height_ratio"`
	ReadinessTimeoutSec             float64 `mapstructure:"readiness_timeout_sec"`
	HoldAfterReadySec               float64 `mapstructure:"hold_after_ready_sec"`
	RequireSlamBackend              bool    `mapstructure:"require_slam_backend"`
	HoverClaim                      string  `mapstructure:"hover_claim"`
	ExplorationClaim                string  `mapstructure:"exploration_claim"`
}

type FrameContractConfig struct {
	RosbagProfile               string   `mapstructure:"rosbag_profile"`
	RequiredFrames              []string `mapstructure:"required_frames"`
	MapFrameID                  string   `mapstructure:"map_frame_id"`
	OdomFrameID                 string   `mapstructure:"odom_frame_id"`
	BaseFrameID                 string   `mapstructure:"base_frame_id"`
	IMUFrameID                  string   `mapstructure:"imu_frame_id"`
	LaserFrameID                string   `mapstructure:"laser_frame_id"`
	RangefinderFrameID          string   `mapstructure:"rangefinder_frame_id"`
	ScanTopic                   string   `mapstructure:"scan_topic"`
	IMUTopic                    string   `mapstructure:"imu_topic"`
	RangefinderRangeTopic       string   `mapstructure:"rangefinder_range_topic"`
	RangefinderStatusTopic      string   `mapstructure:"rangefinder_status_topic"`
	FCUPoseTopic                string   `mapstructure:"fcu_pose_topic"`
	FCUTwistTopic               string   `mapstructure:"fcu_twist_topic"`
	FCUStatusTopic              string   `mapstructure:"fcu_status_topic"`
	CmdVelTopic                 string   `mapstructure:"cmd_vel_topic"`
	SlamOdomTopic               string   `mapstructure:"slam_odom_topic"`
	SlamStatusTopic             string   `mapstructure:"slam_status_topic"`
	TruthDiagnosticTopic        string   `mapstructure:"truth_diagnostic_topic"`
	ControllerStatusTopic       string   `mapstructure:"controller_status_topic"`
	SetpointOutputTopic         string   `mapstructure:"setpoint_output_topic"`
	OwnerStatusTopic            string   `mapstructure:"owner_status_topic"`
	StatusTopic                 string   `mapstructure:"status_topic"`
	MaxDynamicTFAgeSec          float64  `mapstructure:"max_dynamic_tf_age_sec"`
	MinScanValidRatio           float64  `mapstructure:"min_scan_valid_ratio"`
	MaxRangefinderHeightErrorM  float64  `mapstructure:"max_rangefinder_height_error_m"`
	MaxDirectionErrorRad        float64  `mapstructure:"max_direction_error_rad"`
	ProbeDurationSec            float64  `mapstructure:"probe_duration_sec"`
	RequireMotionDirectionCheck bool     `mapstructure:"require_motion_direction_check"`
	HoverClaim                  string   `mapstructure:"hover_claim"`
	ExplorationClaim            string   `mapstructure:"exploration_claim"`
	UsesGazeboTruthAsInput      bool     `mapstructure:"uses_gazebo_truth_as_input"`
}

type SlamHoverConfig struct {
	RosbagProfile                string                       `mapstructure:"rosbag_profile"`
	SlamOdomTopic                string                       `mapstructure:"slam_odom_topic"`
	ExternalNavInputOdomTopic    string                       `mapstructure:"external_nav_input_odom_topic"`
	SlamStatusTopic              string                       `mapstructure:"slam_status_topic"`
	ExternalNavStatusTopic       string                       `mapstructure:"external_nav_status_topic"`
	FCUPoseTopic                 string                       `mapstructure:"fcu_pose_topic"`
	FCUTwistTopic                string                       `mapstructure:"fcu_twist_topic"`
	FCUStatusTopic               string                       `mapstructure:"fcu_status_topic"`
	CmdVelTopic                  string                       `mapstructure:"cmd_vel_topic"`
	RangefinderRangeTopic        string                       `mapstructure:"rangefinder_range_topic"`
	RangefinderStatusTopic       string                       `mapstructure:"rangefinder_status_topic"`
	IMUTopic                     string                       `mapstructure:"imu_topic"`
	TruthDiagnosticTopic         string                       `mapstructure:"truth_diagnostic_topic"`
	ControllerStatusTopic        string                       `mapstructure:"controller_status_topic"`
	SetpointIntentTopic          string                       `mapstructure:"setpoint_intent_topic"`
	SetpointOutputTopic          string                       `mapstructure:"setpoint_output_topic"`
	OwnerStatusTopic             string                       `mapstructure:"owner_status_topic"`
	HoverStatusTopic             string                       `mapstructure:"hover_status_topic"`
	VehicleMarkerTopic           string                       `mapstructure:"vehicle_marker_topic"`
	VehicleMarkerPoseTopic       string                       `mapstructure:"vehicle_marker_pose_topic"`
	VehicleMarkerFrameID         string                       `mapstructure:"vehicle_marker_frame_id"`
	VehicleMarkerRateHz          float64                      `mapstructure:"vehicle_marker_rate_hz"`
	RecordVisualizationMarkers   bool                         `mapstructure:"record_visualization_markers"`
	SettleWindowSec              float64                      `mapstructure:"settle_window_sec"`
	HoverWindowSec               float64                      `mapstructure:"hover_window_sec"`
	HoverHealthMinObservationSec float64                      `mapstructure:"hover_health_min_observation_sec"`
	HoverHealthStableRequiredSec float64                      `mapstructure:"hover_health_stable_required_sec"`
	HoverHealthMaxWaitSec        float64                      `mapstructure:"hover_health_max_wait_sec"`
	StartupReadinessPolicy       StartupReadinessPolicyConfig `mapstructure:"startup_readiness_policy" json:"startup_readiness_policy"`
	OperatorConfirmRequired      bool                         `mapstructure:"operator_confirm_required"`
	OperatorConfirmTimeoutSec    float64                      `mapstructure:"operator_confirm_timeout_sec"`
	FinalHoldWindowSec           float64                      `mapstructure:"final_hold_window_sec"`
	MaxHoverHorizontalDriftM     float64                      `mapstructure:"max_hover_horizontal_drift_m"`
	HoverSpanTargetM             float64                      `mapstructure:"hover_span_target_m"`
	HoverSpanHardCapM            float64                      `mapstructure:"hover_span_hard_cap_m"`
	MaxHoverAltitudeErrorM       float64                      `mapstructure:"max_hover_altitude_error_m"`
	MaxHoverYawDriftRad          float64                      `mapstructure:"max_hover_yaw_drift_rad"`
	MaxStopDriftM                float64                      `mapstructure:"max_stop_drift_m"`
	MinSlamOdomRateHz            float64                      `mapstructure:"min_slam_odom_rate_hz"`
	MinExternalNavRateHz         float64                      `mapstructure:"min_external_nav_rate_hz"`
	MinFCULocalPositionRateHz    float64                      `mapstructure:"min_fcu_local_position_rate_hz"`
	MaxLatestAgeSec              float64                      `mapstructure:"max_latest_age_sec"`
	UsesGazeboTruthAsInput       bool                         `mapstructure:"uses_gazebo_truth_as_input"`
	HoverClaim                   string                       `mapstructure:"hover_claim"`
	ExplorationClaim             string                       `mapstructure:"exploration_claim"`
}

type StartupReadinessPolicyConfig struct {
	TimeoutSec        float64 `mapstructure:"timeout_sec" json:"timeout_sec"`
	GraceSec          float64 `mapstructure:"grace_sec" json:"grace_sec"`
	ProgressWindowSec float64 `mapstructure:"progress_window_sec" json:"progress_window_sec"`
	RestartLimit      int     `mapstructure:"restart_limit" json:"restart_limit"`
}

type MotionGateConfig struct {
	RosbagProfile             string  `mapstructure:"rosbag_profile"`
	SlamOdomTopic             string  `mapstructure:"slam_odom_topic"`
	SlamStatusTopic           string  `mapstructure:"slam_status_topic"`
	ExternalNavStatusTopic    string  `mapstructure:"external_nav_status_topic"`
	FCUPoseTopic              string  `mapstructure:"fcu_pose_topic"`
	FCUTwistTopic             string  `mapstructure:"fcu_twist_topic"`
	FCUStatusTopic            string  `mapstructure:"fcu_status_topic"`
	CmdVelTopic               string  `mapstructure:"cmd_vel_topic"`
	RangefinderRangeTopic     string  `mapstructure:"rangefinder_range_topic"`
	RangefinderStatusTopic    string  `mapstructure:"rangefinder_status_topic"`
	IMUTopic                  string  `mapstructure:"imu_topic"`
	ScanTopic                 string  `mapstructure:"scan_topic"`
	TruthDiagnosticTopic      string  `mapstructure:"truth_diagnostic_topic"`
	ControllerStatusTopic     string  `mapstructure:"controller_status_topic"`
	SetpointIntentTopic       string  `mapstructure:"setpoint_intent_topic"`
	SetpointOutputTopic       string  `mapstructure:"setpoint_output_topic"`
	OwnerStatusTopic          string  `mapstructure:"owner_status_topic"`
	HoverStatusTopic          string  `mapstructure:"hover_status_topic"`
	MotionStatusTopic         string  `mapstructure:"motion_status_topic"`
	SettleWindowSec           float64 `mapstructure:"settle_window_sec"`
	ForwardWindowSec          float64 `mapstructure:"forward_window_sec"`
	BackWindowSec             float64 `mapstructure:"back_window_sec"`
	YawWindowSec              float64 `mapstructure:"yaw_window_sec"`
	StopHoldWindowSec         float64 `mapstructure:"stop_hold_window_sec"`
	FinalHoldWindowSec        float64 `mapstructure:"final_hold_window_sec"`
	MotionDistanceM           float64 `mapstructure:"motion_distance_m"`
	MotionSpeedMPS            float64 `mapstructure:"motion_speed_mps"`
	YawScanRad                float64 `mapstructure:"yaw_scan_rad"`
	YawRateRadPS              float64 `mapstructure:"yaw_rate_radps"`
	MinForwardDisplacementM   float64 `mapstructure:"min_forward_displacement_m"`
	MaxForwardDisplacementM   float64 `mapstructure:"max_forward_displacement_m"`
	MinBackDisplacementM      float64 `mapstructure:"min_back_displacement_m"`
	MaxBackDisplacementM      float64 `mapstructure:"max_back_displacement_m"`
	MinYawDeltaRad            float64 `mapstructure:"min_yaw_delta_rad"`
	MaxYawDeltaRad            float64 `mapstructure:"max_yaw_delta_rad"`
	MaxLateralErrorM          float64 `mapstructure:"max_lateral_error_m"`
	MaxMotionAltitudeErrorM   float64 `mapstructure:"max_motion_altitude_error_m"`
	MaxStopDriftM             float64 `mapstructure:"max_stop_drift_m"`
	MinClearanceM             float64 `mapstructure:"min_clearance_m"`
	MinSlamOdomRateHz         float64 `mapstructure:"min_slam_odom_rate_hz"`
	MinExternalNavRateHz      float64 `mapstructure:"min_external_nav_rate_hz"`
	MinFCULocalPositionRateHz float64 `mapstructure:"min_fcu_local_position_rate_hz"`
	MaxLatestAgeSec           float64 `mapstructure:"max_latest_age_sec"`
	UsesGazeboTruthAsInput    bool    `mapstructure:"uses_gazebo_truth_as_input"`
	HoverClaim                string  `mapstructure:"hover_claim"`
	MotionClaim               string  `mapstructure:"motion_claim"`
	ExplorationClaim          string  `mapstructure:"exploration_claim"`
}

type ExplorationGateConfig struct {
	RosbagProfile             string  `mapstructure:"rosbag_profile"`
	Strategy                  string  `mapstructure:"strategy"`
	SlamOdomTopic             string  `mapstructure:"slam_odom_topic"`
	SlamStatusTopic           string  `mapstructure:"slam_status_topic"`
	ExternalNavStatusTopic    string  `mapstructure:"external_nav_status_topic"`
	MapTopic                  string  `mapstructure:"map_topic"`
	SubmapListTopic           string  `mapstructure:"submap_list_topic"`
	TrajectoryNodeListTopic   string  `mapstructure:"trajectory_node_list_topic"`
	FCUPoseTopic              string  `mapstructure:"fcu_pose_topic"`
	FCUTwistTopic             string  `mapstructure:"fcu_twist_topic"`
	FCUStatusTopic            string  `mapstructure:"fcu_status_topic"`
	CmdVelTopic               string  `mapstructure:"cmd_vel_topic"`
	RangefinderRangeTopic     string  `mapstructure:"rangefinder_range_topic"`
	RangefinderStatusTopic    string  `mapstructure:"rangefinder_status_topic"`
	IMUTopic                  string  `mapstructure:"imu_topic"`
	ScanTopic                 string  `mapstructure:"scan_topic"`
	TruthDiagnosticTopic      string  `mapstructure:"truth_diagnostic_topic"`
	ControllerStatusTopic     string  `mapstructure:"controller_status_topic"`
	SetpointIntentTopic       string  `mapstructure:"setpoint_intent_topic"`
	SetpointOutputTopic       string  `mapstructure:"setpoint_output_topic"`
	OwnerStatusTopic          string  `mapstructure:"owner_status_topic"`
	HoverStatusTopic          string  `mapstructure:"hover_status_topic"`
	MotionStatusTopic         string  `mapstructure:"motion_status_topic"`
	ExplorationStatusTopic    string  `mapstructure:"exploration_status_topic"`
	ExplorationGoalTopic      string  `mapstructure:"exploration_goal_topic"`
	ExplorationCoverageTopic  string  `mapstructure:"exploration_coverage_topic"`
	ExplorationFrontiersTopic string  `mapstructure:"exploration_frontiers_topic"`
	ExplorationPathTopic      string  `mapstructure:"exploration_path_topic"`
	ExplorationMarkersTopic   string  `mapstructure:"exploration_markers_topic"`
	SettleWindowSec           float64 `mapstructure:"settle_window_sec"`
	ExplorationWindowSec      float64 `mapstructure:"exploration_window_sec"`
	ForwardProbeWindowSec     float64 `mapstructure:"forward_probe_window_sec"`
	YawScanWindowSec          float64 `mapstructure:"yaw_scan_window_sec"`
	StopHoldWindowSec         float64 `mapstructure:"stop_hold_window_sec"`
	FinalHoldWindowSec        float64 `mapstructure:"final_hold_window_sec"`
	MotionSpeedMPS            float64 `mapstructure:"motion_speed_mps"`
	YawRateRadPS              float64 `mapstructure:"yaw_rate_radps"`
	MinAcceptedGoals          int     `mapstructure:"min_accepted_goals"`
	MinPathLengthM            float64 `mapstructure:"min_path_length_m"`
	MinKnownCellGrowth        int     `mapstructure:"min_known_cell_growth"`
	MaxStopDriftM             float64 `mapstructure:"max_stop_drift_m"`
	MinClearanceM             float64 `mapstructure:"min_clearance_m"`
	StuckTimeoutSec           float64 `mapstructure:"stuck_timeout_sec"`
	MinSlamOdomRateHz         float64 `mapstructure:"min_slam_odom_rate_hz"`
	MinExternalNavRateHz      float64 `mapstructure:"min_external_nav_rate_hz"`
	MinFCULocalPositionRateHz float64 `mapstructure:"min_fcu_local_position_rate_hz"`
	MaxLatestAgeSec           float64 `mapstructure:"max_latest_age_sec"`
	UsesGazeboTruthAsInput    bool    `mapstructure:"uses_gazebo_truth_as_input"`
	HoverClaim                string  `mapstructure:"hover_claim"`
	MotionClaim               string  `mapstructure:"motion_claim"`
	ExplorationClaim          string  `mapstructure:"exploration_claim"`
}

type Nav2Config struct {
	Enabled          bool              `mapstructure:"enabled"`
	Profile          string            `mapstructure:"profile"`
	GlobalFrame      string            `mapstructure:"global_frame"`
	OdomFrame        string            `mapstructure:"odom_frame"`
	BaseFrame        string            `mapstructure:"base_frame"`
	ScanTopic        string            `mapstructure:"scan_topic"`
	MapTopic         string            `mapstructure:"map_topic"`
	CmdVelTopic      string            `mapstructure:"cmd_vel_topic"`
	BTXML            string            `mapstructure:"bt_xml"`
	PlannerPlugin    string            `mapstructure:"planner_plugin"`
	ControllerPlugin string            `mapstructure:"controller_plugin"`
	UseSimTime       bool              `mapstructure:"use_sim_time"`
	Costmap          Nav2CostmapConfig `mapstructure:"costmap"`
}

type Nav2CostmapConfig struct {
	GlobalCostmapTopic string   `mapstructure:"global_costmap_topic"`
	LocalCostmapTopic  string   `mapstructure:"local_costmap_topic"`
	RequiredLayers     []string `mapstructure:"required_layers"`
	MaxCostmapAgeSec   float64  `mapstructure:"max_costmap_age_sec"`
	MinObstacleCells   int      `mapstructure:"min_obstacle_cells"`
	MaxUnknownRatio    float64  `mapstructure:"max_unknown_ratio"`
	InflationRadiusM   float64  `mapstructure:"inflation_radius_m"`
	FootprintRadiusM   float64  `mapstructure:"footprint_radius_m"`
	HealthTopic        string   `mapstructure:"health_topic"`
	UsesGazeboTruth    bool     `mapstructure:"uses_gazebo_truth"`
	CostmapHealthClaim string   `mapstructure:"costmap_health_claim"`
}

type NavigationAdapterConfig struct {
	SetpointIntentTopic string  `mapstructure:"setpoint_intent_topic"`
	StatusTopic         string  `mapstructure:"status_topic"`
	MaxXYSpeedMPS       float64 `mapstructure:"max_xy_speed_mps"`
	MaxYawRateDPS       float64 `mapstructure:"max_yaw_rate_dps"`
	MaxAccelMPS2        float64 `mapstructure:"max_accel_mps2"`
	FixedAltitudeM      float64 `mapstructure:"fixed_altitude_m"`
	StopOnStaleCostmap  bool    `mapstructure:"stop_on_stale_costmap"`
	StopOnStaleSlam     bool    `mapstructure:"stop_on_stale_slam"`
	AdapterClaim        string  `mapstructure:"adapter_claim"`
}

type NavigationMissionConfig struct {
	Strategy               string                 `mapstructure:"strategy"`
	CompletionPolicy       string                 `mapstructure:"completion_policy"`
	GoalFrame              string                 `mapstructure:"goal_frame"`
	StatusTopic            string                 `mapstructure:"status_topic"`
	EventsTopic            string                 `mapstructure:"events_topic"`
	GoalTopic              string                 `mapstructure:"goal_topic"`
	PathTopic              string                 `mapstructure:"path_topic"`
	RecoveryTopic          string                 `mapstructure:"recovery_topic"`
	NavigationWindowSec    float64                `mapstructure:"navigation_window_sec"`
	MaxGoalRadiusM         float64                `mapstructure:"max_goal_radius_m"`
	MinClearanceM          float64                `mapstructure:"min_clearance_m"`
	MinCoverageGrowth      float64                `mapstructure:"min_coverage_growth"`
	MinPathLengthM         float64                `mapstructure:"min_path_length_m"`
	MinAcceptedGoals       int                    `mapstructure:"min_accepted_goals"`
	MaxRecoveryCount       int                    `mapstructure:"max_recovery_count"`
	ReturnHomePolicy       string                 `mapstructure:"return_home_policy"`
	NavigationClaim        string                 `mapstructure:"navigation_claim"`
	UsesGazeboTruthAsInput bool                   `mapstructure:"uses_gazebo_truth_as_input"`
	ExitGoal               NavigationGoalConfig   `mapstructure:"exit_goal"`
	BoundedGoals           []NavigationGoalConfig `mapstructure:"bounded_goals"`
	HomeGoal               NavigationGoalConfig   `mapstructure:"home_goal"`
}

type NavigationGoalConfig struct {
	ID     string  `mapstructure:"id"`
	XM     float64 `mapstructure:"x_m"`
	YM     float64 `mapstructure:"y_m"`
	YawRad float64 `mapstructure:"yaw_rad"`
}

type ScanIntegrityGateConfig struct {
	RosbagProfile               string  `mapstructure:"rosbag_profile"`
	RawScanTopic                string  `mapstructure:"raw_scan_topic"`
	NormalizedScanTopic         string  `mapstructure:"normalized_scan_topic"`
	ValidatedScanTopic          string  `mapstructure:"validated_scan_topic"`
	StatusTopic                 string  `mapstructure:"status_topic"`
	EventsTopic                 string  `mapstructure:"events_topic"`
	FaultInjectionTopic         string  `mapstructure:"fault_injection_topic"`
	AttitudeSourceTopic         string  `mapstructure:"attitude_source_topic"`
	AttitudeSourceType          string  `mapstructure:"attitude_source_type"`
	RangefinderRangeTopic       string  `mapstructure:"rangefinder_range_topic"`
	IMUTopic                    string  `mapstructure:"imu_topic"`
	FCUPoseTopic                string  `mapstructure:"fcu_pose_topic"`
	ScanSourceTopic             string  `mapstructure:"scan_source_topic"`
	X2StatusTopic               string  `mapstructure:"x2_status_topic"`
	BaseFrameID                 string  `mapstructure:"base_frame_id"`
	ScanFrameID                 string  `mapstructure:"scan_frame_id"`
	SoftTiltDeg                 float64 `mapstructure:"soft_tilt_deg"`
	HardTiltDeg                 float64 `mapstructure:"hard_tilt_deg"`
	MaxDroppedScanRatio         float64 `mapstructure:"max_dropped_scan_ratio"`
	MaxClippedBeamRatio         float64 `mapstructure:"max_clipped_beam_ratio"`
	MaxScanAttitudeTimeOffsetMS float64 `mapstructure:"max_scan_attitude_time_offset_ms"`
	MaxAttitudeSourceAgeMS      float64 `mapstructure:"max_attitude_source_age_ms"`
	MinAttitudeRateHz           float64 `mapstructure:"min_attitude_rate_hz"`
	FloorHitGuardRangeM         float64 `mapstructure:"floor_hit_guard_range_m"`
	MinLidarHeightM             float64 `mapstructure:"min_lidar_height_m"`
	MinDownwardRayZ             float64 `mapstructure:"min_downward_ray_z"`
	MildFaultRollBiasDeg        float64 `mapstructure:"mild_fault_roll_bias_deg"`
	MildFaultPitchBiasDeg       float64 `mapstructure:"mild_fault_pitch_bias_deg"`
	HardFaultRollBiasDeg        float64 `mapstructure:"hard_fault_roll_bias_deg"`
	HardFaultPitchBiasDeg       float64 `mapstructure:"hard_fault_pitch_bias_deg"`
	NormalWindowSec             float64 `mapstructure:"normal_window_sec"`
	FaultWindowSec              float64 `mapstructure:"fault_window_sec"`
	UsesGazeboTruthAsInput      bool    `mapstructure:"uses_gazebo_truth_as_input"`
	HoverClaim                  string  `mapstructure:"hover_claim"`
	MotionClaim                 string  `mapstructure:"motion_claim"`
	ExplorationClaim            string  `mapstructure:"exploration_claim"`
	ScanIntegrityClaim          string  `mapstructure:"scan_integrity_claim"`
}

type ScanStabilizationConfig struct {
	Enabled                     bool    `mapstructure:"enabled"`
	Mode                        string  `mapstructure:"mode"`
	InputScanTopic              string  `mapstructure:"input_scan_topic"`
	OutputScanTopic             string  `mapstructure:"output_scan_topic"`
	StatusTopic                 string  `mapstructure:"status_topic"`
	EventsTopic                 string  `mapstructure:"events_topic"`
	DebugScanTopic              string  `mapstructure:"debug_scan_topic"`
	FaultInjectionTopic         string  `mapstructure:"fault_injection_topic"`
	AttitudeSourceTopic         string  `mapstructure:"attitude_source_topic"`
	AttitudeSourceType          string  `mapstructure:"attitude_source_type"`
	RangeTopic                  string  `mapstructure:"range_topic"`
	BaseFrameID                 string  `mapstructure:"base_frame_id"`
	ScanFrameID                 string  `mapstructure:"scan_frame_id"`
	PassthroughTiltDeg          float64 `mapstructure:"passthrough_tilt_deg"`
	CompensationTiltDeg         float64 `mapstructure:"compensation_tilt_deg"`
	HardDropTiltDeg             float64 `mapstructure:"hard_drop_tilt_deg"`
	MaxVerticalProjectionErrorM float64 `mapstructure:"max_vertical_projection_error_m"`
	MaxRejectedBeamRatio        float64 `mapstructure:"max_rejected_beam_ratio"`
	MinRetainedBeamRatio        float64 `mapstructure:"min_retained_beam_ratio"`
	MaxFloorHitRiskBeamRatio    float64 `mapstructure:"max_floor_hit_risk_beam_ratio"`
	FloorHitGuardRangeM         float64 `mapstructure:"floor_hit_guard_range_m"`
	MinLidarHeightM             float64 `mapstructure:"min_lidar_height_m"`
	MinDownwardRayZ             float64 `mapstructure:"min_downward_ray_z"`
	MaxScanAttitudeTimeOffsetMS float64 `mapstructure:"max_scan_attitude_time_offset_ms"`
	MaxAttitudeSourceAgeMS      float64 `mapstructure:"max_attitude_source_age_ms"`
	MinAttitudeRateHz           float64 `mapstructure:"min_attitude_rate_hz"`
	MinStabilizedScanRateHz     float64 `mapstructure:"min_stabilized_scan_rate_hz"`
	PublishDebugScan            bool    `mapstructure:"publish_debug_scan"`
	UsesGazeboTruthAsInput      bool    `mapstructure:"uses_gazebo_truth_as_input"`
	ScanStabilizationClaim      string  `mapstructure:"scan_stabilization_claim"`
}

type ScanStabilizationGateConfig struct {
	RosbagProfile               string  `mapstructure:"rosbag_profile"`
	MotionProfile               string  `mapstructure:"motion_profile"`
	BaselineMode                string  `mapstructure:"baseline_mode"`
	CandidateMode               string  `mapstructure:"candidate_mode"`
	RawScanTopic                string  `mapstructure:"raw_scan_topic"`
	NormalizedScanTopic         string  `mapstructure:"normalized_scan_topic"`
	ValidatedScanTopic          string  `mapstructure:"validated_scan_topic"`
	ScanSourceTopic             string  `mapstructure:"scan_source_topic"`
	X2StatusTopic               string  `mapstructure:"x2_status_topic"`
	IMUTopic                    string  `mapstructure:"imu_topic"`
	FCUPoseTopic                string  `mapstructure:"fcu_pose_topic"`
	UsesOfficialMazeAsInput     bool    `mapstructure:"uses_official_maze_as_input"`
	OfficialMazeLayerRole       string  `mapstructure:"official_maze_layer_role"`
	HoverClaim                  string  `mapstructure:"hover_claim"`
	MotionClaim                 string  `mapstructure:"motion_claim"`
	ExplorationClaim            string  `mapstructure:"exploration_claim"`
	ScanStabilizationClaim      string  `mapstructure:"scan_stabilization_claim"`
	ReplayReadinessTimeoutSec   float64 `mapstructure:"replay_readiness_timeout_sec"`
	ControllerSummaryTimeoutSec float64 `mapstructure:"controller_summary_timeout_sec"`
}

type AirframeDisturbanceConfig struct {
	Enabled                     bool      `mapstructure:"enabled"`
	Profile                     string    `mapstructure:"profile"`
	InjectionLayer              string    `mapstructure:"injection_layer"`
	Seed                        int       `mapstructure:"seed"`
	MotorCount                  int       `mapstructure:"motor_count"`
	ThrustMultipliers           []float64 `mapstructure:"thrust_multipliers"`
	MaxAbsThrustMultiplierDelta float64   `mapstructure:"max_abs_thrust_multiplier_delta"`
	ESCLagMS                    []float64 `mapstructure:"esc_lag_ms"`
	ESCLagModel                 string    `mapstructure:"esc_lag_model"`
	MaxESCLagMS                 float64   `mapstructure:"max_esc_lag_ms"`
	ThrustNoiseStd              float64   `mapstructure:"thrust_noise_std"`
	ThrustNoiseCorrelationMS    float64   `mapstructure:"thrust_noise_correlation_ms"`
	MotorJitterHz               float64   `mapstructure:"motor_jitter_hz"`
	IMUVibrationEnabled         bool      `mapstructure:"imu_vibration_enabled"`
	IMUInputTopic               string    `mapstructure:"imu_input_topic"`
	IMUOutputTopic              string    `mapstructure:"imu_output_topic"`
	IMUGyroNoiseStdDPS          float64   `mapstructure:"imu_gyro_noise_std_dps"`
	IMUAccelNoiseStdMPS2        float64   `mapstructure:"imu_accel_noise_std_mps2"`
	IMUVibrationFreqHz          float64   `mapstructure:"imu_vibration_freq_hz"`
	IMUVibrationRollPitchAmpDeg float64   `mapstructure:"imu_vibration_roll_pitch_amp_deg"`
	StatusTopic                 string    `mapstructure:"status_topic"`
	EventsTopic                 string    `mapstructure:"events_topic"`
}

type AirframeDisturbanceGateConfig struct {
	RosbagProfile              string   `mapstructure:"rosbag_profile"`
	MotionProfile              string   `mapstructure:"motion_profile"`
	ScanContract               string   `mapstructure:"scan_contract"`
	ProfileSet                 []string `mapstructure:"profile_set"`
	RequiredProfiles           []string `mapstructure:"required_profiles"`
	FaultProfiles              []string `mapstructure:"fault_profiles"`
	AllowHardProfileFail       bool     `mapstructure:"allow_hard_profile_fail"`
	MaxAbsRollDeg              float64  `mapstructure:"max_abs_roll_deg"`
	MaxAbsPitchDeg             float64  `mapstructure:"max_abs_pitch_deg"`
	MaxRMSRollDeg              float64  `mapstructure:"max_rms_roll_deg"`
	MaxRMSPitchDeg             float64  `mapstructure:"max_rms_pitch_deg"`
	MaxAttitudeRateDPS         float64  `mapstructure:"max_attitude_rate_dps"`
	MaxScanDropRatio           float64  `mapstructure:"max_scan_drop_ratio"`
	MaxScanCompensatedRatio    float64  `mapstructure:"max_scan_compensated_ratio"`
	MaxFloorHitRejectedRatio   float64  `mapstructure:"max_floor_hit_rejected_ratio"`
	MinStabilizedScanRateHz    float64  `mapstructure:"min_stabilized_scan_rate_hz"`
	MinSlamOdomRateHz          float64  `mapstructure:"min_slam_odom_rate_hz"`
	MaxMapArtifactScore        float64  `mapstructure:"max_map_artifact_score"`
	MaxExternalNavDropoutRatio float64  `mapstructure:"max_external_nav_dropout_ratio"`
	UsesOfficialMazeAsInput    bool     `mapstructure:"uses_official_maze_as_input"`
	OfficialMazeLayerRole      string   `mapstructure:"official_maze_layer_role"`
	FCUStatusTopic             string   `mapstructure:"fcu_status_topic"`
	FCUStatusModeField         string   `mapstructure:"fcu_status_mode_field"`
	FCUModeWindowTopic         string   `mapstructure:"fcu_mode_window_topic"`
	RequiredFCUModeName        string   `mapstructure:"required_fcu_mode_name"`
	RequiredFCUModeNumber      int      `mapstructure:"required_fcu_mode_number"`
	AirframeDisturbanceClaim   string   `mapstructure:"airframe_disturbance_claim"`
	HorizontalRecoveryClaim    string   `mapstructure:"horizontal_recovery_claim"`
}

type TaskConfig struct {
	ID           string         `mapstructure:"id"`
	Family       string         `mapstructure:"family"`
	Description  string         `mapstructure:"description"`
	Capabilities []string       `mapstructure:"capabilities"`
	Task         TaskParameters `mapstructure:"task"`
	Sections     map[string]any `mapstructure:",remain"`
}

type TaskParameters struct {
	DurationSec       float64 `mapstructure:"duration_sec"`
	TimeoutSec        float64 `mapstructure:"timeout_sec"`
	SimulationProfile string  `mapstructure:"simulation_profile"`
}
