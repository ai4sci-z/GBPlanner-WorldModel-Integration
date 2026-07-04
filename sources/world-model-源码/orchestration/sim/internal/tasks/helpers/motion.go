package helpers

type MotionGateSpec struct {
	SlamOdomTopic        string
	MotionStatusTopic    string
	CmdVelTopic          string
	SetpointOutputTopic  string
	FCUPoseTopic         string
	FCUTwistTopic        string
	TruthDiagnosticTopic string
}

func DefaultMotionGateSpec() MotionGateSpec {
	return MotionGateSpec{
		SlamOdomTopic:        "/slam/odom",
		MotionStatusTopic:    "/navlab/motion/status",
		CmdVelTopic:          "/ap/v1/cmd_vel",
		SetpointOutputTopic:  "/navlab/fcu/setpoint/output",
		FCUPoseTopic:         "/ap/v1/pose/filtered",
		FCUTwistTopic:        "/ap/v1/twist/filtered",
		TruthDiagnosticTopic: "/odometry",
	}
}

func MotionFoxgloveNotes(spec MotionGateSpec) string {
	return "# NavLab motion gate replay notes\n\n" +
		"The motion gate validates forward/back/yaw/stop motion after SLAM hover. It is not an exploration gate.\n\n" +
		"- Fixed frame: `map`.\n" +
		"- Motion status: `" + spec.MotionStatusTopic + "`.\n" +
		"- Setpoint output: `" + spec.SetpointOutputTopic + "`.\n" +
		"- SLAM odom: `" + spec.SlamOdomTopic + "`.\n" +
		"- FCU pose/twist: `" + spec.FCUPoseTopic + "`, `" + spec.FCUTwistTopic + "`.\n" +
		"- Diagnostic truth only: `" + spec.TruthDiagnosticTopic + "`.\n" +
		"- Do not use Gazebo truth as a SLAM, ExternalNav, planning, or control input.\n"
}
