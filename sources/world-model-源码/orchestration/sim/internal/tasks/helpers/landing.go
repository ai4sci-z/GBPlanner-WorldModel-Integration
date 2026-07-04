package helpers

import "sort"

const (
	LandingNotEvaluatedBlocker       = "landing_not_evaluated"
	ReturnHomeRequiredBlocker        = "return_home_required_before_landing_not_satisfied"
	SimulationLandingRequiredBlocker = "simulation_landing_acceptance_not_passed"
	GazeboTruthLandingInputBlocker   = "landing_must_not_use_gazebo_truth_as_input"
	PolicyLandInPlace                = "land_in_place"
	PolicyAPLandModeAfterHover       = "ap_land_mode_after_hover"
	PolicyReturnHomeThenLand         = "return_home_then_land"
	ClaimEvaluated                   = "evaluated"
	ClaimNotEvaluated                = "not_evaluated"
)

type Config struct {
	Enabled                   bool    `json:"enabled"`
	Policy                    string  `json:"policy"`
	DefaultPolicy             string  `json:"default_policy"`
	LandingStatusTopic        string  `json:"landing_status_topic"`
	LandingIntentTopic        string  `json:"landing_intent_topic"`
	HomeSource                string  `json:"home_source"`
	HomeRadiusM               float64 `json:"home_radius_m"`
	PreLandHoldSec            float64 `json:"pre_land_hold_sec"`
	CompletionGraceSec        float64 `json:"completion_grace_sec"`
	MaxReturnHomeDurationSec  float64 `json:"max_return_home_duration_sec"`
	MaxLandingDurationSec     float64 `json:"max_landing_duration_sec"`
	MaxDescentRateMPS         float64 `json:"max_descent_rate_mps"`
	SetpointLookaheadSec      float64 `json:"landing_setpoint_lookahead_sec"`
	TouchdownAltitudeM        float64 `json:"touchdown_altitude_m"`
	TouchdownVerticalSpeedMPS float64 `json:"touchdown_vertical_speed_mps"`
	RequireDisarm             bool    `json:"require_disarm"`
	RequireMotorsSafe         bool    `json:"require_motors_safe"`
	UsesGazeboTruthAsInput    bool    `json:"uses_gazebo_truth_as_input"`
}

type ReturnHome struct {
	Required        bool     `json:"required"`
	OK              bool     `json:"ok"`
	State           string   `json:"state"`
	DistanceToHomeM *float64 `json:"distance_to_home_m"`
	DurationSec     *float64 `json:"duration_sec"`
}

type Landing struct {
	OK                     bool       `json:"ok"`
	Claim                  string     `json:"claim"`
	Policy                 string     `json:"policy"`
	State                  string     `json:"state"`
	ReturnHome             ReturnHome `json:"return_home"`
	LandCommandAccepted    bool       `json:"land_command_accepted"`
	LandingDurationSec     *float64   `json:"landing_duration_sec"`
	LandedConfirmed        bool       `json:"landed_confirmed"`
	TouchdownConfirmed     bool       `json:"touchdown_confirmed"`
	Disarmed               bool       `json:"disarmed"`
	MotorsSafe             bool       `json:"motors_safe"`
	RequireDisarm          bool       `json:"require_disarm"`
	RequireMotorsSafe      bool       `json:"require_motors_safe"`
	UsesGazeboTruthAsInput bool       `json:"uses_gazebo_truth_as_input"`
	Blockers               []string   `json:"blockers"`
}

type Acceptance struct {
	AcceptanceStage             string   `json:"acceptance_stage"`
	LandingClaim                string   `json:"landing_claim"`
	SimulationLandingClaim      string   `json:"simulation_landing_claim"`
	RealLandingClaim            string   `json:"real_landing_claim"`
	LandingConfig               Config   `json:"landing_config"`
	Landing                     Landing  `json:"landing"`
	SimulationLandingAcceptance Gate     `json:"simulation_landing_acceptance"`
	RealLandingAcceptance       Gate     `json:"real_landing_acceptance"`
	Blockers                    []string `json:"blockers"`
	Blocked                     bool     `json:"blocked"`
	OK                          bool     `json:"ok"`
}

type Gate struct {
	OK          bool     `json:"ok"`
	RuntimeMode string   `json:"runtime_mode"`
	State       string   `json:"state,omitempty"`
	Blockers    []string `json:"blockers"`
}

func NormalizePolicy(policy string, defaultPolicy string) string {
	switch policy {
	case PolicyLandInPlace, PolicyAPLandModeAfterHover, PolicyReturnHomeThenLand:
		return policy
	}
	if defaultPolicy == "" {
		return PolicyLandInPlace
	}
	return defaultPolicy
}

func DefaultLanding(config Config) Landing {
	policy := NormalizePolicy(config.Policy, config.DefaultPolicy)
	return Landing{
		OK:     false,
		Claim:  ClaimNotEvaluated,
		Policy: policy,
		State:  "not_started",
		ReturnHome: ReturnHome{
			Required: policy == PolicyReturnHomeThenLand,
			OK:       false,
			State:    "not_started",
		},
		RequireDisarm:          config.RequireDisarm,
		RequireMotorsSafe:      config.RequireMotorsSafe,
		UsesGazeboTruthAsInput: config.UsesGazeboTruthAsInput,
		Blockers:               []string{LandingNotEvaluatedBlocker},
	}
}

func BuildAcceptance(stage string, config Config, landing *Landing, simulationOK bool) Acceptance {
	if stage == "" {
		stage = "simulation"
	}
	value := DefaultLanding(config)
	if landing != nil {
		value = *landing
	}
	value.Policy = NormalizePolicy(value.Policy, config.DefaultPolicy)
	if value.Claim == "" {
		if value.OK {
			value.Claim = ClaimEvaluated
		} else {
			value.Claim = ClaimNotEvaluated
		}
	}
	if value.Blockers == nil {
		value.Blockers = []string{}
	}

	simOK := value.OK
	if stage == "real" {
		simOK = simulationOK
	}
	simBlockers := []string{}
	if !simOK {
		simBlockers = []string{SimulationLandingRequiredBlocker}
	}
	realOK := stage == "real" && value.OK && simOK
	realState := "not_started"
	if stage == "real" {
		if realOK {
			realState = "evaluated"
		} else {
			realState = "blocked"
		}
	}

	blockers := append([]string{}, value.Blockers...)
	if !value.OK {
		blockers = append(blockers, value.Blockers...)
	}
	if (value.Policy == PolicyReturnHomeThenLand || value.ReturnHome.Required) && !value.ReturnHome.OK {
		blockers = append(blockers, ReturnHomeRequiredBlocker)
	}
	if stage == "real" && !simOK {
		blockers = append(blockers, SimulationLandingRequiredBlocker)
	}
	if config.UsesGazeboTruthAsInput {
		blockers = append(blockers, GazeboTruthLandingInputBlocker)
	}
	blockers = uniqueSorted(blockers)

	return Acceptance{
		AcceptanceStage:        stage,
		LandingClaim:           claim(value.OK),
		SimulationLandingClaim: claim(simOK),
		RealLandingClaim:       claim(realOK),
		LandingConfig:          config,
		Landing:                value,
		SimulationLandingAcceptance: Gate{
			OK:          simOK,
			RuntimeMode: "simulation",
			Blockers:    simBlockers,
		},
		RealLandingAcceptance: Gate{
			OK:          realOK,
			RuntimeMode: "real",
			State:       realState,
			Blockers:    realBlockers(stage, realOK, value.Blockers),
		},
		Blockers: blockers,
		Blocked:  len(blockers) > 0,
		OK:       value.OK && len(blockers) == 0,
	}
}

func claim(ok bool) string {
	if ok {
		return ClaimEvaluated
	}
	return ClaimNotEvaluated
}

func realBlockers(stage string, realOK bool, blockers []string) []string {
	if stage == "simulation" || realOK {
		return []string{}
	}
	return append([]string{}, blockers...)
}

func uniqueSorted(values []string) []string {
	seen := map[string]bool{}
	for _, value := range values {
		if value == "" {
			continue
		}
		seen[value] = true
	}
	out := make([]string, 0, len(seen))
	for value := range seen {
		out = append(out, value)
	}
	sort.Strings(out)
	return out
}
