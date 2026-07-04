package config

func applySimulationDefaults(cfg *ProjectConfig) {
	cfg.SessionID = defaultString(cfg.SessionID, "navlab_companion_sitl_gazebo")
	cfg.RosDomainID = defaultString(cfg.RosDomainID, "85")
	cfg.GazeboWorld = defaultString(cfg.GazeboWorld, "/workspace/worlds/navlab_iq_quad_figure8.sdf")
	cfg.RosbagProfile = defaultString(cfg.RosbagProfile, "docker/profiles/navlab-rosbag-topics.txt")
	cfg.Router.Image = defaultString(cfg.Router.Image, imageRepository(cfg, "mavlink_router"))
	cfg.Router.DownstreamEndpoints = defaultString(cfg.Router.DownstreamEndpoints, "127.0.0.1:14551,127.0.0.1:14552,127.0.0.1:14553")
	cfg.Router.Listen = defaultString(cfg.Router.Listen, "0.0.0.0:14550")
	cfg.Router.TCPPort = defaultString(cfg.Router.TCPPort, "0")

	cfg.Sensor.ScanSource = defaultString(cfg.Sensor.ScanSource, "x2_virtual_serial")
	cfg.Sensor.Image = defaultString(cfg.Sensor.Image, imageRepository(cfg, "gazebo_sensor"))
	if !cfg.Slam.Autostart {
		cfg.Slam.Autostart = true
	}
	cfg.Slam.Image = defaultString(cfg.Slam.Image, imageRepository(cfg, "slam"))
	cfg.Slam.Backend = defaultString(cfg.Slam.Backend, "cartographer")
	cfg.Slam.RuntimeConfig = defaultString(cfg.Slam.RuntimeConfig, "/workspace/navlab/config.toml")

	cfg.Official.DDSEnable = defaultString(cfg.Official.DDSEnable, "1")
	cfg.Official.DDSDomainID = defaultString(cfg.Official.DDSDomainID, cfg.RosDomainID)
	cfg.Official.RMWImplementation = defaultString(cfg.Official.RMWImplementation, "rmw_cyclonedds_cpp")
	cfg.Official.ExpectedAPNode = defaultString(cfg.Official.ExpectedAPNode, "/ap")
	cfg.Official.RequiredAPTopics = defaultStrings(cfg.Official.RequiredAPTopics, []string{"/ap/v1/time"})
	cfg.Official.RuntimeImage = defaultString(cfg.Official.RuntimeImage, imageRepository(cfg, "official_baseline"))
	cfg.Official.RequiredROSPackages = defaultStrings(cfg.Official.RequiredROSPackages, []string{
		"ardupilot_sitl", "ardupilot_msgs", "ardupilot_dds_tests", "micro_ros_agent",
		"ardupilot_gz_bringup", "ardupilot_gz_application", "ardupilot_gazebo",
		"ardupilot_gz_gazebo", "ardupilot_sitl_models", "ardupilot_cartographer",
	})
	cfg.Official.MicroROSAgentBinaries = defaultStrings(cfg.Official.MicroROSAgentBinaries, []string{"MicroXRCEAgent", "micro_ros_agent"})
	cfg.Official.SITLLaunch = defaultString(cfg.Official.SITLLaunch, "ros2 launch ardupilot_sitl sitl_dds_udp.launch.py")
	cfg.Official.GazeboLaunch = defaultString(cfg.Official.GazeboLaunch, "ros2 launch ardupilot_gz_bringup iris_maze.launch.py")
	cfg.Official.CartographerLaunch = defaultString(cfg.Official.CartographerLaunch, "ros2 launch ardupilot_cartographer cartographer.launch.py")
	cfg.Official.GazeboBringupMode = defaultString(cfg.Official.GazeboBringupMode, "navlab_custom_bringup")
	cfg.Official.ExternalNavRoute = defaultString(cfg.Official.ExternalNavRoute, "mavlink_fallback")

	cfg.OfficialMazeX2.WorldSource = defaultString(cfg.OfficialMazeX2.WorldSource, "official_iris_maze")
	cfg.OfficialMazeX2.VehicleModelSource = defaultString(cfg.OfficialMazeX2.VehicleModelSource, "official_iris_with_lidar")
	cfg.OfficialMazeX2.GazeboLidarTopic = defaultString(cfg.OfficialMazeX2.GazeboLidarTopic, "/lidar")
	cfg.OfficialMazeX2.X2ScanInputTopic = defaultString(cfg.OfficialMazeX2.X2ScanInputTopic, "/lidar")
	cfg.OfficialMazeX2.X2ScanTopic = defaultString(cfg.OfficialMazeX2.X2ScanTopic, "/scan")
	cfg.OfficialMazeX2.X2StatusTopic = defaultString(cfg.OfficialMazeX2.X2StatusTopic, "/sim/x2/status")
	cfg.OfficialMazeX2.X2VirtualSerialLink = defaultString(cfg.OfficialMazeX2.X2VirtualSerialLink, "/tmp/navlab_official_maze_x2")
	cfg.OfficialMazeX2.AltitudeControlClaim = defaultString(cfg.OfficialMazeX2.AltitudeControlClaim, "not_evaluated")
	cfg.OfficialMazeX2.HoverClaim = defaultString(cfg.OfficialMazeX2.HoverClaim, "not_evaluated")
	cfg.OfficialMazeX2.CartographerLaunch = defaultString(cfg.OfficialMazeX2.CartographerLaunch, cfg.Official.CartographerLaunch)

	defaultLanding(&cfg.Landing)
	defaultRangefinderIMU(&cfg.RangefinderIMU)
	defaultSlamBackend(&cfg.SlamBackend)
	defaultFCUController(&cfg.FCUController)
	defaultFrameContract(&cfg.FrameContract)
	defaultSlamHover(&cfg.SlamHover)
	defaultMotionGate(&cfg.MotionGate)
	defaultExplorationGate(&cfg.ExplorationGate)
	defaultNav2(&cfg.Nav2)
	defaultNavigationAdapter(&cfg.NavigationAdapter)
	defaultNavigationMission(&cfg.NavigationMission)
	defaultScanIntegrityGate(&cfg.ScanIntegrityGate)
	defaultScanStabilization(&cfg.ScanStabilization)
	defaultScanStabilizationGate(&cfg.ScanStabilizationGate)
	defaultAirframeDisturbance(&cfg.AirframeDisturbance)
	defaultAirframeDisturbanceGate(&cfg.AirframeDisturbanceGate)
}

func defaultLanding(cfg *LandingConfig) {
	cfg.DefaultPolicy = defaultString(cfg.DefaultPolicy, "land_in_place")
	cfg.HoverPolicy = defaultString(cfg.HoverPolicy, cfg.DefaultPolicy)
	cfg.ExplorationPolicy = defaultString(cfg.ExplorationPolicy, "return_home_then_land")
	cfg.NavigationPolicy = defaultString(cfg.NavigationPolicy, cfg.ExplorationPolicy)
	cfg.ScanRobustnessPolicy = defaultString(cfg.ScanRobustnessPolicy, cfg.DefaultPolicy)
	cfg.LandingStatusTopic = defaultString(cfg.LandingStatusTopic, "/navlab/landing/status")
	cfg.LandingIntentTopic = defaultString(cfg.LandingIntentTopic, "/navlab/landing/intent")
	cfg.HomeSource = defaultString(cfg.HomeSource, "post_takeoff_hover_pose")
	cfg.HomeRadiusM = defaultFloat(cfg.HomeRadiusM, 0.35)
	cfg.PreLandHoldSec = defaultFloat(cfg.PreLandHoldSec, 2.0)
	cfg.CompletionGraceSec = defaultFloat(cfg.CompletionGraceSec, 3.0)
	cfg.MaxReturnHomeDurationSec = defaultFloat(cfg.MaxReturnHomeDurationSec, 45.0)
	cfg.MaxLandingDurationSec = defaultFloat(cfg.MaxLandingDurationSec, 35.0)
	cfg.MaxDescentRateMPS = defaultFloat(cfg.MaxDescentRateMPS, 0.6)
	cfg.TouchdownAltitudeM = defaultFloat(cfg.TouchdownAltitudeM, 0.12)
	cfg.TouchdownVerticalSpeedMPS = defaultFloat(cfg.TouchdownVerticalSpeedMPS, 0.08)
}

func defaultRangefinderIMU(cfg *RangefinderIMUConfig) {
	cfg.WorldSource = defaultString(cfg.WorldSource, "official_iris_maze")
	cfg.VehicleModelSource = defaultString(cfg.VehicleModelSource, "official_iris_with_lidar")
	cfg.ModelOverlaySource = defaultString(cfg.ModelOverlaySource, "official_iris_with_lidar_plus_down_rangefinder")
	cfg.GazeboLidarTopic = defaultString(cfg.GazeboLidarTopic, "/lidar")
	cfg.X2ScanInputTopic = defaultString(cfg.X2ScanInputTopic, "/lidar")
	cfg.X2ScanTopic = defaultString(cfg.X2ScanTopic, "/scan")
	cfg.X2StatusTopic = defaultString(cfg.X2StatusTopic, "/sim/x2/status")
	cfg.X2VirtualSerialLink = defaultString(cfg.X2VirtualSerialLink, "/tmp/navlab_sim_x2")
	cfg.RangefinderScanIdealTopic = defaultString(cfg.RangefinderScanIdealTopic, "/rangefinder/down/scan_ideal")
	cfg.RangefinderRangeTopic = defaultString(cfg.RangefinderRangeTopic, "/rangefinder/down/range")
	cfg.RangefinderStatusTopic = defaultString(cfg.RangefinderStatusTopic, "/rangefinder/down/status")
	cfg.RangefinderFrameID = defaultString(cfg.RangefinderFrameID, "rangefinder_down_frame")
	cfg.RangefinderModelPose = defaultString(cfg.RangefinderModelPose, "0 0 -0.02 0 1.5707963267948966 0")
	cfg.RangefinderModelUpdateRateHz = defaultFloat(cfg.RangefinderModelUpdateRateHz, 20)
	cfg.RangefinderModelRayCount = defaultString(cfg.RangefinderModelRayCount, "1")
	cfg.RangefinderVirtualSerialLink = defaultString(cfg.RangefinderVirtualSerialLink, "/tmp/navlab_benewake_tfmini")
	if cfg.RangefinderSerialBaud == 0 {
		cfg.RangefinderSerialBaud = 115200
	}
	cfg.RangefinderFCUProbeEndpoint = defaultString(cfg.RangefinderFCUProbeEndpoint, "udpin:0.0.0.0:14552")
	cfg.RangefinderRateHz = defaultFloat(cfg.RangefinderRateHz, 20)
	cfg.RangefinderMinDistanceM = defaultFloat(cfg.RangefinderMinDistanceM, 0.05)
	cfg.RangefinderMaxDistanceM = defaultFloat(cfg.RangefinderMaxDistanceM, 6)
	cfg.IMUSourceRoute = defaultString(cfg.IMUSourceRoute, "official_gazebo_imu_bridge")
	cfg.IMUSourceTopic = defaultString(cfg.IMUSourceTopic, "/imu")
	cfg.IMUOutputTopic = defaultString(cfg.IMUOutputTopic, "/imu")
	cfg.IMUStatusTopic = defaultString(cfg.IMUStatusTopic, "/imu/status")
	cfg.IMUFrameID = defaultString(cfg.IMUFrameID, "imu_link")
	cfg.IMUMinRateHz = defaultFloat(cfg.IMUMinRateHz, 4)
	cfg.AltitudeControlClaim = defaultString(cfg.AltitudeControlClaim, "not_evaluated")
	cfg.HoverClaim = defaultString(cfg.HoverClaim, "not_evaluated")
	cfg.CartographerLaunch = defaultString(cfg.CartographerLaunch, "ros2 launch ardupilot_cartographer cartographer.launch.py")
}

func defaultSlamBackend(cfg *SlamBackendConfig) {
	cfg.Backend = defaultString(cfg.Backend, "cartographer")
	cfg.LaunchPackage = defaultString(cfg.LaunchPackage, "navlab_slam_bringup")
	cfg.LaunchFile = defaultString(cfg.LaunchFile, "navlab_slam_bringup.launch.py")
	cfg.CartographerConfigurationBasename = defaultString(cfg.CartographerConfigurationBasename, "navlab_cartographer_2d_real.lua")
	cfg.ScanTopic = defaultString(cfg.ScanTopic, "/scan")
	cfg.IMUTopic = defaultString(cfg.IMUTopic, "/imu")
	cfg.OdometryTopic = defaultString(cfg.OdometryTopic, "/cartographer/odometry_input")
	cfg.CartographerTFTopic = defaultString(cfg.CartographerTFTopic, "/navlab/slam/tf")
	cfg.OdomSourceMode = defaultString(cfg.OdomSourceMode, "slam_tf")
	cfg.SlamOdomTopic = defaultString(cfg.SlamOdomTopic, "/slam/odom")
	cfg.SlamStatusTopic = defaultString(cfg.SlamStatusTopic, "/navlab/slam/status")
	cfg.ExternalNavStatusTopic = defaultString(cfg.ExternalNavStatusTopic, "/external_nav/status")
	cfg.X2ScanInputTopic = defaultString(cfg.X2ScanInputTopic, "/navlab/x2/scan_ideal")
	cfg.X2VendorScanTopic = defaultString(cfg.X2VendorScanTopic, "/navlab/x2/vendor_scan")
	cfg.X2ScanTopic = defaultString(cfg.X2ScanTopic, "/scan")
	cfg.X2StatusTopic = defaultString(cfg.X2StatusTopic, "/sim/x2/status")
	cfg.RangefinderRangeTopic = defaultString(cfg.RangefinderRangeTopic, "/rangefinder/down/range")
	cfg.RangefinderStatusTopic = defaultString(cfg.RangefinderStatusTopic, "/rangefinder/down/status")
	cfg.IMUFrameID = defaultString(cfg.IMUFrameID, "imu_link")
	cfg.LaserFrameID = defaultString(cfg.LaserFrameID, "base_scan")
	cfg.MapFrameID = defaultString(cfg.MapFrameID, "map")
	cfg.OdomFrameID = defaultString(cfg.OdomFrameID, "odom")
	cfg.BaseFrameID = defaultString(cfg.BaseFrameID, "base_link")
	cfg.MinSlamOdomRateHz = defaultFloat(cfg.MinSlamOdomRateHz, 1)
	cfg.MaxLatestAgeSec = defaultFloat(cfg.MaxLatestAgeSec, 1)
	cfg.MaxJumpM = defaultFloat(cfg.MaxJumpM, 2)
	cfg.MaxYawJumpRad = defaultFloat(cfg.MaxYawJumpRad, 1)
	cfg.MaxStationaryDriftM = defaultFloat(cfg.MaxStationaryDriftM, 2)
	cfg.TruthDiagnosticTopic = defaultString(cfg.TruthDiagnosticTopic, "/odometry")
}

func defaultFCUController(cfg *FCUControllerConfig) {
	cfg.ControlRoute = defaultString(cfg.ControlRoute, "mavlink_bootstrap_plus_dds_cmd_vel")
	cfg.MAVLinkBootstrapEndpoint = defaultString(cfg.MAVLinkBootstrapEndpoint, "udpin:0.0.0.0:14551")
	cfg.MAVLinkBootstrapSourceSystem = defaultInt(cfg.MAVLinkBootstrapSourceSystem, 246)
	cfg.MAVLinkBootstrapSourceComponent = defaultInt(cfg.MAVLinkBootstrapSourceComponent, 190)
	cfg.OwnerName = defaultString(cfg.OwnerName, "navlab_fcu_controller")
	cfg.OwnerID = defaultString(cfg.OwnerID, "navlab-fcu-controller")
	cfg.FCUStateTopic = defaultString(cfg.FCUStateTopic, "/navlab/fcu/state")
	cfg.ControllerStatusTopic = defaultString(cfg.ControllerStatusTopic, "/navlab/fcu/controller/status")
	cfg.SetpointIntentTopic = defaultString(cfg.SetpointIntentTopic, "/navlab/fcu/setpoint/intent")
	cfg.SetpointOutputTopic = defaultString(cfg.SetpointOutputTopic, "/navlab/fcu/setpoint/output")
	cfg.OwnerStatusTopic = defaultString(cfg.OwnerStatusTopic, "/navlab/fcu/owner/status")
	cfg.TimeTopic = defaultString(cfg.TimeTopic, "/ap/v1/time")
	cfg.PrearmService = defaultString(cfg.PrearmService, "/ap/v1/prearm_check")
	cfg.ModeSwitchService = defaultString(cfg.ModeSwitchService, "/ap/v1/mode_switch")
	cfg.ArmService = defaultString(cfg.ArmService, "/ap/v1/arm_motors")
	cfg.TakeoffService = defaultString(cfg.TakeoffService, "/ap/v1/experimental/takeoff")
	cfg.CmdVelTopic = defaultString(cfg.CmdVelTopic, "/ap/v1/cmd_vel")
	cfg.PoseTopic = defaultString(cfg.PoseTopic, "/ap/v1/pose/filtered")
	cfg.TwistTopic = defaultString(cfg.TwistTopic, "/ap/v1/twist/filtered")
	cfg.StatusTopic = defaultString(cfg.StatusTopic, "/ap/v1/status")
	cfg.RangefinderRangeTopic = defaultString(cfg.RangefinderRangeTopic, "/rangefinder/down/range")
	cfg.RangefinderStatusTopic = defaultString(cfg.RangefinderStatusTopic, "/rangefinder/down/status")
	cfg.IMUTopic = defaultString(cfg.IMUTopic, "/imu")
	cfg.SlamOdomTopic = defaultString(cfg.SlamOdomTopic, "/slam/odom")
	cfg.SlamStatusTopic = defaultString(cfg.SlamStatusTopic, "/navlab/slam/status")
	cfg.GuidedMode = defaultInt(cfg.GuidedMode, 4)
	cfg.TakeoffAltM = defaultFloat(cfg.TakeoffAltM, 0.5)
	cfg.TakeoffMinHeightM = defaultFloat(cfg.TakeoffMinHeightM, 0.15)
	cfg.TakeoffMinHeightRatio = defaultFloat(cfg.TakeoffMinHeightRatio, 0.35)
	cfg.ReadinessTimeoutSec = defaultFloat(cfg.ReadinessTimeoutSec, 45)
	cfg.HoldAfterReadySec = defaultFloat(cfg.HoldAfterReadySec, 8)
	if !cfg.RequireSlamBackend {
		cfg.RequireSlamBackend = true
	}
	cfg.HoverClaim = defaultString(cfg.HoverClaim, "not_evaluated")
	cfg.ExplorationClaim = defaultString(cfg.ExplorationClaim, "not_evaluated")
}

func defaultFrameContract(cfg *FrameContractConfig) {
	cfg.RequiredFrames = defaultStrings(cfg.RequiredFrames, []string{"map", "odom", "base_link", "imu_link", "base_scan", "rangefinder_down_frame"})
	cfg.MapFrameID = defaultString(cfg.MapFrameID, "map")
	cfg.OdomFrameID = defaultString(cfg.OdomFrameID, "odom")
	cfg.BaseFrameID = defaultString(cfg.BaseFrameID, "base_link")
	cfg.IMUFrameID = defaultString(cfg.IMUFrameID, "imu_link")
	cfg.LaserFrameID = defaultString(cfg.LaserFrameID, "base_scan")
	cfg.RangefinderFrameID = defaultString(cfg.RangefinderFrameID, "rangefinder_down_frame")
	cfg.ScanTopic = defaultString(cfg.ScanTopic, "/scan")
	cfg.IMUTopic = defaultString(cfg.IMUTopic, "/imu")
	cfg.RangefinderRangeTopic = defaultString(cfg.RangefinderRangeTopic, "/rangefinder/down/range")
	cfg.RangefinderStatusTopic = defaultString(cfg.RangefinderStatusTopic, "/rangefinder/down/status")
	cfg.FCUPoseTopic = defaultString(cfg.FCUPoseTopic, "/ap/v1/pose/filtered")
	cfg.FCUTwistTopic = defaultString(cfg.FCUTwistTopic, "/ap/v1/twist/filtered")
	cfg.FCUStatusTopic = defaultString(cfg.FCUStatusTopic, "/ap/v1/status")
	cfg.CmdVelTopic = defaultString(cfg.CmdVelTopic, "/ap/v1/cmd_vel")
	cfg.SlamOdomTopic = defaultString(cfg.SlamOdomTopic, "/slam/odom")
	cfg.SlamStatusTopic = defaultString(cfg.SlamStatusTopic, "/navlab/slam/status")
	cfg.TruthDiagnosticTopic = defaultString(cfg.TruthDiagnosticTopic, "/odometry")
	cfg.ControllerStatusTopic = defaultString(cfg.ControllerStatusTopic, "/navlab/fcu/controller/status")
	cfg.SetpointOutputTopic = defaultString(cfg.SetpointOutputTopic, "/navlab/fcu/setpoint/output")
	cfg.OwnerStatusTopic = defaultString(cfg.OwnerStatusTopic, "/navlab/fcu/owner/status")
	cfg.StatusTopic = defaultString(cfg.StatusTopic, "/navlab/frame_contract/status")
	cfg.MaxDynamicTFAgeSec = defaultFloat(cfg.MaxDynamicTFAgeSec, 3)
	cfg.MinScanValidRatio = defaultFloat(cfg.MinScanValidRatio, 0.05)
	cfg.MaxRangefinderHeightErrorM = defaultFloat(cfg.MaxRangefinderHeightErrorM, 0.35)
	cfg.MaxDirectionErrorRad = defaultFloat(cfg.MaxDirectionErrorRad, 0.8)
	cfg.ProbeDurationSec = defaultFloat(cfg.ProbeDurationSec, 16)
	cfg.HoverClaim = defaultString(cfg.HoverClaim, "not_evaluated")
	cfg.ExplorationClaim = defaultString(cfg.ExplorationClaim, "not_evaluated")
}

func defaultSlamHover(cfg *SlamHoverConfig) {
	cfg.SlamOdomTopic = defaultString(cfg.SlamOdomTopic, "/slam/odom")
	cfg.SlamStatusTopic = defaultString(cfg.SlamStatusTopic, "/navlab/slam/status")
	cfg.ExternalNavStatusTopic = defaultString(cfg.ExternalNavStatusTopic, "/external_nav/status")
	cfg.FCUPoseTopic = defaultString(cfg.FCUPoseTopic, "/ap/v1/pose/filtered")
	cfg.FCUTwistTopic = defaultString(cfg.FCUTwistTopic, "/ap/v1/twist/filtered")
	cfg.FCUStatusTopic = defaultString(cfg.FCUStatusTopic, "/ap/v1/status")
	cfg.CmdVelTopic = defaultString(cfg.CmdVelTopic, "/ap/v1/cmd_vel")
	cfg.RangefinderRangeTopic = defaultString(cfg.RangefinderRangeTopic, "/rangefinder/down/range")
	cfg.RangefinderStatusTopic = defaultString(cfg.RangefinderStatusTopic, "/rangefinder/down/status")
	cfg.IMUTopic = defaultString(cfg.IMUTopic, "/imu")
	cfg.TruthDiagnosticTopic = defaultString(cfg.TruthDiagnosticTopic, "/odometry")
	cfg.ControllerStatusTopic = defaultString(cfg.ControllerStatusTopic, "/navlab/fcu/controller/status")
	cfg.SetpointIntentTopic = defaultString(cfg.SetpointIntentTopic, "/navlab/fcu/setpoint/intent")
	cfg.SetpointOutputTopic = defaultString(cfg.SetpointOutputTopic, "/navlab/fcu/setpoint/output")
	cfg.OwnerStatusTopic = defaultString(cfg.OwnerStatusTopic, "/navlab/fcu/owner/status")
	cfg.HoverStatusTopic = defaultString(cfg.HoverStatusTopic, "/navlab/hover/status")
	cfg.VehicleMarkerTopic = defaultString(cfg.VehicleMarkerTopic, "/navlab/vehicle/markers")
	cfg.VehicleMarkerPoseTopic = defaultString(cfg.VehicleMarkerPoseTopic, "/ap/v1/pose/filtered")
	cfg.VehicleMarkerRateHz = defaultFloat(cfg.VehicleMarkerRateHz, 10)
	cfg.SettleWindowSec = defaultFloat(cfg.SettleWindowSec, 8)
	cfg.HoverWindowSec = defaultFloat(cfg.HoverWindowSec, 18)
	cfg.HoverHealthMinObservationSec = defaultFloat(cfg.HoverHealthMinObservationSec, 10)
	cfg.HoverHealthStableRequiredSec = defaultFloat(cfg.HoverHealthStableRequiredSec, 5)
	cfg.HoverHealthMaxWaitSec = defaultFloat(cfg.HoverHealthMaxWaitSec, 60)
	defaultStartupReadinessPolicy(&cfg.StartupReadinessPolicy)
	cfg.OperatorConfirmTimeoutSec = defaultFloat(cfg.OperatorConfirmTimeoutSec, 60)
	cfg.FinalHoldWindowSec = defaultFloat(cfg.FinalHoldWindowSec, 5)
	cfg.MaxHoverHorizontalDriftM = defaultFloat(cfg.MaxHoverHorizontalDriftM, 0.10)
	cfg.HoverSpanTargetM = defaultFloat(cfg.HoverSpanTargetM, cfg.MaxHoverHorizontalDriftM)
	cfg.HoverSpanHardCapM = defaultFloat(cfg.HoverSpanHardCapM, 0.15)
	cfg.MaxHoverAltitudeErrorM = defaultFloat(cfg.MaxHoverAltitudeErrorM, 0.30)
	cfg.MaxHoverYawDriftRad = defaultFloat(cfg.MaxHoverYawDriftRad, 0.45)
	cfg.MaxStopDriftM = defaultFloat(cfg.MaxStopDriftM, 0.25)
	cfg.MinSlamOdomRateHz = defaultFloat(cfg.MinSlamOdomRateHz, 1)
	cfg.MinExternalNavRateHz = defaultFloat(cfg.MinExternalNavRateHz, 5)
	cfg.MinFCULocalPositionRateHz = defaultFloat(cfg.MinFCULocalPositionRateHz, 2)
	cfg.MaxLatestAgeSec = defaultFloat(cfg.MaxLatestAgeSec, 1.5)
	cfg.HoverClaim = defaultString(cfg.HoverClaim, "evaluated")
	cfg.ExplorationClaim = defaultString(cfg.ExplorationClaim, "not_evaluated")
}

func defaultStartupReadinessPolicy(cfg *StartupReadinessPolicyConfig) {
	cfg.TimeoutSec = defaultFloat(cfg.TimeoutSec, 35)
	cfg.GraceSec = defaultFloat(cfg.GraceSec, 8)
	cfg.ProgressWindowSec = defaultFloat(cfg.ProgressWindowSec, 3)
}

func defaultMotionGate(cfg *MotionGateConfig) {
	cfg.SlamOdomTopic = defaultString(cfg.SlamOdomTopic, "/slam/odom")
	cfg.SlamStatusTopic = defaultString(cfg.SlamStatusTopic, "/navlab/slam/status")
	cfg.ExternalNavStatusTopic = defaultString(cfg.ExternalNavStatusTopic, "/external_nav/status")
	cfg.FCUPoseTopic = defaultString(cfg.FCUPoseTopic, "/ap/v1/pose/filtered")
	cfg.FCUTwistTopic = defaultString(cfg.FCUTwistTopic, "/ap/v1/twist/filtered")
	cfg.FCUStatusTopic = defaultString(cfg.FCUStatusTopic, "/ap/v1/status")
	cfg.CmdVelTopic = defaultString(cfg.CmdVelTopic, "/ap/v1/cmd_vel")
	cfg.RangefinderRangeTopic = defaultString(cfg.RangefinderRangeTopic, "/rangefinder/down/range")
	cfg.RangefinderStatusTopic = defaultString(cfg.RangefinderStatusTopic, "/rangefinder/down/status")
	cfg.IMUTopic = defaultString(cfg.IMUTopic, "/imu")
	cfg.ScanTopic = defaultString(cfg.ScanTopic, "/scan")
	cfg.TruthDiagnosticTopic = defaultString(cfg.TruthDiagnosticTopic, "/odometry")
	cfg.ControllerStatusTopic = defaultString(cfg.ControllerStatusTopic, "/navlab/fcu/controller/status")
	cfg.SetpointIntentTopic = defaultString(cfg.SetpointIntentTopic, "/navlab/fcu/setpoint/intent")
	cfg.SetpointOutputTopic = defaultString(cfg.SetpointOutputTopic, "/navlab/fcu/setpoint/output")
	cfg.OwnerStatusTopic = defaultString(cfg.OwnerStatusTopic, "/navlab/fcu/owner/status")
	cfg.HoverStatusTopic = defaultString(cfg.HoverStatusTopic, "/navlab/hover/status")
	cfg.MotionStatusTopic = defaultString(cfg.MotionStatusTopic, "/navlab/motion/status")
	cfg.SettleWindowSec = defaultFloat(cfg.SettleWindowSec, 4)
	cfg.ForwardWindowSec = defaultFloat(cfg.ForwardWindowSec, 4)
	cfg.BackWindowSec = defaultFloat(cfg.BackWindowSec, 4)
	cfg.YawWindowSec = defaultFloat(cfg.YawWindowSec, 3)
	cfg.StopHoldWindowSec = defaultFloat(cfg.StopHoldWindowSec, 5)
	cfg.FinalHoldWindowSec = defaultFloat(cfg.FinalHoldWindowSec, 8)
	cfg.MotionDistanceM = defaultFloat(cfg.MotionDistanceM, 0.40)
	cfg.MotionSpeedMPS = defaultFloat(cfg.MotionSpeedMPS, 0.12)
	cfg.YawScanRad = defaultFloat(cfg.YawScanRad, 0.50)
	cfg.YawRateRadPS = defaultFloat(cfg.YawRateRadPS, 0.20)
	cfg.MinForwardDisplacementM = defaultFloat(cfg.MinForwardDisplacementM, 0.20)
	cfg.MaxForwardDisplacementM = defaultFloat(cfg.MaxForwardDisplacementM, 0.80)
	cfg.MinBackDisplacementM = defaultFloat(cfg.MinBackDisplacementM, 0.20)
	cfg.MaxBackDisplacementM = defaultFloat(cfg.MaxBackDisplacementM, 0.80)
	cfg.MinYawDeltaRad = defaultFloat(cfg.MinYawDeltaRad, 0.25)
	cfg.MaxYawDeltaRad = defaultFloat(cfg.MaxYawDeltaRad, 0.90)
	cfg.MaxLateralErrorM = defaultFloat(cfg.MaxLateralErrorM, 0.30)
	cfg.MaxMotionAltitudeErrorM = defaultFloat(cfg.MaxMotionAltitudeErrorM, 0.30)
	cfg.MaxStopDriftM = defaultFloat(cfg.MaxStopDriftM, 0.25)
	cfg.MinClearanceM = defaultFloat(cfg.MinClearanceM, 0.35)
	cfg.MinSlamOdomRateHz = defaultFloat(cfg.MinSlamOdomRateHz, 1)
	cfg.MinExternalNavRateHz = defaultFloat(cfg.MinExternalNavRateHz, 5)
	cfg.MinFCULocalPositionRateHz = defaultFloat(cfg.MinFCULocalPositionRateHz, 2)
	cfg.MaxLatestAgeSec = defaultFloat(cfg.MaxLatestAgeSec, 1.5)
	cfg.HoverClaim = defaultString(cfg.HoverClaim, "evaluated")
	cfg.MotionClaim = defaultString(cfg.MotionClaim, "evaluated")
	cfg.ExplorationClaim = defaultString(cfg.ExplorationClaim, "not_evaluated")
}

func defaultExplorationGate(cfg *ExplorationGateConfig) {
	cfg.Strategy = defaultString(cfg.Strategy, "frontier_lite")
	cfg.SlamOdomTopic = defaultString(cfg.SlamOdomTopic, "/slam/odom")
	cfg.SlamStatusTopic = defaultString(cfg.SlamStatusTopic, "/navlab/slam/status")
	cfg.ExternalNavStatusTopic = defaultString(cfg.ExternalNavStatusTopic, "/external_nav/status")
	cfg.MapTopic = defaultString(cfg.MapTopic, "/map")
	cfg.SubmapListTopic = defaultString(cfg.SubmapListTopic, "/submap_list")
	cfg.TrajectoryNodeListTopic = defaultString(cfg.TrajectoryNodeListTopic, "/trajectory_node_list")
	cfg.FCUPoseTopic = defaultString(cfg.FCUPoseTopic, "/ap/v1/pose/filtered")
	cfg.FCUTwistTopic = defaultString(cfg.FCUTwistTopic, "/ap/v1/twist/filtered")
	cfg.FCUStatusTopic = defaultString(cfg.FCUStatusTopic, "/ap/v1/status")
	cfg.CmdVelTopic = defaultString(cfg.CmdVelTopic, "/ap/v1/cmd_vel")
	cfg.RangefinderRangeTopic = defaultString(cfg.RangefinderRangeTopic, "/rangefinder/down/range")
	cfg.RangefinderStatusTopic = defaultString(cfg.RangefinderStatusTopic, "/rangefinder/down/status")
	cfg.IMUTopic = defaultString(cfg.IMUTopic, "/imu")
	cfg.ScanTopic = defaultString(cfg.ScanTopic, "/scan")
	cfg.TruthDiagnosticTopic = defaultString(cfg.TruthDiagnosticTopic, "/odometry")
	cfg.ControllerStatusTopic = defaultString(cfg.ControllerStatusTopic, "/navlab/fcu/controller/status")
	cfg.SetpointIntentTopic = defaultString(cfg.SetpointIntentTopic, "/navlab/fcu/setpoint/intent")
	cfg.SetpointOutputTopic = defaultString(cfg.SetpointOutputTopic, "/navlab/fcu/setpoint/output")
	cfg.OwnerStatusTopic = defaultString(cfg.OwnerStatusTopic, "/navlab/fcu/owner/status")
	cfg.HoverStatusTopic = defaultString(cfg.HoverStatusTopic, "/navlab/hover/status")
	cfg.MotionStatusTopic = defaultString(cfg.MotionStatusTopic, "/navlab/motion/status")
	cfg.ExplorationStatusTopic = defaultString(cfg.ExplorationStatusTopic, "/navlab/exploration/status")
	cfg.ExplorationGoalTopic = defaultString(cfg.ExplorationGoalTopic, "/navlab/exploration/goal")
	cfg.ExplorationCoverageTopic = defaultString(cfg.ExplorationCoverageTopic, "/navlab/exploration/coverage")
	cfg.ExplorationFrontiersTopic = defaultString(cfg.ExplorationFrontiersTopic, "/navlab/exploration/frontiers")
	cfg.ExplorationPathTopic = defaultString(cfg.ExplorationPathTopic, "/navlab/exploration/path")
	cfg.ExplorationMarkersTopic = defaultString(cfg.ExplorationMarkersTopic, "/navlab/exploration/markers")
	cfg.SettleWindowSec = defaultFloat(cfg.SettleWindowSec, 4)
	cfg.ExplorationWindowSec = defaultFloat(cfg.ExplorationWindowSec, 26)
	cfg.ForwardProbeWindowSec = defaultFloat(cfg.ForwardProbeWindowSec, 3)
	cfg.YawScanWindowSec = defaultFloat(cfg.YawScanWindowSec, 3)
	cfg.StopHoldWindowSec = defaultFloat(cfg.StopHoldWindowSec, 4)
	cfg.FinalHoldWindowSec = defaultFloat(cfg.FinalHoldWindowSec, 8)
	cfg.MotionSpeedMPS = defaultFloat(cfg.MotionSpeedMPS, 0.10)
	cfg.YawRateRadPS = defaultFloat(cfg.YawRateRadPS, 0.18)
	cfg.MinAcceptedGoals = defaultInt(cfg.MinAcceptedGoals, 3)
	cfg.MinPathLengthM = defaultFloat(cfg.MinPathLengthM, 0.35)
	cfg.MaxStopDriftM = defaultFloat(cfg.MaxStopDriftM, 0.30)
	cfg.MinClearanceM = defaultFloat(cfg.MinClearanceM, 0.35)
	cfg.StuckTimeoutSec = defaultFloat(cfg.StuckTimeoutSec, 8)
	cfg.MinSlamOdomRateHz = defaultFloat(cfg.MinSlamOdomRateHz, 1)
	cfg.MinExternalNavRateHz = defaultFloat(cfg.MinExternalNavRateHz, 5)
	cfg.MinFCULocalPositionRateHz = defaultFloat(cfg.MinFCULocalPositionRateHz, 1.5)
	cfg.MaxLatestAgeSec = defaultFloat(cfg.MaxLatestAgeSec, 1.5)
	cfg.HoverClaim = defaultString(cfg.HoverClaim, "evaluated")
	cfg.MotionClaim = defaultString(cfg.MotionClaim, "evaluated")
	cfg.ExplorationClaim = defaultString(cfg.ExplorationClaim, "evaluated")
}

func defaultNav2(cfg *Nav2Config) {
	if !cfg.Enabled {
		cfg.Enabled = true
	}
	cfg.Profile = defaultString(cfg.Profile, "indoor_2d")
	cfg.GlobalFrame = defaultString(cfg.GlobalFrame, "map")
	cfg.OdomFrame = defaultString(cfg.OdomFrame, "odom")
	cfg.BaseFrame = defaultString(cfg.BaseFrame, "base_link")
	cfg.ScanTopic = defaultString(cfg.ScanTopic, "/scan")
	cfg.MapTopic = defaultString(cfg.MapTopic, "/map")
	cfg.CmdVelTopic = defaultString(cfg.CmdVelTopic, "/cmd_vel_nav")
	cfg.BTXML = defaultString(cfg.BTXML, "navigate_to_pose_w_replanning_and_recovery.xml")
	cfg.PlannerPlugin = defaultString(cfg.PlannerPlugin, "GridBased")
	cfg.ControllerPlugin = defaultString(cfg.ControllerPlugin, "FollowPath")
	if !cfg.UseSimTime {
		cfg.UseSimTime = true
	}
	defaultNav2Costmap(&cfg.Costmap)
}

func defaultNav2Costmap(cfg *Nav2CostmapConfig) {
	cfg.GlobalCostmapTopic = defaultString(cfg.GlobalCostmapTopic, "/global_costmap/costmap")
	cfg.LocalCostmapTopic = defaultString(cfg.LocalCostmapTopic, "/local_costmap/costmap")
	cfg.RequiredLayers = defaultStrings(cfg.RequiredLayers, []string{"static_layer", "obstacle_layer", "inflation_layer"})
	cfg.MaxCostmapAgeSec = defaultFloat(cfg.MaxCostmapAgeSec, 1.5)
	cfg.MinObstacleCells = defaultInt(cfg.MinObstacleCells, 1)
	cfg.MaxUnknownRatio = defaultFloat(cfg.MaxUnknownRatio, 0.35)
	cfg.InflationRadiusM = defaultFloat(cfg.InflationRadiusM, 0.35)
	cfg.FootprintRadiusM = defaultFloat(cfg.FootprintRadiusM, 0.22)
	cfg.HealthTopic = defaultString(cfg.HealthTopic, "/navlab/navigation/costmap_health")
	cfg.CostmapHealthClaim = defaultString(cfg.CostmapHealthClaim, "evaluated")
}

func defaultNavigationAdapter(cfg *NavigationAdapterConfig) {
	cfg.SetpointIntentTopic = defaultString(cfg.SetpointIntentTopic, "/navlab/fcu/setpoint/intent")
	cfg.StatusTopic = defaultString(cfg.StatusTopic, "/navlab/navigation/adapter/status")
	cfg.MaxXYSpeedMPS = defaultFloat(cfg.MaxXYSpeedMPS, 0.25)
	cfg.MaxYawRateDPS = defaultFloat(cfg.MaxYawRateDPS, 35)
	cfg.MaxAccelMPS2 = defaultFloat(cfg.MaxAccelMPS2, 0.35)
	cfg.FixedAltitudeM = defaultFloat(cfg.FixedAltitudeM, 0.8)
	if !cfg.StopOnStaleCostmap {
		cfg.StopOnStaleCostmap = true
	}
	if !cfg.StopOnStaleSlam {
		cfg.StopOnStaleSlam = true
	}
	cfg.AdapterClaim = defaultString(cfg.AdapterClaim, "evaluated")
}

func defaultNavigationMission(cfg *NavigationMissionConfig) {
	cfg.Strategy = defaultString(cfg.Strategy, "bounded_frontier")
	cfg.CompletionPolicy = defaultString(cfg.CompletionPolicy, "land_in_place")
	cfg.GoalFrame = defaultString(cfg.GoalFrame, "map")
	cfg.StatusTopic = defaultString(cfg.StatusTopic, "/navlab/navigation/status")
	cfg.EventsTopic = defaultString(cfg.EventsTopic, "/navlab/navigation/events")
	cfg.GoalTopic = defaultString(cfg.GoalTopic, "/navlab/navigation/goal")
	cfg.PathTopic = defaultString(cfg.PathTopic, "/navlab/navigation/path")
	cfg.RecoveryTopic = defaultString(cfg.RecoveryTopic, "/navlab/navigation/recovery")
	cfg.NavigationWindowSec = defaultFloat(cfg.NavigationWindowSec, 120)
	cfg.MaxGoalRadiusM = defaultFloat(cfg.MaxGoalRadiusM, 0.45)
	cfg.MinClearanceM = defaultFloat(cfg.MinClearanceM, 0.35)
	cfg.MinCoverageGrowth = defaultFloat(cfg.MinCoverageGrowth, 0.50)
	cfg.MinPathLengthM = defaultFloat(cfg.MinPathLengthM, 4.0)
	cfg.MinAcceptedGoals = defaultInt(cfg.MinAcceptedGoals, 3)
	cfg.MaxRecoveryCount = defaultInt(cfg.MaxRecoveryCount, 2)
	cfg.ReturnHomePolicy = defaultString(cfg.ReturnHomePolicy, cfg.CompletionPolicy)
	cfg.NavigationClaim = defaultString(cfg.NavigationClaim, "evaluated")
	if cfg.ExitGoal.ID == "" {
		cfg.ExitGoal = NavigationGoalConfig{ID: "maze_exit", XM: 1.5, YM: -0.5, YawRad: 0.0}
	}
	if len(cfg.BoundedGoals) == 0 {
		cfg.BoundedGoals = []NavigationGoalConfig{
			{ID: "p13_probe_1", XM: 1.0, YM: 0.0, YawRad: 0.0},
			{ID: "p13_probe_2", XM: 1.5, YM: 0.5, YawRad: 0.0},
			{ID: "p13_probe_3", XM: 1.5, YM: -0.5, YawRad: 0.0},
		}
	}
	if cfg.HomeGoal.ID == "" {
		cfg.HomeGoal = NavigationGoalConfig{ID: "home", XM: 0.0, YM: 0.0, YawRad: 0.0}
	}
}

func defaultScanIntegrityGate(cfg *ScanIntegrityGateConfig) {
	cfg.RawScanTopic = defaultString(cfg.RawScanTopic, "/navlab/x2/scan_raw")
	cfg.NormalizedScanTopic = defaultString(cfg.NormalizedScanTopic, "/navlab/x2/scan_normalized")
	cfg.ValidatedScanTopic = defaultString(cfg.ValidatedScanTopic, "/scan")
	cfg.StatusTopic = defaultString(cfg.StatusTopic, "/navlab/scan_integrity/status")
	cfg.EventsTopic = defaultString(cfg.EventsTopic, "/navlab/scan_integrity/events")
	cfg.FaultInjectionTopic = defaultString(cfg.FaultInjectionTopic, "/navlab/scan_integrity/fault_injection")
	cfg.AttitudeSourceTopic = defaultString(cfg.AttitudeSourceTopic, "/imu")
	cfg.AttitudeSourceType = defaultString(cfg.AttitudeSourceType, "imu")
	cfg.RangefinderRangeTopic = defaultString(cfg.RangefinderRangeTopic, "/rangefinder/down/range")
	cfg.IMUTopic = defaultString(cfg.IMUTopic, "/imu")
	cfg.FCUPoseTopic = defaultString(cfg.FCUPoseTopic, "/ap/v1/pose/filtered")
	cfg.ScanSourceTopic = defaultString(cfg.ScanSourceTopic, "/lidar")
	cfg.X2StatusTopic = defaultString(cfg.X2StatusTopic, "/sim/x2/status")
	cfg.BaseFrameID = defaultString(cfg.BaseFrameID, "base_link")
	cfg.ScanFrameID = defaultString(cfg.ScanFrameID, "base_scan")
	cfg.SoftTiltDeg = defaultFloat(cfg.SoftTiltDeg, 3)
	cfg.HardTiltDeg = defaultFloat(cfg.HardTiltDeg, 20)
	cfg.MaxDroppedScanRatio = defaultFloat(cfg.MaxDroppedScanRatio, 0.10)
	cfg.MaxClippedBeamRatio = defaultFloat(cfg.MaxClippedBeamRatio, 0.05)
	cfg.MaxScanAttitudeTimeOffsetMS = defaultFloat(cfg.MaxScanAttitudeTimeOffsetMS, 80)
	cfg.MaxAttitudeSourceAgeMS = defaultFloat(cfg.MaxAttitudeSourceAgeMS, 300)
	cfg.MinAttitudeRateHz = defaultFloat(cfg.MinAttitudeRateHz, 4)
	cfg.FloorHitGuardRangeM = defaultFloat(cfg.FloorHitGuardRangeM, 0.35)
	cfg.MinLidarHeightM = defaultFloat(cfg.MinLidarHeightM, 0.08)
	cfg.MinDownwardRayZ = defaultFloat(cfg.MinDownwardRayZ, -0.35)
	cfg.NormalWindowSec = defaultFloat(cfg.NormalWindowSec, 8)
	cfg.FaultWindowSec = defaultFloat(cfg.FaultWindowSec, 8)
	cfg.HoverClaim = defaultString(cfg.HoverClaim, "evaluated")
	cfg.MotionClaim = defaultString(cfg.MotionClaim, "evaluated")
	cfg.ExplorationClaim = defaultString(cfg.ExplorationClaim, "not_evaluated")
	cfg.ScanIntegrityClaim = defaultString(cfg.ScanIntegrityClaim, "evaluated")
}

func defaultScanStabilization(cfg *ScanStabilizationConfig) {
	if !cfg.Enabled {
		cfg.Enabled = true
	}
	cfg.Mode = defaultString(cfg.Mode, "bounded_2d_projection")
	cfg.InputScanTopic = defaultString(cfg.InputScanTopic, "/navlab/x2/scan_normalized")
	cfg.OutputScanTopic = defaultString(cfg.OutputScanTopic, "/scan")
	cfg.StatusTopic = defaultString(cfg.StatusTopic, "/navlab/scan_stabilization/status")
	cfg.EventsTopic = defaultString(cfg.EventsTopic, "/navlab/scan_stabilization/events")
	cfg.DebugScanTopic = defaultString(cfg.DebugScanTopic, "/navlab/scan_stabilization/debug_scan")
	cfg.FaultInjectionTopic = defaultString(cfg.FaultInjectionTopic, "/navlab/scan_stabilization/fault_injection")
	cfg.AttitudeSourceTopic = defaultString(cfg.AttitudeSourceTopic, "/imu")
	cfg.AttitudeSourceType = defaultString(cfg.AttitudeSourceType, "imu")
	cfg.RangeTopic = defaultString(cfg.RangeTopic, "/rangefinder/down/range")
	cfg.BaseFrameID = defaultString(cfg.BaseFrameID, "base_link")
	cfg.ScanFrameID = defaultString(cfg.ScanFrameID, "base_scan")
	cfg.PassthroughTiltDeg = defaultFloat(cfg.PassthroughTiltDeg, 2)
	cfg.CompensationTiltDeg = defaultFloat(cfg.CompensationTiltDeg, 5)
	cfg.HardDropTiltDeg = defaultFloat(cfg.HardDropTiltDeg, 25)
	cfg.MaxVerticalProjectionErrorM = defaultFloat(cfg.MaxVerticalProjectionErrorM, 0.15)
	cfg.MaxRejectedBeamRatio = defaultFloat(cfg.MaxRejectedBeamRatio, 0.35)
	cfg.MinRetainedBeamRatio = defaultFloat(cfg.MinRetainedBeamRatio, 0.60)
	cfg.MaxFloorHitRiskBeamRatio = defaultFloat(cfg.MaxFloorHitRiskBeamRatio, 0.10)
	cfg.FloorHitGuardRangeM = defaultFloat(cfg.FloorHitGuardRangeM, 0.35)
	cfg.MinLidarHeightM = defaultFloat(cfg.MinLidarHeightM, 0.08)
	cfg.MinDownwardRayZ = defaultFloat(cfg.MinDownwardRayZ, -0.35)
	cfg.MaxScanAttitudeTimeOffsetMS = defaultFloat(cfg.MaxScanAttitudeTimeOffsetMS, 80)
	cfg.MaxAttitudeSourceAgeMS = defaultFloat(cfg.MaxAttitudeSourceAgeMS, 300)
	cfg.MinAttitudeRateHz = defaultFloat(cfg.MinAttitudeRateHz, 4)
	cfg.MinStabilizedScanRateHz = defaultFloat(cfg.MinStabilizedScanRateHz, 5)
	cfg.ScanStabilizationClaim = defaultString(cfg.ScanStabilizationClaim, "evaluated")
}

func defaultScanStabilizationGate(cfg *ScanStabilizationGateConfig) {
	cfg.MotionProfile = defaultString(cfg.MotionProfile, "representative_replay")
	cfg.BaselineMode = defaultString(cfg.BaselineMode, "drop_only")
	cfg.CandidateMode = defaultString(cfg.CandidateMode, "bounded_2d_projection")
	cfg.RawScanTopic = defaultString(cfg.RawScanTopic, "/navlab/x2/scan_raw")
	cfg.NormalizedScanTopic = defaultString(cfg.NormalizedScanTopic, "/navlab/x2/scan_normalized")
	cfg.ValidatedScanTopic = defaultString(cfg.ValidatedScanTopic, "/scan")
	cfg.ScanSourceTopic = defaultString(cfg.ScanSourceTopic, "/lidar")
	cfg.X2StatusTopic = defaultString(cfg.X2StatusTopic, "/sim/x2/status")
	cfg.IMUTopic = defaultString(cfg.IMUTopic, "/imu")
	cfg.FCUPoseTopic = defaultString(cfg.FCUPoseTopic, "/ap/v1/pose/filtered")
	cfg.OfficialMazeLayerRole = defaultString(cfg.OfficialMazeLayerRole, "not_input")
	cfg.HoverClaim = defaultString(cfg.HoverClaim, "evaluated")
	cfg.MotionClaim = defaultString(cfg.MotionClaim, "evaluated")
	cfg.ExplorationClaim = defaultString(cfg.ExplorationClaim, "not_evaluated")
	cfg.ScanStabilizationClaim = defaultString(cfg.ScanStabilizationClaim, "evaluated")
	cfg.ReplayReadinessTimeoutSec = defaultFloat(cfg.ReplayReadinessTimeoutSec, 60)
	cfg.ControllerSummaryTimeoutSec = defaultFloat(cfg.ControllerSummaryTimeoutSec, 20)
}

func defaultAirframeDisturbance(cfg *AirframeDisturbanceConfig) {
	cfg.Profile = defaultString(cfg.Profile, "realistic")
	cfg.InjectionLayer = defaultString(cfg.InjectionLayer, "gazebo_motor_model")
	cfg.Seed = defaultInt(cfg.Seed, 7)
	cfg.MotorCount = defaultInt(cfg.MotorCount, 4)
	cfg.ThrustMultipliers = defaultFloats(cfg.ThrustMultipliers, []float64{1, 1, 1, 1})
	cfg.MaxAbsThrustMultiplierDelta = defaultFloat(cfg.MaxAbsThrustMultiplierDelta, 0.18)
	cfg.ESCLagMS = defaultFloats(cfg.ESCLagMS, []float64{0, 0, 0, 0})
	cfg.ESCLagModel = defaultString(cfg.ESCLagModel, "first_order")
	cfg.MaxESCLagMS = defaultFloat(cfg.MaxESCLagMS, 80)
	cfg.IMUInputTopic = defaultString(cfg.IMUInputTopic, "/imu/raw")
	cfg.IMUOutputTopic = defaultString(cfg.IMUOutputTopic, "/imu")
	cfg.StatusTopic = defaultString(cfg.StatusTopic, "/navlab/airframe_disturbance/status")
	cfg.EventsTopic = defaultString(cfg.EventsTopic, "/navlab/airframe_disturbance/events")
}

func defaultAirframeDisturbanceGate(cfg *AirframeDisturbanceGateConfig) {
	cfg.MotionProfile = defaultString(cfg.MotionProfile, "representative_replay")
	cfg.ScanContract = defaultString(cfg.ScanContract, "stabilized_scan")
	cfg.ProfileSet = defaultStrings(cfg.ProfileSet, []string{"ideal", "realistic"})
	cfg.RequiredProfiles = defaultStrings(cfg.RequiredProfiles, []string{"ideal", "realistic"})
	cfg.FaultProfiles = defaultStrings(cfg.FaultProfiles, []string{"invalid_config"})
	cfg.MaxAbsRollDeg = defaultFloat(cfg.MaxAbsRollDeg, 12)
	cfg.MaxAbsPitchDeg = defaultFloat(cfg.MaxAbsPitchDeg, 12)
	cfg.MaxRMSRollDeg = defaultFloat(cfg.MaxRMSRollDeg, 6)
	cfg.MaxRMSPitchDeg = defaultFloat(cfg.MaxRMSPitchDeg, 6)
	cfg.MaxAttitudeRateDPS = defaultFloat(cfg.MaxAttitudeRateDPS, 120)
	cfg.MaxScanDropRatio = defaultFloat(cfg.MaxScanDropRatio, 0.35)
	cfg.MaxScanCompensatedRatio = defaultFloat(cfg.MaxScanCompensatedRatio, 0.65)
	cfg.MaxFloorHitRejectedRatio = defaultFloat(cfg.MaxFloorHitRejectedRatio, 0.20)
	cfg.MinStabilizedScanRateHz = defaultFloat(cfg.MinStabilizedScanRateHz, 5)
	cfg.MinSlamOdomRateHz = defaultFloat(cfg.MinSlamOdomRateHz, 1)
	cfg.MaxMapArtifactScore = defaultFloat(cfg.MaxMapArtifactScore, 0.35)
	cfg.MaxExternalNavDropoutRatio = defaultFloat(cfg.MaxExternalNavDropoutRatio, 0.20)
	cfg.OfficialMazeLayerRole = defaultString(cfg.OfficialMazeLayerRole, "not_input")
	cfg.FCUStatusTopic = defaultString(cfg.FCUStatusTopic, "/ap/v1/status")
	cfg.FCUStatusModeField = defaultString(cfg.FCUStatusModeField, "mode")
	cfg.FCUModeWindowTopic = defaultString(cfg.FCUModeWindowTopic, "/navlab/airframe_disturbance/fcu_mode_window")
	cfg.RequiredFCUModeName = defaultString(cfg.RequiredFCUModeName, "GUIDED")
	cfg.RequiredFCUModeNumber = defaultInt(cfg.RequiredFCUModeNumber, 4)
	cfg.AirframeDisturbanceClaim = defaultString(cfg.AirframeDisturbanceClaim, "evaluated")
	cfg.HorizontalRecoveryClaim = defaultString(cfg.HorizontalRecoveryClaim, "evaluated")
}

func defaultString(value string, fallback string) string {
	if value == "" {
		return fallback
	}
	return value
}

func defaultFloat(value float64, fallback float64) float64 {
	if value == 0 {
		return fallback
	}
	return value
}

func defaultInt(value int, fallback int) int {
	if value == 0 {
		return fallback
	}
	return value
}

func defaultStrings(value []string, fallback []string) []string {
	if len(value) == 0 {
		return append([]string{}, fallback...)
	}
	return value
}

func defaultFloats(value []float64, fallback []float64) []float64 {
	if len(value) == 0 {
		return append([]float64{}, fallback...)
	}
	return value
}

func imageRepository(cfg *ProjectConfig, key string) string {
	image, ok := cfg.Images[key]
	if !ok {
		return ""
	}
	return image.Repository
}
