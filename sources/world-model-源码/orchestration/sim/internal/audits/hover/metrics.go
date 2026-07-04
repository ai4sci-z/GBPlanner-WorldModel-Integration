package hover

import "fmt"

type HoverHealthBand string

const (
	HoverHealthGreen  HoverHealthBand = "green"
	HoverHealthYellow HoverHealthBand = "yellow"
	HoverHealthRed    HoverHealthBand = "red"
)

type HoverSourceTier string

const (
	HoverTierARealFlightSafety HoverSourceTier = "real-flight-safety"
	HoverTierBReviewOnly       HoverSourceTier = "sim-review-only"
	HoverTierCLegacyDiagnostic HoverSourceTier = "legacy-diagnostic"
)

type HoverMetricSeverity string

const (
	HoverMetricInfo    HoverMetricSeverity = "info"
	HoverMetricWarning HoverMetricSeverity = "warning"
	HoverMetricHard    HoverMetricSeverity = "hard"
)

type HoverSourceSpec struct {
	Key      string          `json:"key"`
	Topic    string          `json:"topic"`
	Tier     HoverSourceTier `json:"tier"`
	Role     string          `json:"role"`
	Required bool            `json:"required"`
}

type HoverPairSpec struct {
	Key        string          `json:"key"`
	LeftKey    string          `json:"left_key"`
	RightKey   string          `json:"right_key"`
	Tier       HoverSourceTier `json:"tier"`
	ReviewOnly bool            `json:"review_only"`
}

type HoverMetricSpec struct {
	Key         string          `json:"key"`
	Unit        string          `json:"unit"`
	Description string          `json:"description"`
	Tier        HoverSourceTier `json:"tier"`
	TargetMax   float64         `json:"target_max,omitempty"`
	HardMax     float64         `json:"hard_max,omitempty"`
	ReviewOnly  bool            `json:"review_only,omitempty"`
	HardFail    bool            `json:"hard_fail,omitempty"`
}

type HoverMetricValue struct {
	Key         string              `json:"key"`
	Value       float64             `json:"value"`
	Unit        string              `json:"unit"`
	Band        HoverHealthBand     `json:"band"`
	Severity    HoverMetricSeverity `json:"severity"`
	Tier        HoverSourceTier     `json:"tier"`
	TargetMax   float64             `json:"target_max,omitempty"`
	HardMax     float64             `json:"hard_max,omitempty"`
	ReviewOnly  bool                `json:"review_only,omitempty"`
	HardFail    bool                `json:"hard_fail,omitempty"`
	Reason      string              `json:"reason,omitempty"`
	Description string              `json:"description,omitempty"`
	PairKey     string              `json:"pair_key,omitempty"`
}

func (spec HoverMetricSpec) Classify(value float64) HoverMetricValue {
	out := HoverMetricValue{
		Key:         spec.Key,
		Value:       value,
		Unit:        spec.Unit,
		Band:        HoverHealthGreen,
		Severity:    HoverMetricInfo,
		Tier:        spec.Tier,
		TargetMax:   spec.TargetMax,
		HardMax:     spec.HardMax,
		ReviewOnly:  spec.ReviewOnly,
		HardFail:    spec.HardFail,
		Description: spec.Description,
	}
	if spec.HardMax > 0 && value > spec.HardMax {
		if spec.ReviewOnly {
			out.Band = HoverHealthYellow
			out.Severity = HoverMetricWarning
			out.Reason = "review_only_hard_cap_exceeded"
			return out
		}
		out.Band = HoverHealthRed
		out.Severity = HoverMetricHard
		out.Reason = "hard_cap_exceeded"
		return out
	}
	if spec.HardFail && value > spec.HardMax {
		out.Band = HoverHealthRed
		out.Severity = HoverMetricHard
		out.Reason = "hard_fail_metric_positive"
		return out
	}
	if spec.TargetMax > 0 && value > spec.TargetMax {
		out.Band = HoverHealthYellow
		out.Severity = HoverMetricWarning
		out.Reason = "target_exceeded"
	}
	return out
}

var hoverHealthSourceRegistry = []HoverSourceSpec{
	{Key: "slam_odom", Topic: "/slam/odom", Tier: HoverTierARealFlightSafety, Role: "primary direct-route SLAM odometry", Required: true},
	{Key: "external_nav_odom", Topic: "/external_nav/odom", Tier: HoverTierARealFlightSafety, Role: "ExternalNav bridge output sent to MAVLink", Required: true},
	{Key: "fcu_local_position_pose", Topic: "/navlab/fcu/local_position_pose", Tier: HoverTierARealFlightSafety, Role: "FCU EKF local position feedback mirrored to ROS", Required: true},
	{Key: "mavlink_external_nav_status", Topic: "/mavlink_external_nav/status", Tier: HoverTierARealFlightSafety, Role: "MAVLink ExternalNav sender status", Required: true},
	{Key: "gazebo_model_odometry", Topic: "/gazebo/model/odometry", Tier: HoverTierBReviewOnly, Role: "Gazebo model odometry review source"},
	{Key: "gazebo_tf", Topic: "/gazebo/tf", Tier: HoverTierBReviewOnly, Role: "Gazebo dynamic TF review source"},
	{Key: "gazebo_tf_static", Topic: "/gazebo/tf_static", Tier: HoverTierBReviewOnly, Role: "Gazebo static TF review source"},
	{Key: "cartographer_odometry_input", Topic: "/cartographer/odometry_input", Tier: HoverTierCLegacyDiagnostic, Role: "Cartographer odometry prior diagnostic"},
	{Key: "scan_reference_drift_odom", Topic: "/navlab/scan_reference_drift/odom", Tier: HoverTierCLegacyDiagnostic, Role: "legacy scan-reference odometry diagnostic"},
	{Key: "external_nav_odom_candidate", Topic: "/external_nav/odom_candidate", Tier: HoverTierCLegacyDiagnostic, Role: "legacy selector candidate diagnostic"},
}

var hoverHealthPairRegistry = []HoverPairSpec{
	{Key: "slam_vs_external_nav", LeftKey: "slam_odom", RightKey: "external_nav_odom", Tier: HoverTierARealFlightSafety},
	{Key: "external_nav_vs_fcu", LeftKey: "external_nav_odom", RightKey: "fcu_local_position_pose", Tier: HoverTierARealFlightSafety},
	{Key: "slam_vs_fcu", LeftKey: "slam_odom", RightKey: "fcu_local_position_pose", Tier: HoverTierARealFlightSafety},
	{Key: "gazebo_vs_slam", LeftKey: "gazebo_model_odometry", RightKey: "slam_odom", Tier: HoverTierBReviewOnly, ReviewOnly: true},
	{Key: "gazebo_vs_external_nav", LeftKey: "gazebo_model_odometry", RightKey: "external_nav_odom", Tier: HoverTierBReviewOnly, ReviewOnly: true},
	{Key: "gazebo_vs_fcu", LeftKey: "gazebo_model_odometry", RightKey: "fcu_local_position_pose", Tier: HoverTierBReviewOnly, ReviewOnly: true},
}

func hoverHealthPairMetricSpec(pair HoverPairSpec, metricName string) HoverMetricSpec {
	return HoverMetricSpec{
		Key:         fmt.Sprintf("pair.%s.%s", pair.Key, metricName),
		Unit:        "m",
		Description: fmt.Sprintf("%s relative-motion %s", pair.Key, metricName),
		Tier:        pair.Tier,
		TargetMax:   0.10,
		HardMax:     0.15,
		ReviewOnly:  pair.ReviewOnly,
	}
}

func hoverHealthSourceByTopic(topic string) (HoverSourceSpec, bool) {
	for _, spec := range hoverHealthSourceRegistry {
		if spec.Topic == topic {
			return spec, true
		}
	}
	return HoverSourceSpec{}, false
}

func worseHoverBand(left HoverHealthBand, right HoverHealthBand) HoverHealthBand {
	if left == HoverHealthRed || right == HoverHealthRed {
		return HoverHealthRed
	}
	if left == HoverHealthYellow || right == HoverHealthYellow {
		return HoverHealthYellow
	}
	return HoverHealthGreen
}
