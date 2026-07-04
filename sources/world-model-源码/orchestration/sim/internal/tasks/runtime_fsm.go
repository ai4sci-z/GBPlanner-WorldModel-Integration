package tasks

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"time"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
	navfsm "navlab/orchestration-sim/internal/fsm"
	simruntime "navlab/orchestration-sim/internal/runtime"
)

type FSMArtifactRef = navfsm.ArtifactRef

const (
	rosbagReasonMetadataReady         = "rosbag_metadata_ready"
	rosbagReasonMetadataMissingMCAPOK = "rosbag_metadata_missing_mcap_counts_ok"
	rosbagReasonMCAPReadable          = "rosbag_mcap_readable"
	rosbagReasonRequiredTopicsMissing = "rosbag_required_topics_missing"
	rosbagReasonFinalizeTimeout       = "rosbag_finalize_timeout"
	rosbagReasonEvidenceMissing       = "rosbag_evidence_missing"
	rosbagReasonStopFailed            = "rosbag_stop_failed"
	rosbagReasonCompleted             = "rosbag_completed"
	rosbagReasonStarted               = "rosbag_started"
	rosbagReasonStopRequested         = "rosbag_stop_requested"
	rosbagReasonFinalizing            = "rosbag_finalizing"
	rosbagReasonPostTaskGrace         = "rosbag_post_task_grace"
)

func WriteRosbagRecorderFSMArtifacts(artifactDir string, taskID string, runID string, execution RuntimeExecutionResult, gate GateEvaluation) ([]FSMArtifactRef, []GeneratedRuntimeArtifact, error) {
	if len(execution.RosbagHandles) == 0 {
		return nil, nil, nil
	}
	gates := rosbagGateByName(gate.RosbagProfiles)
	refs := make([]FSMArtifactRef, 0, len(execution.RosbagHandles))
	generated := make([]GeneratedRuntimeArtifact, 0, len(execution.RosbagHandles)*2)
	for _, handle := range execution.RosbagHandles {
		rosbagGate := matchRosbagGate(handle, gates, gate.RosbagProfiles)
		baseName := "rosbag_" + sanitizeArtifactName(handle.ServiceName) + "_fsm"
		jsonPath := artifactlayout.Runtime(artifactDir, baseName+".json")
		dotPath := artifactlayout.Runtime(artifactDir, baseName+".dot")
		relJSON := artifactlayout.RuntimeRel(baseName + ".json")
		relDOT := artifactlayout.RuntimeRel(baseName + ".dot")
		summary, dot := BuildRosbagRecorderFSMSummary(taskID, runID, handle, rosbagGate, relJSON, relDOT)
		if err := writeRuntimeFSMJSON(jsonPath, summary); err != nil {
			return nil, nil, err
		}
		if err := os.MkdirAll(filepath.Dir(dotPath), 0o755); err != nil {
			return nil, nil, err
		}
		if err := os.WriteFile(dotPath, []byte(dot), 0o644); err != nil {
			return nil, nil, err
		}
		refs = append(refs, navfsm.ArtifactRef{
			FSMName:           summary.FSMName,
			Scope:             summary.Scope,
			ArtifactPath:      relJSON,
			State:             summary.State,
			OK:                summary.OK,
			Blocked:           summary.Blocked,
			FailureReasonCode: summary.FailureReasonCode,
		})
		generated = append(generated,
			GeneratedRuntimeArtifact{Type: "runtime_fsm", Path: jsonPath},
			GeneratedRuntimeArtifact{Type: "runtime_fsm_dot", Path: dotPath},
		)
	}
	return refs, generated, nil
}

func WritePlannedTaskFSMArtifact(artifactDir string, taskID string, runID string) (FSMArtifactRef, GeneratedRuntimeArtifact, error) {
	baseName := "task_" + sanitizeArtifactName(taskID) + "_fsm"
	jsonPath := artifactlayout.Runtime(artifactDir, baseName+".json")
	relJSON := artifactlayout.RuntimeRel(baseName + ".json")
	summary := BuildTaskFSMSummary(taskID, runID, "planned", true, nil, nil, nil, relJSON)
	if err := writeRuntimeFSMJSON(jsonPath, summary); err != nil {
		return FSMArtifactRef{}, GeneratedRuntimeArtifact{}, err
	}
	return navfsm.ArtifactRef{
			FSMName:           summary.FSMName,
			Scope:             summary.Scope,
			ArtifactPath:      relJSON,
			State:             summary.State,
			OK:                summary.OK,
			Blocked:           summary.Blocked,
			FailureReasonCode: summary.FailureReasonCode,
		},
		GeneratedRuntimeArtifact{Type: "fsm", Path: jsonPath},
		nil
}

func WriteTaskFSMArtifact(artifactDir string, taskID string, runID string, gate GateEvaluation, executionErr error, subFSMs []FSMArtifactRef) (FSMArtifactRef, GeneratedRuntimeArtifact, error) {
	baseName := "task_" + sanitizeArtifactName(taskID) + "_fsm"
	jsonPath := artifactlayout.Runtime(artifactDir, baseName+".json")
	relJSON := artifactlayout.RuntimeRel(baseName + ".json")
	ok := gate.OK && executionErr == nil
	blockers := append([]string(nil), gate.Blockers...)
	if executionErr != nil {
		blockers = append(blockers, "runtime_execution_failed:"+executionErr.Error())
	}
	summary := BuildTaskFSMSummary(taskID, runID, "actual", ok, blockers, &gate, subFSMs, relJSON)
	if err := writeRuntimeFSMJSON(jsonPath, summary); err != nil {
		return FSMArtifactRef{}, GeneratedRuntimeArtifact{}, err
	}
	return navfsm.ArtifactRef{
			FSMName:           summary.FSMName,
			Scope:             summary.Scope,
			ArtifactPath:      relJSON,
			State:             summary.State,
			OK:                summary.OK,
			Blocked:           summary.Blocked,
			FailureReasonCode: summary.FailureReasonCode,
		},
		GeneratedRuntimeArtifact{Type: "fsm", Path: jsonPath},
		nil
}

func BuildTaskFSMSummary(taskID string, runID string, mode string, ok bool, blockers []string, gate *GateEvaluation, subFSMs []FSMArtifactRef, artifactPath string) navfsm.Summary {
	if taskID == "hover" {
		return buildHoverTaskFSMSummary(taskID, runID, mode, ok, blockers, gate, subFSMs, artifactPath)
	}
	return buildDefaultTaskFSMSummary(taskID, runID, mode, ok, blockers, subFSMs, artifactPath)
}

func buildHoverTaskFSMSummary(taskID string, runID string, mode string, ok bool, blockers []string, gate *GateEvaluation, subFSMs []FSMArtifactRef, artifactPath string) navfsm.Summary {
	states := []navfsm.State{
		{State: "runtime_ready"},
		{State: "guided"},
		{State: "armed"},
		{State: "takeoff"},
		{State: "hover_health_hold"},
		{State: "hover_hold"},
		{State: "landing"},
		{State: "disarmed"},
		{State: "completed", Terminal: true},
		{State: "blocked", Terminal: true, Failure: true},
	}
	triggers := []navfsm.Trigger{
		{Trigger: "runtime_ready"},
		{Trigger: "guided_confirmed"},
		{Trigger: "arm_confirmed"},
		{Trigger: "takeoff_confirmed"},
		{Trigger: "hover_health_stable"},
		{Trigger: "hover_hold_started"},
		{Trigger: "landing_started"},
		{Trigger: "disarm_confirmed"},
		{Trigger: "task_completed"},
		{Trigger: "block"},
	}
	rules := []navfsm.Rule{
		{From: "runtime_ready", Trigger: "guided_confirmed", To: "guided"},
		{From: "guided", Trigger: "arm_confirmed", To: "armed"},
		{From: "armed", Trigger: "takeoff_confirmed", To: "takeoff"},
		{From: "takeoff", Trigger: "hover_health_stable", To: "hover_health_hold"},
		{From: "hover_health_hold", Trigger: "hover_hold_started", To: "hover_hold"},
		{From: "hover_hold", Trigger: "landing_started", To: "landing"},
		{From: "landing", Trigger: "disarm_confirmed", To: "disarmed"},
		{From: "disarmed", Trigger: "task_completed", To: "completed"},
		{From: "runtime_ready", Trigger: "block", To: "blocked"},
		{From: "guided", Trigger: "block", To: "blocked"},
		{From: "armed", Trigger: "block", To: "blocked"},
		{From: "takeoff", Trigger: "block", To: "blocked"},
		{From: "hover_health_hold", Trigger: "block", To: "blocked"},
		{From: "hover_hold", Trigger: "block", To: "blocked"},
		{From: "landing", Trigger: "block", To: "blocked"},
		{From: "disarmed", Trigger: "block", To: "blocked"},
	}
	recorder := navfsm.NewRecorder(taskID+"_task", "task", taskID, runID, mode, "runtime_ready", states, triggers, rules)
	recorder.SetArtifactPath(artifactPath)
	recorder.SetEvidence(hoverTaskFSMEvidence(gate))
	recorder.SetDebugArtifacts(nil)
	fireHoverTransition := func(trigger, at, reason string, evidence map[string]any) {
		_ = recorder.Fire(trigger, at, true, reason, evidence, nil)
	}
	if mode == "planned" {
		for _, transition := range []struct {
			trigger string
			reason  string
		}{
			{"guided_confirmed", "guided_ack_planned"},
			{"arm_confirmed", "arm_ack_accepted_planned"},
			{"takeoff_confirmed", "takeoff_ack_and_altitude_planned"},
			{"hover_health_stable", "hover_health_stable_window_planned"},
			{"hover_hold_started", "hover_hold_window_planned"},
			{"landing_started", "landing_policy_planned"},
			{"disarm_confirmed", "landing_and_disarm_planned"},
			{"task_completed", "hover_completed_planned"},
		} {
			fireHoverTransition(transition.trigger, "planned", transition.reason, map[string]any{"dry_run": true})
		}
		recorder.Complete()
		summary := recorder.Summary()
		summary.SubFSMs = append([]navfsm.ArtifactRef(nil), subFSMs...)
		return summary
	}
	history := hoverMissionHistory(gate)
	historyEvidence := map[string]any{"mission_phase_history": history}
	for _, transition := range []struct {
		trigger string
		reason  string
	}{
		{"guided_confirmed", "guided_observed"},
		{"arm_confirmed", "arm_observed"},
		{"takeoff_confirmed", "takeoff_observed"},
		{"hover_health_stable", "hover_health_observed"},
		{"hover_hold_started", "hover_hold_observed"},
		{"landing_started", "landing_observed"},
		{"disarm_confirmed", "disarm_observed"},
		{"task_completed", "hover_completed"},
	} {
		if ok {
			fireHoverTransition(transition.trigger, "", transition.reason, historyEvidence)
		}
	}
	if ok {
		recorder.Complete()
	} else {
		reason := firstBlocker(blockers, "hover_task_blocked")
		_ = recorder.Fire("block", "", false, reason, historyEvidence, nil)
		recorder.Fail("blocked", "block", blockerCode(reason), false, reason, "task")
	}
	summary := recorder.Summary()
	summary.SubFSMs = append([]navfsm.ArtifactRef(nil), subFSMs...)
	return summary
}

func buildDefaultTaskFSMSummary(taskID string, runID string, mode string, ok bool, blockers []string, subFSMs []FSMArtifactRef, artifactPath string) navfsm.Summary {
	recorder := navfsm.NewRecorder(
		taskID+"_task",
		"task",
		taskID,
		runID,
		mode,
		"runtime_ready",
		[]navfsm.State{
			{State: "runtime_ready"},
			{State: "task_body"},
			{State: "completed", Terminal: true},
			{State: "blocked", Terminal: true, Failure: true},
		},
		[]navfsm.Trigger{
			{Trigger: "start_task_body"},
			{Trigger: "task_completed"},
			{Trigger: "block"},
		},
		[]navfsm.Rule{
			{From: "runtime_ready", Trigger: "start_task_body", To: "task_body"},
			{From: "task_body", Trigger: "task_completed", To: "completed"},
			{From: "runtime_ready", Trigger: "block", To: "blocked"},
			{From: "task_body", Trigger: "block", To: "blocked"},
		},
	)
	recorder.SetArtifactPath(artifactPath)
	recorder.SetEvidence(map[string]any{"task_doctor_claim": "default_fsm"})
	if mode == "planned" || ok {
		_ = recorder.Fire("start_task_body", mode, true, "task_body_started", nil, nil)
		_ = recorder.Fire("task_completed", mode, true, "task_completed", nil, nil)
		recorder.Complete()
	} else {
		reason := firstBlocker(blockers, "task_blocked")
		_ = recorder.Fire("block", "", false, reason, map[string]any{"blockers": blockers}, nil)
		recorder.Fail("blocked", "block", blockerCode(reason), false, reason, "task")
	}
	summary := recorder.Summary()
	summary.SubFSMs = append([]navfsm.ArtifactRef(nil), subFSMs...)
	return summary
}

func hoverTaskFSMEvidence(gate *GateEvaluation) map[string]any {
	if gate == nil {
		return map[string]any{"source": "planned_fsm"}
	}
	evidence := map[string]any{
		"gate_ok":  gate.OK,
		"blockers": append([]string(nil), gate.Blockers...),
	}
	if gate.Metrics.HoverMission != nil {
		evidence["mission_phase_state"] = gate.Metrics.HoverMission["mission_phase_state"]
		evidence["mission_phase_blocker"] = gate.Metrics.HoverMission["mission_phase_blocker"]
		evidence["mission_phase_last_transition_reason"] = gate.Metrics.HoverMission["mission_phase_last_transition_reason"]
	}
	return evidence
}

func hoverMissionHistory(gate *GateEvaluation) []any {
	if gate == nil || gate.Metrics.HoverMission == nil {
		return nil
	}
	history, ok := gate.Metrics.HoverMission["mission_phase_history"].([]any)
	if !ok {
		return nil
	}
	return append([]any(nil), history...)
}

func firstBlocker(blockers []string, fallback string) string {
	for _, blocker := range blockers {
		if strings.TrimSpace(blocker) != "" {
			return blocker
		}
	}
	return fallback
}

func BuildRosbagRecorderFSMSummary(taskID string, runID string, handle simruntime.RuntimeHandle, rosbagGate *RosbagGateSummary, artifactPath string, dotPath string) (navfsm.Summary, string) {
	recorder := navfsm.NewRecorder(
		"rosbag_recorder",
		"rosbag",
		taskID,
		runID,
		"actual",
		"idle",
		rosbagRecorderStates(),
		rosbagRecorderTriggers(),
		rosbagRecorderRules(),
	)
	recorder.SetParent(navfsm.ParentRef{FSMName: taskID + "_runtime", Scope: "runtime"})
	recorder.SetArtifactPath(artifactPath)
	recorder.SetDebugArtifacts([]navfsm.DebugArtifact{{Type: "dot_graph", Path: dotPath}})
	recorder.SetEvidence(rosbagHandleEvidence(handle, rosbagGate))

	startedAt := formatTime(handle.StartedAt)
	_ = recorder.Fire("start", startedAt, true, rosbagReasonStarted, map[string]any{
		"backend":        handle.Backend,
		"service_name":   handle.ServiceName,
		"identifier":     handle.Identifier,
		"container_name": handle.ContainerName,
		"log_path":       handle.LogPath,
	}, nil)
	_ = recorder.Fire("started", startedAt, true, rosbagReasonStarted, nil, nil)
	_ = recorder.Fire("task_terminal", handle.StopRequestedAt, true, rosbagReasonPostTaskGrace, nil, nil)
	_ = recorder.Fire("request_stop", handle.StopRequestedAt, true, rosbagReasonStopRequested, map[string]any{
		"stop_signal":      handle.StopSignal,
		"stop_timeout_sec": handle.StopTimeoutSec,
	}, nil)
	_ = recorder.Fire("finalize", handle.StoppedAt, true, rosbagReasonFinalizing, map[string]any{
		"wait_exit_code": handle.WaitExitCode,
	}, nil)

	reason, ok, failureState, failureTrigger := rosbagEvidenceReason(handle, rosbagGate)
	if ok {
		_ = recorder.Fire("verify_evidence", handle.StoppedAt, true, reason, rosbagVerificationEvidence(handle, rosbagGate), rosbagVerificationGuards(handle, rosbagGate))
		_ = recorder.Fire("cleanup", handle.StoppedAt, true, "", nil, nil)
		_ = recorder.Fire("complete", handle.StoppedAt, true, rosbagReasonCompleted, nil, nil)
		recorder.Complete()
		return recorder.Summary(), recorder.DOTGraph()
	}

	if failureTrigger == "" {
		failureTrigger = "fail_evidence_missing"
	}
	_ = recorder.Fire(failureTrigger, handle.StoppedAt, false, reason, rosbagVerificationEvidence(handle, rosbagGate), rosbagVerificationGuards(handle, rosbagGate))
	recorder.Fail(failureState, failureTrigger, reason, false, reason, "rosbag")
	return recorder.Summary(), recorder.DOTGraph()
}

func rosbagRecorderStates() []navfsm.State {
	return []navfsm.State{
		{State: "idle"},
		{State: "starting"},
		{State: "recording"},
		{State: "post_task_grace"},
		{State: "stop_requested"},
		{State: "finalizing"},
		{State: "evidence_verified"},
		{State: "cleanup"},
		{State: "completed", Terminal: true},
		{State: "start_failed", Terminal: true, Failure: true},
		{State: "stop_failed", Terminal: true, Failure: true},
		{State: "finalize_timeout", Terminal: true, Failure: true},
		{State: "evidence_missing", Terminal: true, Failure: true},
		{State: "required_topics_missing", Terminal: true, Failure: true},
		{State: "cleanup_failed", Terminal: true, Failure: true},
	}
}

func rosbagRecorderTriggers() []navfsm.Trigger {
	return []navfsm.Trigger{
		{Trigger: "start"},
		{Trigger: "started"},
		{Trigger: "task_terminal"},
		{Trigger: "request_stop"},
		{Trigger: "finalize"},
		{Trigger: "verify_evidence"},
		{Trigger: "cleanup"},
		{Trigger: "complete"},
		{Trigger: "fail_start"},
		{Trigger: "fail_stop"},
		{Trigger: "fail_finalize_timeout"},
		{Trigger: "fail_evidence_missing"},
		{Trigger: "fail_required_topics_missing"},
		{Trigger: "fail_cleanup"},
	}
}

func rosbagRecorderRules() []navfsm.Rule {
	return []navfsm.Rule{
		{From: "idle", Trigger: "start", To: "starting"},
		{From: "starting", Trigger: "started", To: "recording"},
		{From: "recording", Trigger: "task_terminal", To: "post_task_grace"},
		{From: "post_task_grace", Trigger: "request_stop", To: "stop_requested"},
		{From: "stop_requested", Trigger: "finalize", To: "finalizing"},
		{From: "finalizing", Trigger: "verify_evidence", To: "evidence_verified"},
		{From: "evidence_verified", Trigger: "cleanup", To: "cleanup"},
		{From: "cleanup", Trigger: "complete", To: "completed"},
		{From: "starting", Trigger: "fail_start", To: "start_failed"},
		{From: "stop_requested", Trigger: "fail_stop", To: "stop_failed"},
		{From: "finalizing", Trigger: "fail_stop", To: "stop_failed"},
		{From: "finalizing", Trigger: "fail_finalize_timeout", To: "finalize_timeout"},
		{From: "finalizing", Trigger: "fail_evidence_missing", To: "evidence_missing"},
		{From: "finalizing", Trigger: "fail_required_topics_missing", To: "required_topics_missing"},
		{From: "cleanup", Trigger: "fail_cleanup", To: "cleanup_failed"},
	}
}

func rosbagEvidenceReason(handle simruntime.RuntimeHandle, rosbagGate *RosbagGateSummary) (string, bool, string, string) {
	if strings.Contains(strings.ToLower(handle.FinalizeStatus), "timeout") {
		return rosbagReasonFinalizeTimeout, false, "finalize_timeout", "fail_finalize_timeout"
	}
	if handle.WaitExitCode != nil && *handle.WaitExitCode != 0 && *handle.WaitExitCode != 124 && !handle.FinalizeOK {
		return rosbagReasonStopFailed, false, "stop_failed", "fail_stop"
	}
	if rosbagGate != nil && (len(rosbagGate.MissingRequiredTopics) > 0 || len(rosbagGate.ZeroCountRequiredTopics) > 0) {
		return rosbagReasonRequiredTopicsMissing, false, "required_topics_missing", "fail_required_topics_missing"
	}
	if handle.MetadataPath != "" || (rosbagGate != nil && rosbagGate.MessageCountsSource == "metadata") {
		return rosbagReasonMetadataReady, true, "", ""
	}
	if len(handle.MCAPPaths) > 0 || (rosbagGate != nil && rosbagGate.MessageCountsSource == "mcap_stream" && rosbagGate.OK) {
		if handle.MetadataPath == "" {
			return rosbagReasonMetadataMissingMCAPOK, true, "", ""
		}
		return rosbagReasonMCAPReadable, true, "", ""
	}
	if handle.FinalizeOK {
		return rosbagReasonMCAPReadable, true, "", ""
	}
	return rosbagReasonEvidenceMissing, false, "evidence_missing", "fail_evidence_missing"
}

func rosbagVerificationEvidence(handle simruntime.RuntimeHandle, rosbagGate *RosbagGateSummary) map[string]any {
	evidence := map[string]any{
		"finalize_ok":           handle.FinalizeOK,
		"finalize_status":       handle.FinalizeStatus,
		"metadata_path":         handle.MetadataPath,
		"mcap_paths":            append([]string(nil), handle.MCAPPaths...),
		"message_counts_source": handle.MessageCountsSource,
	}
	if rosbagGate != nil {
		evidence["gate_ok"] = rosbagGate.OK
		evidence["required_topics"] = append([]string(nil), rosbagGate.RequiredTopics...)
		evidence["missing_required_topics"] = append([]string(nil), rosbagGate.MissingRequiredTopics...)
		evidence["zero_count_required_topics"] = append([]string(nil), rosbagGate.ZeroCountRequiredTopics...)
		evidence["gate_message_counts_source"] = rosbagGate.MessageCountsSource
		evidence["gate_mcap_paths"] = append([]string(nil), rosbagGate.MCAPPaths...)
	}
	return evidence
}

func rosbagVerificationGuards(handle simruntime.RuntimeHandle, rosbagGate *RosbagGateSummary) []navfsm.Guard {
	guards := []navfsm.Guard{
		{
			Name:       "finalize_ok",
			OK:         handle.FinalizeOK,
			Required:   true,
			ReasonCode: reasonCodeIf(!handle.FinalizeOK, rosbagReasonFinalizeTimeout),
			Evidence: map[string]any{
				"finalize_status": handle.FinalizeStatus,
			},
		},
		{
			Name:     "metadata_or_mcap_readable",
			OK:       handle.MetadataPath != "" || len(handle.MCAPPaths) > 0 || (rosbagGate != nil && rosbagGate.MessageCountsSource != ""),
			Required: true,
			Evidence: map[string]any{
				"metadata_path": handle.MetadataPath,
				"mcap_paths":    append([]string(nil), handle.MCAPPaths...),
			},
		},
	}
	if rosbagGate != nil {
		ok := len(rosbagGate.MissingRequiredTopics) == 0 && len(rosbagGate.ZeroCountRequiredTopics) == 0
		guards = append(guards, navfsm.Guard{
			Name:       "required_topics_present",
			OK:         ok,
			Required:   true,
			ReasonCode: reasonCodeIf(!ok, rosbagReasonRequiredTopicsMissing),
			Evidence: map[string]any{
				"missing_required_topics":    append([]string(nil), rosbagGate.MissingRequiredTopics...),
				"zero_count_required_topics": append([]string(nil), rosbagGate.ZeroCountRequiredTopics...),
			},
		})
	}
	return guards
}

func rosbagHandleEvidence(handle simruntime.RuntimeHandle, rosbagGate *RosbagGateSummary) map[string]any {
	evidence := map[string]any{
		"backend":               handle.Backend,
		"service_name":          handle.ServiceName,
		"identifier":            handle.Identifier,
		"container_name":        handle.ContainerName,
		"command":               append([]string(nil), handle.Command...),
		"started_at":            formatTime(handle.StartedAt),
		"stop_requested_at":     handle.StopRequestedAt,
		"stopped_at":            handle.StoppedAt,
		"stop_signal":           handle.StopSignal,
		"stop_timeout_sec":      handle.StopTimeoutSec,
		"wait_exit_code":        handle.WaitExitCode,
		"output_path":           handle.OutputPath,
		"host_output_path":      handle.HostOutputPath,
		"metadata_path":         handle.MetadataPath,
		"mcap_paths":            append([]string(nil), handle.MCAPPaths...),
		"message_counts_source": handle.MessageCountsSource,
		"finalize_ok":           handle.FinalizeOK,
		"finalize_status":       handle.FinalizeStatus,
		"finalize_timeout_sec":  handle.FinalizeTimeoutSec,
	}
	if rosbagGate != nil {
		evidence["gate_name"] = rosbagGate.Name
		evidence["gate_ok"] = rosbagGate.OK
		evidence["required_topics"] = append([]string(nil), rosbagGate.RequiredTopics...)
		evidence["message_counts_source"] = firstNonEmpty(handle.MessageCountsSource, rosbagGate.MessageCountsSource)
	}
	return evidence
}

func rosbagGateByName(profiles []RosbagGateSummary) map[string]RosbagGateSummary {
	result := map[string]RosbagGateSummary{}
	for _, profile := range profiles {
		result[profile.Name] = profile
	}
	return result
}

func matchRosbagGate(handle simruntime.RuntimeHandle, byName map[string]RosbagGateSummary, profiles []RosbagGateSummary) *RosbagGateSummary {
	for _, name := range []string{handle.ServiceName, strings.TrimPrefix(handle.ServiceName, "rosbag_")} {
		if profile, ok := byName[name]; ok {
			copy := profile
			return &copy
		}
	}
	if len(profiles) == 1 {
		copy := profiles[0]
		return &copy
	}
	return nil
}

func sanitizeArtifactName(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return "unnamed"
	}
	var builder strings.Builder
	for _, r := range value {
		switch {
		case r >= 'a' && r <= 'z':
			builder.WriteRune(r)
		case r >= 'A' && r <= 'Z':
			builder.WriteRune(r)
		case r >= '0' && r <= '9':
			builder.WriteRune(r)
		default:
			builder.WriteByte('_')
		}
	}
	result := strings.Trim(builder.String(), "_")
	if result == "" {
		return "unnamed"
	}
	return result
}

func formatTime(value time.Time) string {
	if value.IsZero() {
		return ""
	}
	return value.UTC().Format(time.RFC3339Nano)
}

func reasonCodeIf(condition bool, reason string) string {
	if condition {
		return reason
	}
	return ""
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func writeRuntimeFSMJSON(path string, value any) error {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, append(data, '\n'), 0o644)
}
