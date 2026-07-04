package tasks

import "navlab/orchestration-sim/internal/config"

const (
	StartupReadinessActionWaitLonger       = "wait_longer"
	StartupReadinessActionProceed          = "proceed"
	StartupReadinessActionFailFast         = "fail_fast"
	StartupReadinessActionRestartLeaf      = "restart_leaf_services"
	StartupReadinessActionFailClosed       = "fail_closed"
	StartupReadinessReasonProgressObserved = "startup_readiness_progress_observed"
	StartupReadinessReasonReady            = "startup_readiness_ready"
	StartupReadinessReasonWithinGrace      = "startup_readiness_within_grace"
	StartupReadinessReasonNoProgress       = "startup_readiness_no_progress"
	StartupReadinessReasonTimeout          = "startup_readiness_timeout"
	StartupReadinessReasonRestartAllowed   = "startup_readiness_prearm_restart_allowed"
	StartupReadinessReasonRestartForbidden = "startup_readiness_restart_forbidden_after_takeoff"
	StartupReadinessReasonRestartExhausted = "startup_readiness_restart_limit_exhausted"
)

type StartupReadinessEvidence struct {
	MissionElapsedSec      float64
	ArmedSeen              bool
	AirborneSeen           bool
	HoverHoldSeen          bool
	RestartAttempts        int
	SerialByteDelta        int
	SerialFrameDelta       int
	RangeInputDelta        int
	RangeSampleDelta       int
	HeightEstimateDelta    int
	RangefinderReady       bool
	RangeSampleOK          bool
	HeightEstimateOK       bool
	ExternalNavHeightReady bool
}

type StartupReadinessPolicyDecision struct {
	Action        string         `json:"action"`
	Reason        string         `json:"reason"`
	SafeToRestart bool           `json:"safe_to_restart"`
	Policy        map[string]any `json:"policy"`
}

func DecideStartupReadinessPolicyAction(
	policy config.StartupReadinessPolicyConfig,
	evidence StartupReadinessEvidence,
) StartupReadinessPolicyDecision {
	_ = config.NormalizeStartupReadinessPolicy(&policy)
	safeToRestart := !evidence.ArmedSeen && !evidence.AirborneSeen && !evidence.HoverHoldSeen
	decision := StartupReadinessPolicyDecision{
		Action:        StartupReadinessActionWaitLonger,
		Reason:        StartupReadinessReasonWithinGrace,
		SafeToRestart: safeToRestart,
		Policy:        startupReadinessPolicySummary(policy),
	}
	if !safeToRestart {
		decision.Action = StartupReadinessActionFailClosed
		decision.Reason = StartupReadinessReasonRestartForbidden
		return decision
	}
	if evidence.RangefinderReady && evidence.RangeSampleOK && (evidence.HeightEstimateOK || evidence.ExternalNavHeightReady) {
		decision.Action = StartupReadinessActionProceed
		decision.Reason = StartupReadinessReasonReady
		return decision
	}
	if startupReadinessProgressObserved(evidence) {
		decision.Action = StartupReadinessActionWaitLonger
		decision.Reason = StartupReadinessReasonProgressObserved
		return decision
	}
	if evidence.MissionElapsedSec >= policy.TimeoutSec {
		decision.Action = StartupReadinessActionFailFast
		decision.Reason = StartupReadinessReasonTimeout
		return decision
	}
	if evidence.MissionElapsedSec < policy.GraceSec {
		return decision
	}
	if evidence.RestartAttempts < policy.RestartLimit {
		decision.Action = StartupReadinessActionRestartLeaf
		decision.Reason = StartupReadinessReasonRestartAllowed
		return decision
	}
	decision.Action = StartupReadinessActionFailFast
	if policy.RestartLimit > 0 {
		decision.Reason = StartupReadinessReasonRestartExhausted
	} else {
		decision.Reason = StartupReadinessReasonNoProgress
	}
	return decision
}

func startupReadinessProgressObserved(evidence StartupReadinessEvidence) bool {
	return evidence.SerialByteDelta > 0 ||
		evidence.SerialFrameDelta > 0 ||
		evidence.RangeInputDelta > 0 ||
		evidence.RangeSampleDelta > 0 ||
		evidence.HeightEstimateDelta > 0
}

func startupReadinessPolicySummary(policy config.StartupReadinessPolicyConfig) map[string]any {
	_ = config.NormalizeStartupReadinessPolicy(&policy)
	return map[string]any{
		"owner":               "go_runtime_config",
		"strategy_layers":     []string{"wait_longer_policy", "fail_fast_policy", "prearm_restart_policy"},
		"timeout_sec":         policy.TimeoutSec,
		"grace_sec":           policy.GraceSec,
		"progress_window_sec": policy.ProgressWindowSec,
		"restart_limit":       policy.RestartLimit,
		"restart_boundary":    "prearm_preairborne_pre_hover_hold_only",
		"runtime_control":     "startup_readiness_monitor_before_hover_mission",
	}
}
