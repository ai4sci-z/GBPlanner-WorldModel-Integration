package helpers

import (
	"encoding/json"
	"os"
	"path/filepath"

	toml "github.com/pelletier/go-toml/v2"
)

const (
	OfficialIrisWithLidarModel       = "/opt/navlab_official_ws/install/ardupilot_gz_description/share/ardupilot_gz_description/models/iris_with_lidar/model.sdf"
	OfficialGazeboIrisParams         = "/opt/navlab_official_ws/install/ardupilot_sitl/share/ardupilot_sitl/config/default_params/gazebo-iris.parm"
	FCUControllerContainer           = "navlab-fcu-controller"
	MAVLinkExternalNavContainer      = "navlab-mavlink-external-nav"
	FCURosbagContainer               = "navlab-fcu-rosbag"
	FrameContractRosbagContainer     = "navlab-frame-contract-rosbag"
	HoverRosbagContainer             = "navlab-hover-rosbag"
	HoverVehicleMarkerContainer      = "navlab-hover-vehicle-markers"
	ScanStabilizationRosbagContainer = "navlab-scan-stabilization-rosbag"
	ExplorationRosbagContainer       = "navlab-exploration-rosbag"
)

type SensorRuntimeSpec struct {
	RuntimeConfigPath         string
	X2VirtualSerialLink       string
	X2ScanInputTopic          string
	X2ScanTopic               string
	X2StatusTopic             string
	RangefinderFrameID        string
	RangefinderScanIdealTopic string
	RangefinderRangeTopic     string
	RangefinderStatusTopic    string
	RangefinderVirtualSerial  string
	RangefinderSerialBaud     int
	RangefinderRateHz         float64
	RangefinderMinDistanceM   float64
	RangefinderMaxDistanceM   float64
	RangefinderModelPose      string
	RangefinderModelUpdateHz  float64
	RangefinderModelRayCount  int
	RangefinderModelNoiseM    float64
	IMUOutputTopic            string
	IMUSourceRoute            string
	IMUSourceTopic            string
	SyntheticFallbackEnabled  bool
}

type SlamOnlySpec struct {
	ScanTopic              string
	IMUTopic               string
	SlamOdomTopic          string
	SlamStatusTopic        string
	ExternalNavStatusTopic string
	TFTopic                string
	TFStaticTopic          string
	MinOdomRateHz          float64
	MaxOdomStaleSec        float64
	MaxPositionJumpM       float64
	ProbeDurationSec       float64
	MinProbeDurationSec    float64
}

func DefaultSlamOnlySpec() SlamOnlySpec {
	slam := DefaultSlamRuntimeSpec()
	return SlamOnlySpec{
		ScanTopic:              slam.ScanTopic,
		IMUTopic:               "/navlab/slam/imu",
		SlamOdomTopic:          slam.SlamOdomTopic,
		SlamStatusTopic:        slam.SlamStatusTopic,
		ExternalNavStatusTopic: slam.ExternalNavStatusTopic,
		TFTopic:                "/tf",
		TFStaticTopic:          "/tf_static",
		MinOdomRateHz:          4.0,
		MaxOdomStaleSec:        1.0,
		MaxPositionJumpM:       1.0,
		ProbeDurationSec:       25.0,
		MinProbeDurationSec:    8.0,
	}
}

func (spec SlamOnlySpec) RequiredTopics() []string {
	return []string{spec.ScanTopic, spec.IMUTopic, spec.SlamOdomTopic, spec.SlamStatusTopic}
}

func (spec SlamOnlySpec) RosbagTopics() []string {
	return appendUniqueTopics([]string{
		spec.TFTopic,
		spec.TFStaticTopic,
		spec.ScanTopic,
		"/lidar",
		"/imu",
		spec.IMUTopic,
		spec.SlamOdomTopic,
		spec.SlamStatusTopic,
		spec.ExternalNavStatusTopic,
		"/map",
		"/sim/x2/status",
	}, spec.RequiredTopics()...)
}

func DefaultSensorRuntimeSpec() SensorRuntimeSpec {
	return SensorRuntimeSpec{
		RuntimeConfigPath:         "artifacts/runtime/config/gazebo_sensor_runtime.toml",
		X2VirtualSerialLink:       "/tmp/navlab_sim_x2",
		X2ScanInputTopic:          "/lidar",
		X2ScanTopic:               "/scan",
		X2StatusTopic:             "/sim/x2/status",
		RangefinderFrameID:        "rangefinder_down_frame",
		RangefinderScanIdealTopic: "/rangefinder/down/scan_ideal",
		RangefinderRangeTopic:     "/rangefinder/down/range",
		RangefinderStatusTopic:    "/rangefinder/down/status",
		RangefinderVirtualSerial:  "/tmp/navlab_benewake_tfmini",
		RangefinderSerialBaud:     115200,
		RangefinderRateHz:         20.0,
		RangefinderMinDistanceM:   0.05,
		RangefinderMaxDistanceM:   6.0,
		RangefinderModelPose:      "0 0 -0.02 0 1.5707963267948966 0",
		RangefinderModelUpdateHz:  20.0,
		RangefinderModelRayCount:  1,
		RangefinderModelNoiseM:    0.0,
		IMUOutputTopic:            "/imu",
		IMUSourceRoute:            "official_gazebo_imu_bridge",
		IMUSourceTopic:            "/imu",
		SyntheticFallbackEnabled:  false,
	}
}

func WriteSensorRuntimeConfig(path string, vendorProfile string, spec SensorRuntimeSpec) error {
	if spec.RuntimeConfigPath == "" {
		spec = DefaultSensorRuntimeSpec()
	}
	data := map[string]any{
		"gazebo_sensor": map[string]any{
			"x2_protocol": map[string]any{
				"enabled":               true,
				"scan_source":           "x2_virtual_serial",
				"profile":               vendorProfile,
				"virtual_serial_link":   spec.X2VirtualSerialLink,
				"scan_ideal_topic":      spec.X2ScanInputTopic,
				"vendor_scan_topic":     "/navlab/x2/vendor_scan",
				"scan_topic":            spec.X2ScanTopic,
				"status_topic":          spec.X2StatusTopic,
				"sample_rate_hz":        3000.0,
				"scan_frequency_hz":     7.0,
				"scan_frequency_min_hz": 7.0,
				"scan_frequency_max_hz": 7.0,
				"static_range_m":        1.5,
				"range_min_m":           0.1,
				"range_max_m":           8.0,
				"auto_start":            true,
			},
			"down_rangefinder": map[string]any{
				"enabled":              true,
				"scan_ideal_topic":     spec.RangefinderScanIdealTopic,
				"range_topic":          spec.RangefinderRangeTopic,
				"status_topic":         spec.RangefinderStatusTopic,
				"virtual_serial_link":  spec.RangefinderVirtualSerial,
				"serial_baud":          spec.RangefinderSerialBaud,
				"frame_id":             spec.RangefinderFrameID,
				"rate_hz":              spec.RangefinderRateHz,
				"min_distance_m":       spec.RangefinderMinDistanceM,
				"max_distance_m":       spec.RangefinderMaxDistanceM,
				"model_pose":           spec.RangefinderModelPose,
				"model_update_rate_hz": spec.RangefinderModelUpdateHz,
				"model_ray_count":      spec.RangefinderModelRayCount,
				"model_noise_stddev_m": spec.RangefinderModelNoiseM,
			},
		},
	}
	return writeTOML(path, data)
}

func RangefinderProbeScript(spec SensorRuntimeSpec) (string, error) {
	if spec.RuntimeConfigPath == "" {
		spec = DefaultSensorRuntimeSpec()
	}
	return rosProbeScript("navlab_rangefinder_probe", []string{spec.RangefinderRangeTopic, spec.RangefinderStatusTopic}, map[string]any{
		"probe_timeout_sec": 45.0,
		"range_topic":       spec.RangefinderRangeTopic,
		"status_topic":      spec.RangefinderStatusTopic,
	})
}

func StartupReadinessProbeScript(spec SlamHoverSpec) (string, error) {
	if spec.SlamOdomTopic == "" {
		spec = DefaultSlamHoverSpec()
	}
	return rosProbeScriptWithOptionalTopics(
		"navlab_startup_readiness_probe",
		[]string{
			spec.RangefinderRangeTopic,
			spec.RangefinderStatusTopic,
			"/height/estimate",
			"/height/status",
			spec.ExternalNavStatusTopic,
		},
		nil,
		map[string]any{"probe_timeout_sec": 5.0},
	)
}

func IMUProbeScript(spec SensorRuntimeSpec) (string, error) {
	if spec.RuntimeConfigPath == "" {
		spec = DefaultSensorRuntimeSpec()
	}
	return rosProbeScript("navlab_imu_probe", []string{spec.IMUOutputTopic}, map[string]any{
		"topic":                      spec.IMUOutputTopic,
		"source_route":               spec.IMUSourceRoute,
		"source_topic":               spec.IMUSourceTopic,
		"synthetic_fallback_enabled": spec.SyntheticFallbackEnabled,
	})
}

type FCUControllerSpec struct {
	ControlRoute                    string
	MAVLinkBootstrap                string
	MAVLinkBootstrapSourceSystem    int
	MAVLinkBootstrapSourceComponent int
	OwnerName                       string
	OwnerID                         string
	FCUStateTopic                   string
	ControllerStatusTopic           string
	SetpointIntentTopic             string
	SetpointOutputTopic             string
	OwnerStatusTopic                string
	TimeTopic                       string
	PrearmService                   string
	ModeSwitchService               string
	ArmService                      string
	TakeoffService                  string
	CmdVelTopic                     string
	PoseTopic                       string
	TwistTopic                      string
	StatusTopic                     string
	RangefinderRangeTopic           string
	RangefinderStatusTopic          string
	IMUTopic                        string
	IMUInputTopic                   string
	ScanInputTopic                  string
	ScanOutputTopic                 string
	ScanStabilizationTopic          string
	DisturbanceStatusTopic          string
	ExplorationStatusTopic          string
	TaskCompletionStatusTopic       string
	SlamOdomTopic                   string
	CartographerOdometryTopic       string
	SlamStatusTopic                 string
	MapFrameID                      string
	OdomFrameID                     string
	BaseFrameID                     string
	LaserFrameID                    string
	LandingPolicy                   string
	CompletionGraceSec              float64
	MotionSpeedMPS                  float64
	MinAcceptedGoals                int
	MinPathLengthM                  float64
	DisturbanceProfile              string
	RequiredProfiles                []string
	ESCLagMS                        []float64
	MotorJitterHz                   float64
	ThrustNoiseStd                  float64
	IMUVibrationEnabled             bool
	IMUVibrationRollPitchAmpDeg     float64
	GuidedMode                      string
	TakeoffAltM                     float64
	TakeoffMinHeightM               float64
	TakeoffMinHeightRatio           float64
	ReadinessTimeoutSec             float64
	HoldAfterReadySec               float64
	RequireSlamBackend              bool
	DisableArmingChecks             bool
	ForceArm                        bool
}

func DefaultFCUControllerSpec() FCUControllerSpec {
	return FCUControllerSpec{
		ControlRoute:                    "mavlink_bootstrap_plus_dds_cmd_vel",
		MAVLinkBootstrap:                "udpin:0.0.0.0:14551",
		MAVLinkBootstrapSourceSystem:    246,
		MAVLinkBootstrapSourceComponent: 190,
		OwnerName:                       "navlab_fcu_controller",
		OwnerID:                         "fcu-controller",
		FCUStateTopic:                   "/navlab/fcu/state",
		ControllerStatusTopic:           "/navlab/fcu/controller/status",
		SetpointIntentTopic:             "/navlab/fcu/setpoint/intent",
		SetpointOutputTopic:             "/navlab/fcu/setpoint/output",
		OwnerStatusTopic:                "/navlab/fcu/owner/status",
		TimeTopic:                       "/ap/v1/time",
		PrearmService:                   "/ap/v1/prearm_check",
		ModeSwitchService:               "/ap/v1/mode_switch",
		ArmService:                      "/ap/v1/arm_motors",
		TakeoffService:                  "/ap/v1/experimental/takeoff",
		CmdVelTopic:                     "/ap/v1/cmd_vel",
		PoseTopic:                       "/ap/v1/pose/filtered",
		TwistTopic:                      "/ap/v1/twist/filtered",
		StatusTopic:                     "/ap/v1/status",
		RangefinderRangeTopic:           "/rangefinder/down/range",
		RangefinderStatusTopic:          "/rangefinder/down/status",
		IMUTopic:                        "/imu",
		IMUInputTopic:                   "",
		ScanInputTopic:                  "",
		ScanOutputTopic:                 "",
		ScanStabilizationTopic:          "",
		DisturbanceStatusTopic:          "",
		ExplorationStatusTopic:          "",
		TaskCompletionStatusTopic:       "",
		SlamOdomTopic:                   "/slam/odom",
		CartographerOdometryTopic:       "",
		SlamStatusTopic:                 "/navlab/slam/status",
		MapFrameID:                      "map",
		OdomFrameID:                     "odom",
		BaseFrameID:                     "base_link",
		LaserFrameID:                    "base_scan",
		LandingPolicy:                   "land_in_place",
		CompletionGraceSec:              3.0,
		MotionSpeedMPS:                  0.0,
		MinAcceptedGoals:                0,
		MinPathLengthM:                  0.0,
		DisturbanceProfile:              "realistic",
		RequiredProfiles:                nil,
		ESCLagMS:                        nil,
		MotorJitterHz:                   0.0,
		ThrustNoiseStd:                  0.0,
		IMUVibrationEnabled:             false,
		IMUVibrationRollPitchAmpDeg:     0.0,
		GuidedMode:                      "GUIDED",
		TakeoffAltM:                     0.5,
		TakeoffMinHeightM:               0.15,
		TakeoffMinHeightRatio:           0.35,
		ReadinessTimeoutSec:             45.0,
		HoldAfterReadySec:               8.0,
		RequireSlamBackend:              true,
		DisableArmingChecks:             true,
		ForceArm:                        true,
	}
}

func WriteFCUControllerRuntimeConfig(path string, spec FCUControllerSpec) error {
	if spec.ControlRoute == "" {
		spec = DefaultFCUControllerSpec()
	}
	return writeTOML(path, map[string]any{"fcu_controller": map[string]any{"runtime": spec}})
}

func FCUControllerRuntimeScript(spec FCUControllerSpec, durationSec float64) (string, error) {
	if spec.ControlRoute == "" {
		spec = DefaultFCUControllerSpec()
	}
	payload := map[string]any{
		"duration_sec":                       durationSec,
		"control_route":                      spec.ControlRoute,
		"mavlink_bootstrap_endpoint":         spec.MAVLinkBootstrap,
		"mavlink_bootstrap_source_system":    spec.MAVLinkBootstrapSourceSystem,
		"mavlink_bootstrap_source_component": spec.MAVLinkBootstrapSourceComponent,
		"pose_topic":                         spec.PoseTopic,
		"controller_status_topic":            spec.ControllerStatusTopic,
		"setpoint_intent_topic":              spec.SetpointIntentTopic,
		"setpoint_output_topic":              spec.SetpointOutputTopic,
		"owner_status_topic":                 spec.OwnerStatusTopic,
		"fcu_state_topic":                    spec.FCUStateTopic,
		"cmd_vel_topic":                      spec.CmdVelTopic,
		"prearm_service":                     spec.PrearmService,
		"mode_switch_service":                spec.ModeSwitchService,
		"arm_service":                        spec.ArmService,
		"takeoff_service":                    spec.TakeoffService,
		"takeoff_alt_m":                      spec.TakeoffAltM,
		"takeoff_min_height_m":               spec.TakeoffMinHeightM,
		"takeoff_min_height_ratio":           spec.TakeoffMinHeightRatio,
		"guided_mode":                        spec.GuidedMode,
		"readiness_timeout_sec":              spec.ReadinessTimeoutSec,
		"hold_after_ready_sec":               spec.HoldAfterReadySec,
		"require_slam_backend":               spec.RequireSlamBackend,
		"disable_arming_checks":              spec.DisableArmingChecks,
		"force_arm":                          spec.ForceArm,
		"rangefinder_range_topic":            spec.RangefinderRangeTopic,
		"rangefinder_status_topic":           spec.RangefinderStatusTopic,
		"imu_input_topic":                    spec.IMUInputTopic,
		"imu_output_topic":                   spec.IMUTopic,
		"scan_input_topic":                   spec.ScanInputTopic,
		"scan_output_topic":                  spec.ScanOutputTopic,
		"scan_stabilization_topic":           spec.ScanStabilizationTopic,
		"disturbance_status_topic":           spec.DisturbanceStatusTopic,
		"exploration_status_topic":           spec.ExplorationStatusTopic,
		"task_completion_status_topic":       spec.TaskCompletionStatusTopic,
		"slam_odom_topic":                    spec.SlamOdomTopic,
		"cartographer_odometry_topic":        spec.CartographerOdometryTopic,
		"slam_status_topic":                  spec.SlamStatusTopic,
		"map_frame_id":                       spec.MapFrameID,
		"odom_frame_id":                      spec.OdomFrameID,
		"base_frame_id":                      spec.BaseFrameID,
		"laser_frame_id":                     spec.LaserFrameID,
		"hover_status_topic":                 "/navlab/hover/status",
		"landing_status_topic":               "/navlab/landing/status",
		"landing_policy":                     spec.LandingPolicy,
		"completion_grace_sec":               spec.CompletionGraceSec,
		"motion_speed_mps":                   spec.MotionSpeedMPS,
		"min_accepted_goals":                 spec.MinAcceptedGoals,
		"min_path_length_m":                  spec.MinPathLengthM,
		"disturbance_profile":                spec.DisturbanceProfile,
		"required_profiles":                  append([]string(nil), spec.RequiredProfiles...),
		"esc_lag_ms":                         append([]float64(nil), spec.ESCLagMS...),
		"motor_jitter_hz":                    spec.MotorJitterHz,
		"thrust_noise_std":                   spec.ThrustNoiseStd,
		"imu_vibration_enabled":              spec.IMUVibrationEnabled,
		"imu_vibration_roll_pitch_amp_deg":   spec.IMUVibrationRollPitchAmpDeg,
	}
	return fcuControllerRuntimeScript(payload)
}

type FrameContractSpec struct {
	RequiredFrames          []string
	MapFrameID              string
	OdomFrameID             string
	BaseFrameID             string
	IMUFrameID              string
	LaserFrameID            string
	RangefinderFrameID      string
	ScanTopic               string
	IMUTopic                string
	RangefinderRangeTopic   string
	RangefinderStatusTopic  string
	FCUPoseTopic            string
	FCUTwistTopic           string
	FCUStatusTopic          string
	CmdVelTopic             string
	SlamOdomTopic           string
	SlamStatusTopic         string
	TruthDiagnosticTopic    string
	ControllerStatusTopic   string
	SetpointOutputTopic     string
	OwnerStatusTopic        string
	StatusTopic             string
	MaxDynamicTFAgeSec      float64
	MinScanValidRatio       float64
	MaxRangefinderHeightErr float64
	MaxDirectionErrorRad    float64
	ProbeDurationSec        float64
}

func DefaultFrameContractSpec() FrameContractSpec {
	return FrameContractSpec{
		RequiredFrames:          []string{"map", "odom", "base_link", "imu_link", "base_scan", "rangefinder_down_frame"},
		MapFrameID:              "map",
		OdomFrameID:             "odom",
		BaseFrameID:             "base_link",
		IMUFrameID:              "imu_link",
		LaserFrameID:            "base_scan",
		RangefinderFrameID:      "rangefinder_down_frame",
		ScanTopic:               "/scan",
		IMUTopic:                "/imu",
		RangefinderRangeTopic:   "/rangefinder/down/range",
		RangefinderStatusTopic:  "/rangefinder/down/status",
		FCUPoseTopic:            "/ap/v1/pose/filtered",
		FCUTwistTopic:           "/ap/v1/twist/filtered",
		FCUStatusTopic:          "/ap/v1/status",
		CmdVelTopic:             "/ap/v1/cmd_vel",
		SlamOdomTopic:           "/slam/odom",
		SlamStatusTopic:         "/navlab/slam/status",
		TruthDiagnosticTopic:    "/odometry",
		ControllerStatusTopic:   "/navlab/fcu/controller/status",
		SetpointOutputTopic:     "/navlab/fcu/setpoint/output",
		OwnerStatusTopic:        "/navlab/fcu/owner/status",
		StatusTopic:             "/navlab/frame_contract/status",
		MaxDynamicTFAgeSec:      1.0,
		MinScanValidRatio:       0.8,
		MaxRangefinderHeightErr: 0.25,
		MaxDirectionErrorRad:    0.35,
		ProbeDurationSec:        12.0,
	}
}

func WriteFrameContractRuntimeConfig(path string, spec FrameContractSpec) error {
	if spec.MapFrameID == "" {
		spec = DefaultFrameContractSpec()
	}
	return writeTOML(path, map[string]any{"frame_contract": map[string]any{"runtime": spec}})
}

func FrameContractProbeScript(spec FrameContractSpec) (string, error) {
	if spec.MapFrameID == "" {
		spec = DefaultFrameContractSpec()
	}
	return rosProbeScript("navlab_frame_contract_probe", []string{"/tf", "/tf_static", spec.ScanTopic, spec.IMUTopic, spec.RangefinderRangeTopic, spec.FCUPoseTopic, spec.SlamOdomTopic, spec.SlamStatusTopic}, spec)
}

type SlamHoverSpec struct {
	SlamOdomTopic                     string
	SlamStatusTopic                   string
	ExternalNavStatusTopic            string
	ScanReferenceOdomTopic            string
	ScanReferenceStatusTopic          string
	FCUPoseTopic                      string
	FCUTwistTopic                     string
	FCUStatusTopic                    string
	CmdVelTopic                       string
	RangefinderRangeTopic             string
	RangefinderStatusTopic            string
	IMUTopic                          string
	TruthDiagnosticTopic              string
	ControllerStatusTopic             string
	SetpointIntentTopic               string
	SetpointOutputTopic               string
	OwnerStatusTopic                  string
	HoverStatusTopic                  string
	VehicleMarkerTopic                string
	VehicleMarkerPoseTopic            string
	VehicleMarkerFrameID              string
	VehicleMarkerRateHz               float64
	SettleWindowSec                   float64
	HoverWindowSec                    float64
	FinalHoldWindowSec                float64
	MaxHoverHorizontalDrift           float64
	HoverSpanTargetM                  float64
	HoverSpanHardCapM                 float64
	MaxHoverAltitudeError             float64
	MaxHoverYawDriftRad               float64
	MaxStopDriftM                     float64
	StartupReadinessTimeoutSec        float64
	StartupReadinessGraceSec          float64
	StartupReadinessProgressWindowSec float64
	StartupReadinessRestartLimit      int
	ProbeTimeoutSec                   float64
}

type ScanReferenceDriftSpec struct {
	ScanTopic                                    string
	HoverStatusTopic                             string
	OdomTopic                                    string
	StatusTopic                                  string
	FrameID                                      string
	ChildFrameID                                 string
	MinValidBeams                                int
	MaxResidualRMSM                              float64
	MaxRangeDeltaM                               float64
	MaxHorizontalDriftM                          float64
	MaxInlierResidualM                           float64
	MinInlierRatio                               float64
	RobustIterations                             int
	YawSearchWindowRad                           float64
	YawSearchSteps                               int
	EligibilityWindowSamples                     int
	MinStableSamples                             int
	MinAxisDriftM                                float64
	AxisDeadbandM                                float64
	MaxAxisSignFlips                             int
	MaxVelocityMPS                               float64
	MinDirectionCosine                           float64
	MaxPhase4BSaturationRatio                    float64
	MinCorrectionIntentConsecutiveAllowedSamples int
	MaxCorrectionIntentM                         float64
	CorrectionIntentGain                         float64
	ResetOnHoverHold                             bool
}

type ScanReferenceCorrectionSpec struct {
	SlamOdomTopic                string
	ScanReferenceStatusTopic     string
	HoverStatusTopic             string
	OutputOdomTopic              string
	StatusTopic                  string
	ExpectedFrameID              string
	ExpectedChildFrameID         string
	MaxStatusAgeMS               float64
	MaxCorrectionM               float64
	MaxMeasurementDeltaM         float64
	MaxCorrectionStepM           float64
	MinRuntimeConsistencySamples int
	MinDirectionCosine           float64
	MaxAxisSignFlips             int
	MaxSaturationRatio           float64
	HistorySamples               int
	EnableCorrection             bool
}

type ExternalNavSourceSelectorSpec struct {
	SlamOdomTopic             string
	ScanReferenceOdomTopic    string
	ScanReferenceStatusTopic  string
	HoverStatusTopic          string
	OutputOdomTopic           string
	StatusTopic               string
	MaxStatusAgeMS            float64
	CartographerDisagreementM float64
}

type HoverMissionRuntimeSpec struct {
	Endpoint                          string
	SourceSystem                      int
	SourceComponent                   int
	Mode                              string
	TakeoffAltM                       float64
	MinAirborneAltM                   float64
	PreflightReadySec                 float64
	MaxWaitReadySec                   float64
	HoverSettleSec                    float64
	HoverAltitudeToleranceM           float64
	HoverHoldSec                      float64
	HoverHealthMinObservationSec      float64
	HoverHealthStableRequiredSec      float64
	HoverHealthMaxWaitSec             float64
	StartupReadinessTimeoutSec        float64
	StartupReadinessGraceSec          float64
	StartupReadinessProgressWindowSec float64
	StartupReadinessRestartLimit      int
	OperatorConfirmRequired           bool
	OperatorConfirmTimeoutSec         float64
	MaxHorizontalDriftM               float64
	HoverSpanTargetM                  float64
	HoverSpanHardCapM                 float64
	MaxAltitudeDriftM                 float64
	StatusTopic                       string
	LandingStatusTopic                string
	LandingIntentTopic                string
	ExternalNavStatusTopic            string
	MAVLinkExternalNavStatusTopic     string
	IMUStatusTopic                    string
	MAVLinkStatusTopic                string
	PreLandHoldSec                    float64
	LandingPolicy                     string
	MaxLandingDurationSec             float64
	LandingDescentRateMPS             float64
	LandingLandCommandAltitudeM       float64
	LandingSetpointLookaheadSec       float64
	MaxLandingDescentRateMPS          float64
	TouchdownAltitudeM                float64
	TouchdownVerticalSpeedMPS         float64
	ForceDisarmGraceSec               float64
	RequireDisarm                     bool
	RequireMotorsSafe                 bool
	RequireExternalNav                bool
	RequireIMUStatus                  bool
	DisableArmingChecks               bool
	ForceArm                          bool
}

func DefaultSlamHoverSpec() SlamHoverSpec {
	return SlamHoverSpec{
		SlamOdomTopic:                     "/slam/odom",
		SlamStatusTopic:                   "/navlab/slam/status",
		ExternalNavStatusTopic:            "/external_nav/status",
		ScanReferenceOdomTopic:            "/navlab/scan_reference_drift/odom",
		ScanReferenceStatusTopic:          "/navlab/scan_reference_drift/status",
		FCUPoseTopic:                      "/ap/v1/pose/filtered",
		FCUTwistTopic:                     "/ap/v1/twist/filtered",
		FCUStatusTopic:                    "/ap/v1/status",
		CmdVelTopic:                       "/ap/v1/cmd_vel",
		RangefinderRangeTopic:             "/rangefinder/down/range",
		RangefinderStatusTopic:            "/rangefinder/down/status",
		IMUTopic:                          "/navlab/slam/imu",
		TruthDiagnosticTopic:              "/odometry",
		ControllerStatusTopic:             "/navlab/fcu/controller/status",
		SetpointIntentTopic:               "/navlab/fcu/setpoint/intent",
		SetpointOutputTopic:               "/navlab/fcu/setpoint/output",
		OwnerStatusTopic:                  "/navlab/fcu/owner/status",
		HoverStatusTopic:                  "/navlab/hover/status",
		VehicleMarkerTopic:                "/navlab/vehicle_marker",
		VehicleMarkerPoseTopic:            "/navlab/vehicle_marker/pose",
		VehicleMarkerFrameID:              "base_link",
		VehicleMarkerRateHz:               5.0,
		SettleWindowSec:                   8.0,
		HoverWindowSec:                    18.0,
		FinalHoldWindowSec:                5.0,
		MaxHoverHorizontalDrift:           0.10,
		HoverSpanTargetM:                  0.10,
		HoverSpanHardCapM:                 0.15,
		MaxHoverAltitudeError:             0.30,
		MaxHoverYawDriftRad:               0.35,
		MaxStopDriftM:                     0.20,
		StartupReadinessTimeoutSec:        35.0,
		StartupReadinessGraceSec:          8.0,
		StartupReadinessProgressWindowSec: 3.0,
		StartupReadinessRestartLimit:      0,
		ProbeTimeoutSec:                   120.0,
	}
}

func DefaultScanReferenceDriftSpec() ScanReferenceDriftSpec {
	return ScanReferenceDriftSpec{
		ScanTopic:                 "/scan",
		HoverStatusTopic:          "/navlab/hover/status",
		OdomTopic:                 "/navlab/scan_reference_drift/odom",
		StatusTopic:               "/navlab/scan_reference_drift/status",
		FrameID:                   "scan_reference",
		ChildFrameID:              "base_link",
		MinValidBeams:             80,
		MaxResidualRMSM:           0.30,
		MaxRangeDeltaM:            3.0,
		MaxHorizontalDriftM:       5.0,
		MaxInlierResidualM:        0.35,
		MinInlierRatio:            0.45,
		RobustIterations:          3,
		YawSearchWindowRad:        0.12,
		YawSearchSteps:            13,
		EligibilityWindowSamples:  8,
		MinStableSamples:          5,
		MinAxisDriftM:             0.03,
		AxisDeadbandM:             0.03,
		MaxAxisSignFlips:          0,
		MaxVelocityMPS:            0.75,
		MinDirectionCosine:        0.70,
		MaxPhase4BSaturationRatio: 0.95,
		MinCorrectionIntentConsecutiveAllowedSamples: 8,
		MaxCorrectionIntentM:                         0.25,
		CorrectionIntentGain:                         1.0,
		ResetOnHoverHold:                             true,
	}
}

func DefaultCartographerScanReferenceOdometrySpec() ScanReferenceDriftSpec {
	spec := DefaultScanReferenceDriftSpec()
	spec.OdomTopic = CartographerOdometryInputTopic
	spec.StatusTopic = "/navlab/scan_reference_cartographer_odom/status"
	spec.FrameID = "odom"
	spec.ResetOnHoverHold = false
	return spec
}

func DefaultScanReferenceCorrectionSpec() ScanReferenceCorrectionSpec {
	return ScanReferenceCorrectionSpec{
		SlamOdomTopic:                "/slam/odom",
		ScanReferenceStatusTopic:     "/navlab/scan_reference_drift/status",
		HoverStatusTopic:             "/navlab/hover/status",
		OutputOdomTopic:              "/slam/odom_corrected",
		StatusTopic:                  "/navlab/scan_reference_correction/status",
		ExpectedFrameID:              "map",
		ExpectedChildFrameID:         "base_link",
		MaxStatusAgeMS:               400.0,
		MaxCorrectionM:               0.25,
		MaxMeasurementDeltaM:         1.25,
		MaxCorrectionStepM:           0.03,
		MinRuntimeConsistencySamples: 5,
		MinDirectionCosine:           0.70,
		MaxAxisSignFlips:             0,
		MaxSaturationRatio:           0.95,
		HistorySamples:               8,
		EnableCorrection:             true,
	}
}

func DefaultExternalNavSourceSelectorSpec() ExternalNavSourceSelectorSpec {
	return ExternalNavSourceSelectorSpec{
		SlamOdomTopic:             "/slam/odom",
		ScanReferenceOdomTopic:    "/navlab/scan_reference_drift/odom",
		ScanReferenceStatusTopic:  "/navlab/scan_reference_drift/status",
		HoverStatusTopic:          "/navlab/hover/status",
		OutputOdomTopic:           "/external_nav/odom_candidate",
		StatusTopic:               "/external_nav/source_selector/status",
		MaxStatusAgeMS:            400.0,
		CartographerDisagreementM: 0.15,
	}
}

func DefaultHoverMissionRuntimeSpec() HoverMissionRuntimeSpec {
	fcu := DefaultFCUControllerSpec()
	hover := DefaultSlamHoverSpec()
	return HoverMissionRuntimeSpec{
		Endpoint:                          fcu.MAVLinkBootstrap,
		SourceSystem:                      fcu.MAVLinkBootstrapSourceSystem,
		SourceComponent:                   fcu.MAVLinkBootstrapSourceComponent,
		Mode:                              fcu.GuidedMode,
		TakeoffAltM:                       fcu.TakeoffAltM,
		MinAirborneAltM:                   0.10,
		PreflightReadySec:                 5.0,
		MaxWaitReadySec:                   35.0,
		HoverSettleSec:                    2.0,
		HoverAltitudeToleranceM:           0.18,
		HoverHoldSec:                      hover.HoverWindowSec,
		HoverHealthMinObservationSec:      10.0,
		HoverHealthStableRequiredSec:      5.0,
		HoverHealthMaxWaitSec:             60.0,
		StartupReadinessTimeoutSec:        35.0,
		StartupReadinessGraceSec:          8.0,
		StartupReadinessProgressWindowSec: 3.0,
		StartupReadinessRestartLimit:      0,
		OperatorConfirmRequired:           false,
		OperatorConfirmTimeoutSec:         60.0,
		MaxHorizontalDriftM:               hover.MaxHoverHorizontalDrift,
		HoverSpanTargetM:                  hover.HoverSpanTargetM,
		HoverSpanHardCapM:                 hover.HoverSpanHardCapM,
		MaxAltitudeDriftM:                 hover.MaxHoverAltitudeError,
		StatusTopic:                       hover.HoverStatusTopic,
		LandingStatusTopic:                "/navlab/landing/status",
		LandingIntentTopic:                "/navlab/landing/intent",
		ExternalNavStatusTopic:            hover.ExternalNavStatusTopic,
		MAVLinkExternalNavStatusTopic:     "/mavlink_external_nav/status",
		IMUStatusTopic:                    "/imu/status",
		MAVLinkStatusTopic:                "/navlab/mavlink/status",
		PreLandHoldSec:                    2.0,
		LandingPolicy:                     PolicyAPLandModeAfterHover,
		MaxLandingDurationSec:             35.0,
		LandingDescentRateMPS:             0.09,
		LandingLandCommandAltitudeM:       0.18,
		LandingSetpointLookaheadSec:       0.5,
		MaxLandingDescentRateMPS:          0.60,
		TouchdownAltitudeM:                0.12,
		TouchdownVerticalSpeedMPS:         0.08,
		ForceDisarmGraceSec:               3.0,
		RequireDisarm:                     true,
		RequireMotorsSafe:                 true,
		RequireExternalNav:                true,
		RequireIMUStatus:                  true,
		DisableArmingChecks:               true,
		ForceArm:                          false,
	}
}

func WriteHoverRuntimeConfig(path string, spec SlamHoverSpec) error {
	if spec.SlamOdomTopic == "" {
		spec = DefaultSlamHoverSpec()
	}
	return writeTOML(path, map[string]any{"slam_hover": map[string]any{"runtime": spec}})
}

func HoverProbeScript(spec SlamHoverSpec) (string, error) {
	if spec.SlamOdomTopic == "" {
		spec = DefaultSlamHoverSpec()
	}
	sourceSelector := DefaultExternalNavSourceSelectorSpec()
	return rosProbeScriptWithOptionalTopics(
		"navlab_slam_hover_probe",
		[]string{spec.FCUPoseTopic, spec.SlamOdomTopic, spec.SlamStatusTopic, spec.ExternalNavStatusTopic, sourceSelector.OutputOdomTopic, sourceSelector.StatusTopic, spec.ScanReferenceOdomTopic, spec.ScanReferenceStatusTopic, "/mavlink_external_nav/status", "/sim/x2/status", spec.HoverStatusTopic, "/navlab/landing/status"},
		[]string{"/navlab/landing/status"},
		spec,
	)
}

func ScanReferenceDriftRuntimeScript(spec ScanReferenceDriftSpec) (string, error) {
	if spec.ScanTopic == "" {
		spec = DefaultScanReferenceDriftSpec()
	}
	payload, err := json.Marshal(map[string]any{
		"scan_topic":                   spec.ScanTopic,
		"hover_status_topic":           spec.HoverStatusTopic,
		"odom_topic":                   spec.OdomTopic,
		"status_topic":                 spec.StatusTopic,
		"frame_id":                     spec.FrameID,
		"child_frame_id":               spec.ChildFrameID,
		"min_valid_beams":              spec.MinValidBeams,
		"max_residual_rms_m":           spec.MaxResidualRMSM,
		"max_range_delta_m":            spec.MaxRangeDeltaM,
		"max_horizontal_drift_m":       spec.MaxHorizontalDriftM,
		"max_inlier_residual_m":        spec.MaxInlierResidualM,
		"min_inlier_ratio":             spec.MinInlierRatio,
		"robust_iterations":            spec.RobustIterations,
		"yaw_search_window_rad":        spec.YawSearchWindowRad,
		"yaw_search_steps":             spec.YawSearchSteps,
		"eligibility_window_samples":   spec.EligibilityWindowSamples,
		"min_stable_samples":           spec.MinStableSamples,
		"min_axis_drift_m":             spec.MinAxisDriftM,
		"axis_deadband_m":              spec.AxisDeadbandM,
		"max_axis_sign_flips":          spec.MaxAxisSignFlips,
		"max_velocity_mps":             spec.MaxVelocityMPS,
		"min_direction_cosine":         spec.MinDirectionCosine,
		"max_phase4b_saturation_ratio": spec.MaxPhase4BSaturationRatio,
		"min_correction_intent_consecutive_allowed_samples": spec.MinCorrectionIntentConsecutiveAllowedSamples,
		"max_correction_intent_m":                           spec.MaxCorrectionIntentM,
		"correction_intent_gain":                            spec.CorrectionIntentGain,
		"reset_on_hover_hold":                               spec.ResetOnHoverHold,
	})
	if err != nil {
		return "", err
	}
	return renderRuntimeScriptTemplate("scan_reference_drift_runtime.py.tmpl", payload)
}

func ScanReferenceCorrectionRuntimeScript(spec ScanReferenceCorrectionSpec) (string, error) {
	if spec.OutputOdomTopic == "" {
		spec = DefaultScanReferenceCorrectionSpec()
	}
	payload, err := json.Marshal(map[string]any{
		"slam_odom_topic":                 spec.SlamOdomTopic,
		"scan_reference_status_topic":     spec.ScanReferenceStatusTopic,
		"hover_status_topic":              spec.HoverStatusTopic,
		"output_odom_topic":               spec.OutputOdomTopic,
		"status_topic":                    spec.StatusTopic,
		"expected_frame_id":               spec.ExpectedFrameID,
		"expected_child_frame_id":         spec.ExpectedChildFrameID,
		"max_status_age_ms":               spec.MaxStatusAgeMS,
		"max_correction_m":                spec.MaxCorrectionM,
		"max_measurement_delta_m":         spec.MaxMeasurementDeltaM,
		"max_correction_step_m":           spec.MaxCorrectionStepM,
		"min_runtime_consistency_samples": spec.MinRuntimeConsistencySamples,
		"min_direction_cosine":            spec.MinDirectionCosine,
		"max_axis_sign_flips":             spec.MaxAxisSignFlips,
		"max_saturation_ratio":            spec.MaxSaturationRatio,
		"history_samples":                 spec.HistorySamples,
		"enable_correction":               spec.EnableCorrection,
	})
	if err != nil {
		return "", err
	}
	return renderRuntimeScriptTemplate("scan_reference_correction_runtime.py.tmpl", payload)
}

func ExternalNavSourceSelectorRuntimeScript(spec ExternalNavSourceSelectorSpec) (string, error) {
	if spec.OutputOdomTopic == "" {
		spec = DefaultExternalNavSourceSelectorSpec()
	}
	payload, err := json.Marshal(map[string]any{
		"slam_odom_topic":             spec.SlamOdomTopic,
		"scan_reference_odom_topic":   spec.ScanReferenceOdomTopic,
		"scan_reference_status_topic": spec.ScanReferenceStatusTopic,
		"hover_status_topic":          spec.HoverStatusTopic,
		"output_odom_topic":           spec.OutputOdomTopic,
		"status_topic":                spec.StatusTopic,
		"max_status_age_ms":           spec.MaxStatusAgeMS,
		"cartographer_disagreement_m": spec.CartographerDisagreementM,
	})
	if err != nil {
		return "", err
	}
	return renderRuntimeScriptTemplate("external_nav_source_selector_runtime.py.tmpl", payload)
}

func HoverMissionRuntimeScript(spec HoverMissionRuntimeSpec, durationSec float64) (string, error) {
	if spec.Endpoint == "" {
		spec = DefaultHoverMissionRuntimeSpec()
	}
	payload, err := json.Marshal(map[string]any{
		"duration_sec":                     durationSec,
		"endpoint":                         spec.Endpoint,
		"source_system":                    spec.SourceSystem,
		"source_component":                 spec.SourceComponent,
		"mode":                             spec.Mode,
		"takeoff_alt_m":                    spec.TakeoffAltM,
		"min_airborne_alt_m":               spec.MinAirborneAltM,
		"preflight_ready_sec":              spec.PreflightReadySec,
		"max_wait_ready_sec":               spec.MaxWaitReadySec,
		"hover_settle_sec":                 spec.HoverSettleSec,
		"hover_altitude_tolerance_m":       spec.HoverAltitudeToleranceM,
		"hover_hold_sec":                   spec.HoverHoldSec,
		"hover_health_min_observation_sec": spec.HoverHealthMinObservationSec,
		"hover_health_stable_required_sec": spec.HoverHealthStableRequiredSec,
		"hover_health_max_wait_sec":        spec.HoverHealthMaxWaitSec,
		"startup_readiness_policy": map[string]any{
			"owner":               "go_runtime_config",
			"timeout_sec":         spec.StartupReadinessTimeoutSec,
			"grace_sec":           spec.StartupReadinessGraceSec,
			"progress_window_sec": spec.StartupReadinessProgressWindowSec,
			"restart_limit":       spec.StartupReadinessRestartLimit,
		},
		"operator_confirm_required":         spec.OperatorConfirmRequired,
		"operator_confirm_timeout_sec":      spec.OperatorConfirmTimeoutSec,
		"max_horizontal_drift_m":            spec.MaxHorizontalDriftM,
		"hover_span_target_m":               spec.HoverSpanTargetM,
		"hover_span_hard_cap_m":             spec.HoverSpanHardCapM,
		"max_altitude_drift_m":              spec.MaxAltitudeDriftM,
		"status_topic":                      spec.StatusTopic,
		"landing_status_topic":              spec.LandingStatusTopic,
		"landing_intent_topic":              spec.LandingIntentTopic,
		"external_nav_status_topic":         spec.ExternalNavStatusTopic,
		"mavlink_external_nav_status_topic": spec.MAVLinkExternalNavStatusTopic,
		"imu_status_topic":                  spec.IMUStatusTopic,
		"mavlink_status_topic":              spec.MAVLinkStatusTopic,
		"pre_land_hold_sec":                 spec.PreLandHoldSec,
		"landing_policy":                    spec.LandingPolicy,
		"max_landing_duration_sec":          spec.MaxLandingDurationSec,
		"landing_descent_rate_mps":          spec.LandingDescentRateMPS,
		"landing_land_command_altitude_m":   spec.LandingLandCommandAltitudeM,
		"landing_setpoint_lookahead_sec":    spec.LandingSetpointLookaheadSec,
		"max_landing_descent_rate_mps":      spec.MaxLandingDescentRateMPS,
		"touchdown_altitude_m":              spec.TouchdownAltitudeM,
		"touchdown_vertical_speed_mps":      spec.TouchdownVerticalSpeedMPS,
		"force_disarm_grace_sec":            spec.ForceDisarmGraceSec,
		"require_disarm":                    spec.RequireDisarm,
		"require_motors_safe":               spec.RequireMotorsSafe,
		"require_external_nav":              spec.RequireExternalNav,
		"require_imu_status":                spec.RequireIMUStatus,
		"disable_arming_checks":             spec.DisableArmingChecks,
		"force_arm":                         spec.ForceArm,
	})
	if err != nil {
		return "", err
	}
	return renderRuntimeScriptTemplate("hover_mission_runtime.py.tmpl", payload)
}

func SlamOnlyProbeScript(spec SlamOnlySpec, durationSec float64) (string, error) {
	if spec.ScanTopic == "" {
		spec = DefaultSlamOnlySpec()
	}
	probeDuration := spec.ProbeDurationSec
	if durationSec > 0 && durationSec < probeDuration {
		probeDuration = durationSec
	}
	if probeDuration < spec.MinProbeDurationSec {
		probeDuration = spec.MinProbeDurationSec
	}
	payload, err := json.Marshal(map[string]any{
		"scan_topic":                spec.ScanTopic,
		"imu_topic":                 spec.IMUTopic,
		"slam_odom_topic":           spec.SlamOdomTopic,
		"slam_status_topic":         spec.SlamStatusTopic,
		"external_nav_status_topic": spec.ExternalNavStatusTopic,
		"duration_sec":              probeDuration,
		"min_odom_rate_hz":          spec.MinOdomRateHz,
		"max_odom_stale_sec":        spec.MaxOdomStaleSec,
		"max_position_jump_m":       spec.MaxPositionJumpM,
		"min_probe_duration_sec":    spec.MinProbeDurationSec,
	})
	if err != nil {
		return "", err
	}
	return renderRuntimeScriptTemplate("slam_only_probe.py.tmpl", payload)
}

type ScanStabilizationSpec struct {
	Mode                        string
	InputScanTopic              string
	OutputScanTopic             string
	StatusTopic                 string
	AttitudeSourceTopic         string
	MaxRejectedBeamRatio        float64
	MinRetainedBeamRatio        float64
	MaxFloorHitRiskBeamRatio    float64
	MaxVerticalProjectionErrorM float64
	MaxAttitudeSourceAgeMS      float64
	PassthroughTiltDeg          float64
	CompensationTiltDeg         float64
	HardDropTiltDeg             float64
	UsesGazeboTruthAsInput      bool
	ScanStabilizationClaim      string
	ReplayReadinessTimeoutSec   float64
	ControllerSummaryTimeoutSec float64
}

func DefaultScanStabilizationSpec() ScanStabilizationSpec {
	return ScanStabilizationSpec{
		Mode:                        "bounded_2d_projection",
		InputScanTopic:              "/navlab/x2/scan_normalized",
		OutputScanTopic:             "/scan",
		StatusTopic:                 "/navlab/scan_stabilization/status",
		AttitudeSourceTopic:         "/imu",
		MaxRejectedBeamRatio:        0.35,
		MinRetainedBeamRatio:        0.60,
		MaxFloorHitRiskBeamRatio:    0.10,
		MaxVerticalProjectionErrorM: 0.15,
		MaxAttitudeSourceAgeMS:      300.0,
		PassthroughTiltDeg:          2.0,
		CompensationTiltDeg:         5.0,
		HardDropTiltDeg:             25.0,
		UsesGazeboTruthAsInput:      false,
		ScanStabilizationClaim:      "evaluated",
		ReplayReadinessTimeoutSec:   60.0,
		ControllerSummaryTimeoutSec: 20.0,
	}
}

func ValidateScanStabilizationConfig(spec ScanStabilizationSpec) []string {
	var blockers []string
	if spec.Mode != "bounded_2d_projection" {
		blockers = append(blockers, "scan_stabilization_config_invalid: mode must be bounded_2d_projection")
	}
	if spec.InputScanTopic == spec.OutputScanTopic {
		blockers = append(blockers, "scan_stabilization_config_invalid: input and output topics must differ")
	}
	if !(0.0 <= spec.PassthroughTiltDeg && spec.PassthroughTiltDeg < spec.CompensationTiltDeg && spec.CompensationTiltDeg < spec.HardDropTiltDeg) {
		blockers = append(blockers, "scan_stabilization_config_invalid: tilt thresholds must be ordered")
	}
	if spec.UsesGazeboTruthAsInput {
		blockers = append(blockers, "scan_stabilization must not use Gazebo truth as input")
	}
	if spec.ScanStabilizationClaim != "evaluated" {
		blockers = append(blockers, "scan_stabilization_claim must be evaluated")
	}
	return blockers
}

func WriteScanStabilizationRuntimeConfig(path string, spec ScanStabilizationSpec) error {
	if spec.Mode == "" {
		spec = DefaultScanStabilizationSpec()
	}
	return writeTOML(path, map[string]any{
		"scan_stabilization":      map[string]any{"runtime": spec},
		"scan_stabilization_gate": map[string]any{"runtime": map[string]any{"replay_readiness_timeout_sec": spec.ReplayReadinessTimeoutSec, "controller_summary_timeout_sec": spec.ControllerSummaryTimeoutSec}},
	})
}

func StabilizationStatusProbeScript(spec ScanStabilizationSpec) (string, error) {
	if spec.Mode == "" {
		spec = DefaultScanStabilizationSpec()
	}
	return rosProbeScript("navlab_scan_stabilization_status_probe", []string{spec.StatusTopic}, map[string]any{"status_topic": spec.StatusTopic})
}

func AirframeDisturbanceProbeScript(spec ScanRobustnessWorkflowSpec) (string, error) {
	if spec.Profile == "" {
		spec = DefaultScanRobustnessWorkflowSpec()
	}
	return rosProbeScript("navlab_airframe_disturbance_probe", []string{spec.DisturbanceStatusTopic}, map[string]any{
		"status_topic":      spec.DisturbanceStatusTopic,
		"required_profiles": spec.RequiredProfiles,
		"profile":           spec.Profile,
	})
}

type ExplorationWorkflowSpec struct {
	Strategy               string
	ExplorationWindowSec   float64
	MotionSpeedMPS         float64
	YawRateRadPS           float64
	MinAcceptedGoals       int
	MinPathLengthM         float64
	ProbeTimeoutSec        float64
	ControllerStatusTopic  string
	SetpointIntentTopic    string
	SetpointOutputTopic    string
	SlamOdomTopic          string
	ExplorationStatusTopic string
}

func DefaultExplorationWorkflowSpec() ExplorationWorkflowSpec {
	return ExplorationWorkflowSpec{
		Strategy:               "frontier_lite",
		ExplorationWindowSec:   26.0,
		MotionSpeedMPS:         0.10,
		YawRateRadPS:           0.18,
		MinAcceptedGoals:       3,
		MinPathLengthM:         0.35,
		ProbeTimeoutSec:        35.0,
		ControllerStatusTopic:  "/navlab/fcu/controller/status",
		SetpointIntentTopic:    "/navlab/fcu/setpoint/intent",
		SetpointOutputTopic:    "/navlab/fcu/setpoint/output",
		SlamOdomTopic:          "/slam/odom",
		ExplorationStatusTopic: "/navlab/exploration/status",
	}
}

func WriteExplorationRuntimeConfig(path string, spec ExplorationWorkflowSpec) error {
	if spec.Strategy == "" {
		spec = DefaultExplorationWorkflowSpec()
	}
	return writeTOML(path, map[string]any{"exploration_gate": map[string]any{"runtime": spec}})
}

func ExplorationProbeScript(spec ExplorationWorkflowSpec) (string, error) {
	if spec.Strategy == "" {
		spec = DefaultExplorationWorkflowSpec()
	}
	return rosProbeScript(
		"navlab_exploration_probe",
		[]string{spec.ControllerStatusTopic, spec.SetpointOutputTopic, spec.ExplorationStatusTopic, spec.SlamOdomTopic, "/navlab/landing/status"},
		spec,
	)
}

func ExplorationWorkflowRuntimeScript(spec ExplorationWorkflowSpec, durationSec float64) (string, error) {
	if spec.Strategy == "" {
		spec = DefaultExplorationWorkflowSpec()
	}
	payload, err := json.Marshal(map[string]any{
		"duration_sec":             durationSec,
		"strategy":                 spec.Strategy,
		"exploration_window_sec":   spec.ExplorationWindowSec,
		"motion_speed_mps":         spec.MotionSpeedMPS,
		"yaw_rate_radps":           spec.YawRateRadPS,
		"min_accepted_goals":       spec.MinAcceptedGoals,
		"min_path_length_m":        spec.MinPathLengthM,
		"controller_status_topic":  spec.ControllerStatusTopic,
		"setpoint_intent_topic":    spec.SetpointIntentTopic,
		"setpoint_output_topic":    spec.SetpointOutputTopic,
		"slam_odom_topic":          spec.SlamOdomTopic,
		"exploration_status_topic": spec.ExplorationStatusTopic,
	})
	if err != nil {
		return "", err
	}
	return renderRuntimeScriptTemplate("exploration_workflow_runtime.py.tmpl", payload)
}

type Nav2NavigationSpec struct {
	Profile                      string
	GlobalFrame                  string
	OdomFrame                    string
	BaseFrame                    string
	ScanTopic                    string
	MapTopic                     string
	SeedMapTopic                 string
	CmdVelTopic                  string
	BTXML                        string
	PlannerPlugin                string
	ControllerPlugin             string
	UseSimTime                   bool
	GlobalCostmapTopic           string
	LocalCostmapTopic            string
	RequiredCostmapLayers        []string
	MaxCostmapAgeSec             float64
	MinObstacleCells             int
	MaxUnknownRatio              float64
	InflationRadiusM             float64
	FootprintRadiusM             float64
	CostmapHealthTopic           string
	SetpointIntentTopic          string
	AdapterStatusTopic           string
	MaxXYSpeedMPS                float64
	MaxYawRateDPS                float64
	MaxAccelMPS2                 float64
	FixedAltitudeM               float64
	StopOnStaleCostmap           bool
	StopOnStaleSlam              bool
	NavigationStatusTopic        string
	NavigationEventsTopic        string
	NavigationGoalTopic          string
	NavigationPathTopic          string
	NavigationRecoveryTopic      string
	Strategy                     string
	CompletionPolicy             string
	GoalFrame                    string
	NavigationWindowSec          float64
	MaxGoalRadiusM               float64
	MinClearanceM                float64
	MinCoverageGrowth            float64
	MinPathLengthM               float64
	MinAcceptedGoals             int
	MaxRecoveryCount             int
	ReturnHomePolicy             string
	UsesGazeboTruthAsInput       bool
	ExitGoal                     NavigationGoalSpec
	BoundedGoals                 []NavigationGoalSpec
	HomeGoal                     NavigationGoalSpec
	SlamOdomTopic                string
	SlamStatusTopic              string
	ControllerStatusTopic        string
	OwnerStatusTopic             string
	ScanStabilizationStatusTopic string
	LandingStatusTopic           string
}

type NavigationGoalSpec struct {
	ID     string
	XM     float64
	YM     float64
	YawRad float64
}

func DefaultNav2NavigationSpec() Nav2NavigationSpec {
	return Nav2NavigationSpec{
		Profile:                      "indoor_2d",
		GlobalFrame:                  "map",
		OdomFrame:                    "odom",
		BaseFrame:                    "base_link",
		ScanTopic:                    "/scan",
		MapTopic:                     "/map",
		SeedMapTopic:                 "/navlab/navigation/seed_map",
		CmdVelTopic:                  "/cmd_vel_nav",
		BTXML:                        "navigate_to_pose_w_replanning_and_recovery.xml",
		PlannerPlugin:                "GridBased",
		ControllerPlugin:             "FollowPath",
		UseSimTime:                   true,
		GlobalCostmapTopic:           "/global_costmap/costmap",
		LocalCostmapTopic:            "/local_costmap/costmap",
		RequiredCostmapLayers:        []string{"static_layer", "obstacle_layer", "inflation_layer"},
		MaxCostmapAgeSec:             1.5,
		MinObstacleCells:             1,
		MaxUnknownRatio:              0.35,
		InflationRadiusM:             0.35,
		FootprintRadiusM:             0.22,
		CostmapHealthTopic:           "/navlab/navigation/costmap_health",
		SetpointIntentTopic:          "/navlab/fcu/setpoint/intent",
		AdapterStatusTopic:           "/navlab/navigation/adapter/status",
		MaxXYSpeedMPS:                0.25,
		MaxYawRateDPS:                35,
		MaxAccelMPS2:                 0.35,
		FixedAltitudeM:               0.8,
		StopOnStaleCostmap:           true,
		StopOnStaleSlam:              true,
		NavigationStatusTopic:        "/navlab/navigation/status",
		NavigationEventsTopic:        "/navlab/navigation/events",
		NavigationGoalTopic:          "/navlab/navigation/goal",
		NavigationPathTopic:          "/navlab/navigation/path",
		NavigationRecoveryTopic:      "/navlab/navigation/recovery",
		Strategy:                     "bounded_frontier",
		CompletionPolicy:             "land_in_place",
		GoalFrame:                    "map",
		NavigationWindowSec:          120,
		MaxGoalRadiusM:               0.45,
		MinClearanceM:                0.35,
		MinCoverageGrowth:            0.50,
		MinPathLengthM:               4.0,
		MinAcceptedGoals:             3,
		MaxRecoveryCount:             2,
		ReturnHomePolicy:             "return_home_then_land",
		UsesGazeboTruthAsInput:       false,
		ExitGoal:                     NavigationGoalSpec{ID: "maze_exit", XM: 1.5, YM: -0.5, YawRad: 0.0},
		BoundedGoals:                 []NavigationGoalSpec{{ID: "p13_probe_1", XM: 1.0, YM: 0.0, YawRad: 0.0}},
		HomeGoal:                     NavigationGoalSpec{ID: "home", XM: 0.0, YM: 0.0, YawRad: 0.0},
		SlamOdomTopic:                "/slam/odom",
		SlamStatusTopic:              "/navlab/slam/status",
		ControllerStatusTopic:        "/navlab/fcu/controller/status",
		OwnerStatusTopic:             "/navlab/fcu/owner/status",
		ScanStabilizationStatusTopic: "/navlab/scan_stabilization/status",
		LandingStatusTopic:           "/navlab/landing/status",
	}
}

func WriteNav2ParamsYAML(path string, spec Nav2NavigationSpec) error {
	if spec.Profile == "" {
		spec = DefaultNav2NavigationSpec()
	}
	content, err := renderHelperTemplate("yaml/nav2_params.yaml.tmpl", spec)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, []byte(content), 0o644)
}

func WriteNavigationAdapterRuntimeConfig(path string, spec Nav2NavigationSpec) error {
	if spec.Profile == "" {
		spec = DefaultNav2NavigationSpec()
	}
	return writeTOML(path, map[string]any{
		"nav2": map[string]any{"runtime": map[string]any{
			"profile":           spec.Profile,
			"global_frame":      spec.GlobalFrame,
			"odom_frame":        spec.OdomFrame,
			"base_frame":        spec.BaseFrame,
			"scan_topic":        spec.ScanTopic,
			"map_topic":         spec.MapTopic,
			"seed_map_topic":    spec.SeedMapTopic,
			"cmd_vel_topic":     spec.CmdVelTopic,
			"bt_xml":            spec.BTXML,
			"planner_plugin":    spec.PlannerPlugin,
			"controller_plugin": spec.ControllerPlugin,
			"use_sim_time":      spec.UseSimTime,
		}},
		"navigation_adapter": map[string]any{"runtime": map[string]any{
			"setpoint_intent_topic": spec.SetpointIntentTopic,
			"status_topic":          spec.AdapterStatusTopic,
			"max_xy_speed_mps":      spec.MaxXYSpeedMPS,
			"max_yaw_rate_dps":      spec.MaxYawRateDPS,
			"max_accel_mps2":        spec.MaxAccelMPS2,
			"fixed_altitude_m":      spec.FixedAltitudeM,
			"stop_on_stale_costmap": spec.StopOnStaleCostmap,
			"stop_on_stale_slam":    spec.StopOnStaleSlam,
		}},
		"navigation_mission": map[string]any{"runtime": map[string]any{
			"strategy":                   spec.Strategy,
			"completion_policy":          spec.CompletionPolicy,
			"goal_frame":                 spec.GoalFrame,
			"status_topic":               spec.NavigationStatusTopic,
			"events_topic":               spec.NavigationEventsTopic,
			"goal_topic":                 spec.NavigationGoalTopic,
			"path_topic":                 spec.NavigationPathTopic,
			"recovery_topic":             spec.NavigationRecoveryTopic,
			"navigation_window_sec":      spec.NavigationWindowSec,
			"max_goal_radius_m":          spec.MaxGoalRadiusM,
			"min_clearance_m":            spec.MinClearanceM,
			"min_coverage_growth":        spec.MinCoverageGrowth,
			"min_path_length_m":          spec.MinPathLengthM,
			"min_accepted_goals":         spec.MinAcceptedGoals,
			"max_recovery_count":         spec.MaxRecoveryCount,
			"return_home_policy":         spec.ReturnHomePolicy,
			"uses_gazebo_truth_as_input": spec.UsesGazeboTruthAsInput,
			"exit_goal":                  spec.ExitGoal,
			"bounded_goals":              spec.BoundedGoals,
			"home_goal":                  spec.HomeGoal,
		}},
	})
}

func WriteNavigationFoxgloveLiteProfile(path string, spec Nav2NavigationSpec) error {
	if spec.Profile == "" {
		spec = DefaultNav2NavigationSpec()
	}
	profile := map[string]any{
		"schemaVersion": "navlab.sim.foxglove_lite_profile.v1",
		"taskId":        "navigation",
		"name":          "P13 Nav2 indoor navigation",
		"topics": []map[string]string{
			{"role": "map", "topic": spec.MapTopic, "messageType": "nav_msgs/msg/OccupancyGrid"},
			{"role": "global_costmap", "topic": spec.GlobalCostmapTopic, "messageType": "nav_msgs/msg/OccupancyGrid"},
			{"role": "local_costmap", "topic": spec.LocalCostmapTopic, "messageType": "nav_msgs/msg/OccupancyGrid"},
			{"role": "scan", "topic": spec.ScanTopic, "messageType": "sensor_msgs/msg/LaserScan"},
			{"role": "trajectory", "topic": spec.SlamOdomTopic, "messageType": "nav_msgs/msg/Odometry"},
			{"role": "path", "topic": spec.NavigationPathTopic, "messageType": "std_msgs/msg/String"},
			{"role": "goals", "topic": spec.NavigationGoalTopic, "messageType": "std_msgs/msg/String"},
			{"role": "events", "topic": spec.NavigationEventsTopic, "messageType": "std_msgs/msg/String"},
			{"role": "navigation_status", "topic": spec.NavigationStatusTopic, "messageType": "std_msgs/msg/String"},
			{"role": "adapter_status", "topic": spec.AdapterStatusTopic, "messageType": "std_msgs/msg/String"},
			{"role": "costmap_health", "topic": spec.CostmapHealthTopic, "messageType": "std_msgs/msg/String"},
			{"role": "landing_status", "topic": spec.LandingStatusTopic, "messageType": "std_msgs/msg/String"},
		},
		"reviewChecks": []string{
			"map frame and path frame stay in map",
			"Nav2 path does not bypass the adapter intent topic",
			"costmap health remains fresh while goals execute",
			"frontier candidates, rejected reasons, and blacklist are visible in navigation status",
		},
	}
	data, err := json.MarshalIndent(profile, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, append(data, '\n'), 0o644)
}

func NavigationAdapterRuntimeScript(spec Nav2NavigationSpec, durationSec float64) (string, error) {
	if spec.Profile == "" {
		spec = DefaultNav2NavigationSpec()
	}
	payload, err := json.Marshal(spec)
	if err != nil {
		return "", err
	}
	return renderRuntimeScriptTemplateData("navigation_adapter_runtime.py.tmpl", runtimeScriptTemplateData{SpecJSON: string(payload), DurationSec: durationSec})
}

func NavigationMissionRuntimeScript(spec Nav2NavigationSpec, durationSec float64) (string, error) {
	if spec.Profile == "" {
		spec = DefaultNav2NavigationSpec()
	}
	payload, err := json.Marshal(spec)
	if err != nil {
		return "", err
	}
	return renderRuntimeScriptTemplateData("navigation_mission_runtime.py.tmpl", runtimeScriptTemplateData{SpecJSON: string(payload), DurationSec: durationSec})
}

func Nav2LifecycleProbeScript(spec Nav2NavigationSpec) (string, error) {
	if spec.Profile == "" {
		spec = DefaultNav2NavigationSpec()
	}
	payload, err := json.Marshal(spec)
	if err != nil {
		return "", err
	}
	return renderRuntimeScriptTemplate("nav2_lifecycle_probe.py.tmpl", payload)
}

func CostmapHealthProbeScript(spec Nav2NavigationSpec) (string, error) {
	if spec.Profile == "" {
		spec = DefaultNav2NavigationSpec()
	}
	payload, err := json.Marshal(spec)
	if err != nil {
		return "", err
	}
	return renderRuntimeScriptTemplate("costmap_health_probe.py.tmpl", payload)
}

func NavigationStatusProbeScript(spec Nav2NavigationSpec) (string, error) {
	if spec.Profile == "" {
		spec = DefaultNav2NavigationSpec()
	}
	payload, err := json.Marshal(spec)
	if err != nil {
		return "", err
	}
	return renderRuntimeScriptTemplate("navigation_status_probe.py.tmpl", payload)
}

type ScanRobustnessWorkflowSpec struct {
	Profile                string
	RequiredProfiles       []string
	FCUStatusTopic         string
	StabilizedScanTopic    string
	DisturbanceStatusTopic string
	IMURawTopic            string
	IMUOutputTopic         string
	LandingPolicy          string
}

func DefaultScanRobustnessWorkflowSpec() ScanRobustnessWorkflowSpec {
	return ScanRobustnessWorkflowSpec{
		Profile:                "ideal",
		RequiredProfiles:       []string{"ideal", "realistic"},
		FCUStatusTopic:         "/navlab/fcu/controller/status",
		StabilizedScanTopic:    "/scan",
		DisturbanceStatusTopic: "/navlab/airframe_disturbance/status",
		IMURawTopic:            "/imu/raw",
		IMUOutputTopic:         "/imu",
		LandingPolicy:          "land_in_place",
	}
}

func WriteScanRobustnessRuntimeConfig(path string, spec ScanRobustnessWorkflowSpec) error {
	if spec.Profile == "" {
		spec = DefaultScanRobustnessWorkflowSpec()
	}
	return writeTOML(path, map[string]any{
		"airframe_disturbance":      map[string]any{"runtime": spec},
		"airframe_disturbance_gate": map[string]any{"runtime": map[string]any{"required_profiles": spec.RequiredProfiles}},
		"landing":                   map[string]any{"runtime": map[string]any{"policy": spec.LandingPolicy}},
	})
}

func WriteScanRobustnessBridgeOverride(path string, imuRawTopic string) error {
	return writeBridgeOverride(path, trimTopicSlash(imuRawTopic))
}

func BaselineROSEnv() map[string]string {
	return map[string]string{
		"CYCLONEDDS_URI":     "<CycloneDDS><Domain><Discovery><ParticipantIndex>auto</ParticipantIndex><MaxAutoParticipantIndex>512</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>",
		"DDS_ENABLE":         "from config.toml",
		"DDS_DOMAIN_ID":      "from config.toml",
		"ROS_DOMAIN_ID":      "from config.toml",
		"ROS_DISTRO":         "from config.toml",
		"RMW_IMPLEMENTATION": "from config.toml",
		"PYTHONPATH":         "/workspace",
	}
}

func rosProbeScript(nodeName string, topics []string, spec any) (string, error) {
	return rosProbeScriptWithOptionalTopics(nodeName, topics, nil, spec)
}

func rosProbeScriptWithOptionalTopics(nodeName string, topics []string, optionalTopics []string, spec any) (string, error) {
	if optionalTopics == nil {
		optionalTopics = []string{}
	}
	payload, err := json.Marshal(spec)
	if err != nil {
		return "", err
	}
	topicPayload, err := json.Marshal(topics)
	if err != nil {
		return "", err
	}
	optionalTopicPayload, err := json.Marshal(optionalTopics)
	if err != nil {
		return "", err
	}
	return renderRuntimeScriptTemplateData("ros_probe.py.tmpl", runtimeScriptTemplateData{
		SpecJSON:           string(payload),
		TopicsJSON:         string(topicPayload),
		OptionalTopicsJSON: string(optionalTopicPayload),
		NodeName:           nodeName,
	})
}

func fcuControllerRuntimeScript(spec map[string]any) (string, error) {
	payload, err := json.Marshal(spec)
	if err != nil {
		return "", err
	}
	return renderRuntimeScriptTemplate("fcu_controller_runtime.py.tmpl", payload)
}

func writeTOML(path string, value any) error {
	encoded, err := toml.Marshal(value)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, encoded, 0o644)
}

func trimTopicSlash(topic string) string {
	for len(topic) > 0 && topic[0] == '/' {
		topic = topic[1:]
	}
	return topic
}
