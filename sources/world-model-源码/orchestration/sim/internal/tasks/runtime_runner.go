package tasks

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
	"navlab/orchestration-sim/internal/config"
	simruntime "navlab/orchestration-sim/internal/runtime"
)

type RuntimeExecutionOptions struct {
	KeepRunning            bool
	WaitForRosbags         bool
	RosbagPostTaskGraceSec float64
	TaskDeadlineSec        float64
	TaskID                 string
	RunID                  string
	ArtifactDir            string
	StartupReadinessPolicy config.StartupReadinessPolicyConfig
	EventSink              RuntimeEventSink
}

const DefaultRosbagPostTaskGraceSec = 5.0

var errTaskRuntimeTimeout = errors.New("task_runtime_timeout")

type runtimeDeadline struct {
	enabled bool
	at      time.Time
}

func runtimeTaskDeadline(started time.Time, options RuntimeExecutionOptions) runtimeDeadline {
	if options.TaskDeadlineSec <= 0 {
		return runtimeDeadline{}
	}
	return runtimeDeadline{enabled: true, at: started.Add(time.Duration(options.TaskDeadlineSec * float64(time.Second)))}
}

func (deadline runtimeDeadline) expired() bool {
	return deadline.enabled && !time.Now().Before(deadline.at)
}

type RuntimeEventSink interface {
	EmitRuntimeEvent(event RuntimeEvent)
}

type RuntimeEvent struct {
	Time        time.Time      `json:"time"`
	TaskID      string         `json:"task_id,omitempty"`
	RunID       string         `json:"run_id,omitempty"`
	Phase       string         `json:"phase"`
	Component   string         `json:"component,omitempty"`
	ComponentID string         `json:"component_id,omitempty"`
	Level       string         `json:"level,omitempty"`
	Message     string         `json:"message,omitempty"`
	Artifact    string         `json:"artifact,omitempty"`
	Payload     map[string]any `json:"payload,omitempty"`
}

type RuntimeExecutionResult struct {
	ServiceHandles []simruntime.RuntimeHandle `json:"service_handles"`
	RosbagHandles  []simruntime.RuntimeHandle `json:"rosbag_handles"`
	ProbeResults   []simruntime.ProbeResult   `json:"probe_results"`
	StopErrors     []string                   `json:"stop_errors,omitempty"`
}

func ExecuteRuntimeSpecs(
	backend simruntime.Backend,
	bundle RuntimeSpecBundle,
	options RuntimeExecutionOptions,
) (RuntimeExecutionResult, error) {
	if backend == nil {
		return RuntimeExecutionResult{}, errors.New("runtime backend is required")
	}
	var result RuntimeExecutionResult
	deadline := runtimeTaskDeadline(time.Now(), options)
	cleanup := func() {
		if options.KeepRunning {
			return
		}
		stopRuntimeHandles(backend, append([]simruntime.RuntimeHandle{}, result.RosbagHandles...), "rosbag", &result, options)
		stopRuntimeHandles(backend, append([]simruntime.RuntimeHandle{}, result.ServiceHandles...), "service", &result, options)
	}
	timeout := func(stage string) (RuntimeExecutionResult, error) {
		err := taskRuntimeTimeoutError(options, stage)
		emitRuntimeTimeout(options, stage)
		writeTaskRuntimeTimeoutMissionSummary(options.ArtifactDir, stage, options.TaskDeadlineSec)
		captureRuntimeHandleLogs(backend, result.ServiceHandles, "task runtime timeout")
		cleanup()
		return result, err
	}

	emitRuntimeEvent(options, RuntimeEvent{Phase: "run.started", Level: "info", Message: "runtime execution started"})
	delayedServices := []simruntime.ServiceSpec{}
	for _, spec := range bundle.Services {
		if shouldDelayUntilStartupReady(spec, bundle, options) {
			delayedServices = append(delayedServices, spec)
			continue
		}
		emitRuntimeEvent(options, componentEvent("service.starting", "service", spec.Name, spec.LogPath, "starting service"))
		handle, err := backend.StartService(spec)
		if err != nil {
			emitRuntimeEvent(options, componentEvent("service.failed", "service", spec.Name, spec.LogPath, err.Error()))
			cleanup()
			emitRuntimeEvent(options, RuntimeEvent{Phase: "run.failed", Level: "error", Message: err.Error()})
			return result, fmt.Errorf("start service %s: %w", spec.Name, err)
		}
		result.ServiceHandles = append(result.ServiceHandles, handle)
		emitRuntimeEvent(options, componentEvent("service.started", "service", spec.Name, handle.LogPath, "service started"))
	}
	if deadline.expired() {
		return timeout("startup_readiness")
	}
	if err := runStartupReadinessMonitor(backend, bundle, &result, options, deadline); err != nil {
		if errors.Is(err, errTaskRuntimeTimeout) {
			return timeout("startup_readiness")
		}
		captureRuntimeHandleLogs(backend, result.ServiceHandles, "startup readiness failure")
		cleanup()
		emitRuntimeEvent(options, RuntimeEvent{Phase: "run.blocked", Level: "error", Message: err.Error()})
		return result, err
	}
	if deadline.expired() {
		return timeout("startup_readiness")
	}
	for _, spec := range delayedServices {
		emitRuntimeEvent(options, componentEvent("service.starting", "service", spec.Name, spec.LogPath, "starting service after startup readiness"))
		handle, err := backend.StartService(spec)
		if err != nil {
			emitRuntimeEvent(options, componentEvent("service.failed", "service", spec.Name, spec.LogPath, err.Error()))
			cleanup()
			emitRuntimeEvent(options, RuntimeEvent{Phase: "run.failed", Level: "error", Message: err.Error()})
			return result, fmt.Errorf("start service %s: %w", spec.Name, err)
		}
		result.ServiceHandles = append(result.ServiceHandles, handle)
		emitRuntimeEvent(options, componentEvent("service.started", "service", spec.Name, handle.LogPath, "service started"))
	}
	for _, spec := range bundle.Rosbags {
		emitRuntimeEvent(options, componentEvent("rosbag.starting", "rosbag", spec.Name, spec.LogPath, "starting rosbag"))
		handle, err := backend.StartRosbag(spec)
		if err != nil {
			emitRuntimeEvent(options, componentEvent("rosbag.failed", "rosbag", spec.Name, spec.LogPath, err.Error()))
			cleanup()
			emitRuntimeEvent(options, RuntimeEvent{Phase: "run.failed", Level: "error", Message: err.Error()})
			return result, fmt.Errorf("start rosbag %s: %w", spec.Name, err)
		}
		result.RosbagHandles = append(result.RosbagHandles, handle)
		event := componentEvent("rosbag.started", "rosbag", spec.Name, handle.LogPath, "rosbag started")
		event.Artifact = spec.OutputPath
		emitRuntimeEvent(options, event)
	}

	probeResults, probeTimedOut, pendingProbes := runProbes(backend, bundle.Probes, options, deadline)
	if probeTimedOut {
		return timeout("probes:" + strings.Join(pendingProbes, ","))
	}
	var probeFailures []string
	for _, probeResult := range probeResults {
		spec := probeResult.Spec
		probe := probeResult.Result
		err := probeResult.Err
		result.ProbeResults = append(result.ProbeResults, probe)
		event := componentEvent("probe.finished", "probe", spec.Name, probe.LogPath, "probe finished")
		event.Payload = map[string]any{"return_code": probe.ReturnCode, "required": spec.Required}
		if err != nil || !probe.OK() {
			event.Phase = "probe.failed"
			event.Level = "warn"
			event.Message = fmt.Sprintf("probe return code %d", probe.ReturnCode)
			if err != nil {
				event.Message = err.Error()
			}
		}
		emitRuntimeEvent(options, event)
		if err != nil && spec.Required {
			probeFailures = append(probeFailures, fmt.Sprintf("%s: %v", spec.Name, err))
			continue
		}
		if spec.Required && !probe.OK() {
			probeFailures = append(probeFailures, fmt.Sprintf("%s: return code %d", spec.Name, probe.ReturnCode))
		}
	}
	if len(probeFailures) > 0 {
		if options.WaitForRosbags {
			if options.RosbagPostTaskGraceSec > 0 {
				waitPostTaskRosbagGrace(result.RosbagHandles, options)
				if err := finalizeRosbags(backend, result.RosbagHandles, options, &result); err != nil {
					cleanup()
					emitRuntimeEvent(options, RuntimeEvent{Phase: "run.failed", Level: "error", Message: err.Error()})
					return result, err
				}
			} else if waitErr := waitForRosbags(backend, result.RosbagHandles, options); waitErr != nil {
				cleanup()
				emitRuntimeEvent(options, RuntimeEvent{Phase: "run.failed", Level: "error", Message: waitErr.Error()})
				return result, waitErr
			}
		}
		captureRuntimeHandleLogs(backend, result.ServiceHandles, "probe failure")
		cleanup()
		err := fmt.Errorf("required probes failed: %s", strings.Join(probeFailures, "; "))
		emitRuntimeEvent(options, RuntimeEvent{Phase: "run.blocked", Level: "error", Message: err.Error()})
		return result, err
	}

	if options.WaitForRosbags {
		if options.RosbagPostTaskGraceSec > 0 {
			waitPostTaskRosbagGrace(result.RosbagHandles, options)
			if err := finalizeRosbags(backend, result.RosbagHandles, options, &result); err != nil {
				cleanup()
				emitRuntimeEvent(options, RuntimeEvent{Phase: "run.failed", Level: "error", Message: err.Error()})
				return result, err
			}
		} else if err := waitForRosbags(backend, result.RosbagHandles, options); err != nil {
			cleanup()
			emitRuntimeEvent(options, RuntimeEvent{Phase: "run.failed", Level: "error", Message: err.Error()})
			return result, err
		}
	}
	cleanup()
	if len(result.StopErrors) > 0 {
		message := fmt.Sprintf("runtime cleanup completed with warnings: %s", strings.Join(result.StopErrors, "; "))
		emitRuntimeEvent(options, RuntimeEvent{Phase: "run.cleanup_warning", Level: "warn", Message: message})
		emitRuntimeEvent(options, RuntimeEvent{Phase: "run.completed", Level: "info", Message: "runtime execution completed"})
		return result, nil
	}
	emitRuntimeEvent(options, RuntimeEvent{Phase: "run.completed", Level: "info", Message: "runtime execution completed"})
	return result, nil
}

type probeRunResult struct {
	Spec   simruntime.ProbeSpec
	Result simruntime.ProbeResult
	Err    error
}

func runProbes(backend simruntime.Backend, probes []simruntime.ProbeSpec, options RuntimeExecutionOptions, deadline runtimeDeadline) ([]probeRunResult, bool, []string) {
	if len(probes) == 0 {
		return nil, false, nil
	}
	results := make([]probeRunResult, 0, len(probes))
	resultCh := make(chan probeRunResult, len(probes))
	pending := map[string]bool{}
	for _, spec := range probes {
		pending[spec.Name] = true
		emitRuntimeEvent(options, componentEvent("probe.running", "probe", spec.Name, spec.LogPath, "running probe"))
		go func(spec simruntime.ProbeSpec) {
			probe, err := backend.RunProbe(spec)
			resultCh <- probeRunResult{Spec: spec, Result: probe, Err: err}
		}(spec)
	}
	for len(results) < len(probes) {
		if deadline.enabled {
			remaining := time.Until(deadline.at)
			if remaining <= 0 {
				return results, true, sortedPendingProbeNames(pending)
			}
			timer := time.NewTimer(remaining)
			select {
			case result := <-resultCh:
				if !timer.Stop() {
					select {
					case <-timer.C:
					default:
					}
				}
				results = append(results, result)
				delete(pending, result.Spec.Name)
			case <-timer.C:
				return results, true, sortedPendingProbeNames(pending)
			}
			continue
		}
		result := <-resultCh
		results = append(results, result)
		delete(pending, result.Spec.Name)
	}
	return results, false, nil
}

func sortedPendingProbeNames(pending map[string]bool) []string {
	names := make([]string, 0, len(pending))
	for name, stillPending := range pending {
		if stillPending {
			names = append(names, name)
		}
	}
	sort.Strings(names)
	return names
}

type startupReadinessRuntimeArtifact struct {
	SchemaVersion       string                         `json:"schemaVersion"`
	Policy              map[string]any                 `json:"policy"`
	FinalDecision       StartupReadinessPolicyDecision `json:"final_decision"`
	Timeline            []startupReadinessSample       `json:"timeline"`
	RestartableServices []string                       `json:"restartable_services"`
	RestartAttempts     int                            `json:"restart_attempts"`
	StartedAt           string                         `json:"started_at"`
	FinishedAt          string                         `json:"finished_at"`
}

type startupReadinessSample struct {
	ElapsedSec             float64 `json:"elapsed_sec"`
	ProbeOK                bool    `json:"probe_ok"`
	RangefinderReady       bool    `json:"rangefinder_ready"`
	RangeSampleOK          bool    `json:"range_sample_ok"`
	RangeInputCount        int     `json:"range_input_count"`
	HeightEstimateOK       bool    `json:"height_estimate_ok"`
	ExternalNavHeightReady bool    `json:"external_nav_height_ready"`
	SerialByteCount        int     `json:"serial_byte_count"`
	SerialFrameCount       int     `json:"serial_frame_count"`
	FailureKind            string  `json:"failure_kind,omitempty"`
}

func shouldDelayUntilStartupReady(spec simruntime.ServiceSpec, bundle RuntimeSpecBundle, options RuntimeExecutionOptions) bool {
	return startupReadinessMonitorEnabled(bundle, options) && spec.Name == "hover_mission"
}

func startupReadinessMonitorEnabled(bundle RuntimeSpecBundle, options RuntimeExecutionOptions) bool {
	return options.TaskID == "hover" && bundle.StartupReadinessProbe != nil && strings.TrimSpace(options.ArtifactDir) != ""
}

func runStartupReadinessMonitor(backend simruntime.Backend, bundle RuntimeSpecBundle, result *RuntimeExecutionResult, options RuntimeExecutionOptions, deadline runtimeDeadline) error {
	if !startupReadinessMonitorEnabled(bundle, options) {
		return nil
	}
	policy := options.StartupReadinessPolicy
	_ = config.NormalizeStartupReadinessPolicy(&policy)
	started := time.Now().UTC()
	artifact := startupReadinessRuntimeArtifact{
		SchemaVersion:       "navlab.startup_readiness_runtime.v1",
		Policy:              startupReadinessPolicySummary(policy),
		RestartableServices: restartableServiceNames(bundle.Services),
		StartedAt:           started.Format(time.RFC3339Nano),
	}
	artifactPath := artifactlayout.Audit(options.ArtifactDir, "startup_readiness_runtime.json")
	emitRuntimeEvent(options, RuntimeEvent{Phase: "startup_readiness.monitoring", Level: "info", Artifact: artifactPath, Message: "monitoring startup readiness"})
	var previous *startupReadinessSample
	restartAttempts := 0
	for {
		if deadline.expired() {
			artifact.FinalDecision = StartupReadinessPolicyDecision{
				Action:        StartupReadinessActionFailFast,
				Reason:        "task_runtime_timeout",
				SafeToRestart: false,
				Policy:        startupReadinessPolicySummary(policy),
			}
			artifact.RestartAttempts = restartAttempts
			writeStartupReadinessRuntimeArtifact(artifactPath, artifact)
			return errTaskRuntimeTimeout
		}
		elapsed := time.Since(started).Seconds()
		sample := collectStartupReadinessSample(backend, *bundle.StartupReadinessProbe, options.ArtifactDir, elapsed)
		artifact.Timeline = append(artifact.Timeline, sample)
		if startupReadinessSampleReady(sample) {
			artifact.FinalDecision = StartupReadinessPolicyDecision{
				Action:        StartupReadinessActionProceed,
				Reason:        StartupReadinessReasonReady,
				SafeToRestart: true,
				Policy:        startupReadinessPolicySummary(policy),
			}
			artifact.RestartAttempts = restartAttempts
			writeStartupReadinessRuntimeArtifact(artifactPath, artifact)
			emitRuntimeEvent(options, RuntimeEvent{Phase: "startup_readiness.ready", Level: "info", Artifact: artifactPath, Message: "startup readiness satisfied"})
			return nil
		}
		evidence := startupReadinessEvidenceFromSamples(previous, sample, policy, restartAttempts)
		decision := DecideStartupReadinessPolicyAction(policy, evidence)
		artifact.FinalDecision = decision
		artifact.RestartAttempts = restartAttempts
		writeStartupReadinessRuntimeArtifact(artifactPath, artifact)
		switch decision.Action {
		case StartupReadinessActionWaitLonger:
			previous = &sample
			time.Sleep(time.Duration(policy.ProgressWindowSec * float64(time.Second)))
			continue
		case StartupReadinessActionRestartLeaf:
			if err := restartStartupReadinessLeafServices(backend, bundle.Services, result, options); err != nil {
				artifact.FinalDecision = StartupReadinessPolicyDecision{
					Action:        StartupReadinessActionFailFast,
					Reason:        "startup_readiness_restart_failed:" + err.Error(),
					SafeToRestart: true,
					Policy:        startupReadinessPolicySummary(policy),
				}
				writeStartupReadinessRuntimeArtifact(artifactPath, artifact)
				return fmt.Errorf("startup readiness restart failed: %w", err)
			}
			restartAttempts++
			previous = nil
			continue
		default:
			writeStartupReadinessMissionSummary(options.ArtifactDir, decision)
			return fmt.Errorf("startup readiness blocked: %s", decision.Reason)
		}
	}
}

func collectStartupReadinessSample(backend simruntime.Backend, probe simruntime.ProbeSpec, artifactDir string, elapsed float64) startupReadinessSample {
	result, err := backend.RunProbe(probe)
	payload := readStartupProbePayload(probe.OutputPath, result.Stdout)
	sample := startupReadinessSample{
		ElapsedSec: roundSeconds(elapsed),
		ProbeOK:    err == nil && result.OK(),
	}
	if payload == nil {
		sample.FailureKind = "startup_readiness_probe_missing"
		return sample
	}
	samples := mapFromAny(payload["samples"])
	rangeStatus := mapFromAny(mapFromAny(samples["/rangefinder/down/status"])["parsed"])
	rangeSample := mapFromAny(samples["/rangefinder/down/range"])
	heightSample := mapFromAny(samples["/height/estimate"])
	externalNav := mapFromAny(mapFromAny(samples["/external_nav/status"])["parsed"])
	height := mapFromAny(externalNav["height"])
	sample.RangefinderReady = boolFromMap(rangeStatus, "ready")
	sample.RangeInputCount = metricInt(rangeStatus, "input_count")
	sample.RangeSampleOK = boolFromMap(rangeSample, "ok")
	sample.HeightEstimateOK = boolFromMap(heightSample, "ok")
	sample.ExternalNavHeightReady = boolFromMap(height, "ready")
	if serial := parseBenewakeTFMiniRuntimeLog(artifactlayout.RuntimeLog(artifactDir, "benewake_tfmini_serial.runtime.log")); serial != nil {
		sample.SerialByteCount = metricInt(serial, "byte_count")
		sample.SerialFrameCount = metricInt(serial, "frame_count")
	}
	if !sample.RangefinderReady {
		sample.FailureKind = "startup_readiness_rangefinder_not_ready"
	}
	if !sample.HeightEstimateOK && !sample.ExternalNavHeightReady {
		sample.FailureKind = "startup_readiness_height_not_ready"
	}
	return sample
}

func readStartupProbePayload(path string, stdout string) map[string]any {
	for _, raw := range []string{stdout, readFileString(path)} {
		raw = strings.TrimSpace(raw)
		if raw == "" {
			continue
		}
		payload := map[string]any{}
		if err := json.Unmarshal([]byte(raw), &payload); err == nil {
			return payload
		}
	}
	return nil
}

func readFileString(path string) string {
	data, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	return string(data)
}

func startupReadinessSampleReady(sample startupReadinessSample) bool {
	return sample.RangefinderReady && sample.RangeSampleOK && (sample.HeightEstimateOK || sample.ExternalNavHeightReady)
}

func startupReadinessEvidenceFromSamples(previous *startupReadinessSample, sample startupReadinessSample, policy config.StartupReadinessPolicyConfig, restartAttempts int) StartupReadinessEvidence {
	evidence := StartupReadinessEvidence{
		MissionElapsedSec:      sample.ElapsedSec,
		RestartAttempts:        restartAttempts,
		RangefinderReady:       sample.RangefinderReady,
		RangeSampleOK:          sample.RangeSampleOK,
		HeightEstimateOK:       sample.HeightEstimateOK,
		ExternalNavHeightReady: sample.ExternalNavHeightReady,
	}
	if previous != nil {
		evidence.SerialByteDelta = sample.SerialByteCount - previous.SerialByteCount
		evidence.SerialFrameDelta = sample.SerialFrameCount - previous.SerialFrameCount
		evidence.RangeInputDelta = sample.RangeInputCount - previous.RangeInputCount
		if sample.RangeSampleOK && !previous.RangeSampleOK {
			evidence.RangeSampleDelta = 1
		}
		if sample.HeightEstimateOK && !previous.HeightEstimateOK {
			evidence.HeightEstimateDelta = 1
		}
	}
	return evidence
}

func restartStartupReadinessLeafServices(backend simruntime.Backend, services []simruntime.ServiceSpec, result *RuntimeExecutionResult, options RuntimeExecutionOptions) error {
	for _, spec := range services {
		if !spec.Restartable {
			continue
		}
		handleIndex := runtimeHandleIndex(result.ServiceHandles, spec.Name)
		if handleIndex >= 0 {
			handle := result.ServiceHandles[handleIndex]
			emitRuntimeEvent(options, componentEvent("startup_readiness.restart_stopping", "service", spec.Name, handle.LogPath, "stopping startup readiness leaf service"))
			if err := backend.Stop(handle); err != nil {
				return err
			}
			result.ServiceHandles = append(result.ServiceHandles[:handleIndex], result.ServiceHandles[handleIndex+1:]...)
		}
		emitRuntimeEvent(options, componentEvent("startup_readiness.restart_starting", "service", spec.Name, spec.LogPath, "restarting startup readiness leaf service"))
		handle, err := backend.StartService(spec)
		if err != nil {
			return err
		}
		result.ServiceHandles = append(result.ServiceHandles, handle)
	}
	return nil
}

func runtimeHandleIndex(handles []simruntime.RuntimeHandle, serviceName string) int {
	for index, handle := range handles {
		if handle.ServiceName == serviceName {
			return index
		}
	}
	return -1
}

func restartableServiceNames(services []simruntime.ServiceSpec) []string {
	names := []string{}
	for _, spec := range services {
		if spec.Restartable {
			names = append(names, spec.Name)
		}
	}
	return names
}

func writeStartupReadinessRuntimeArtifact(path string, artifact startupReadinessRuntimeArtifact) {
	artifact.FinishedAt = time.Now().UTC().Format(time.RFC3339Nano)
	data, err := json.MarshalIndent(artifact, "", "  ")
	if err != nil {
		return
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return
	}
	_ = os.WriteFile(path, append(data, '\n'), 0o644)
}

func writeStartupReadinessMissionSummary(artifactDir string, decision StartupReadinessPolicyDecision) {
	if strings.TrimSpace(artifactDir) == "" {
		return
	}
	path := filepath.Join(artifactDir, "mission_summary.json")
	if _, err := os.Stat(path); err == nil {
		return
	}
	payload := map[string]any{
		"ok":                       false,
		"reason":                   "startup_readiness_failed",
		"mission_abort_reason":     decision.Reason,
		"mission_phase_state":      "S1 wait_nav_ready",
		"mission_phase_blocker":    decision.Reason,
		"phases_seen":              []string{"wait_nav_ready"},
		"airborne_seen":            false,
		"hover_hold_seen":          false,
		"startup_readiness_action": decision.Action,
		"startup_readiness_reason": decision.Reason,
	}
	data, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return
	}
	_ = os.WriteFile(path, append(data, '\n'), 0o644)
}

func roundSeconds(value float64) float64 {
	return float64(int(value*1000)) / 1000
}

func waitForRosbags(backend simruntime.Backend, handles []simruntime.RuntimeHandle, options RuntimeExecutionOptions) error {
	for _, handle := range handles {
		emitRuntimeEvent(options, componentEvent("rosbag.waiting", "rosbag", handle.ServiceName, handle.LogPath, "waiting for rosbag"))
		code, err := backend.Wait(handle)
		if err != nil {
			captureRuntimeLogs(backend, handle, "wait error")
			emitRuntimeEvent(options, componentEvent("rosbag.failed", "rosbag", handle.ServiceName, handle.LogPath, err.Error()))
			return fmt.Errorf("wait rosbag %s: %w", handle.ServiceName, err)
		}
		if code != 0 && code != 124 {
			err := fmt.Errorf("wait rosbag %s: return code %d", handle.ServiceName, code)
			captureRuntimeLogs(backend, handle, "wait return code "+fmt.Sprint(code))
			emitRuntimeEvent(options, componentEvent("rosbag.failed", "rosbag", handle.ServiceName, handle.LogPath, err.Error()))
			return err
		}
		event := componentEvent("rosbag.finished", "rosbag", handle.ServiceName, handle.LogPath, "rosbag finished")
		event.Payload = map[string]any{"return_code": code}
		emitRuntimeEvent(options, event)
	}
	return nil
}

func waitPostTaskRosbagGrace(handles []simruntime.RuntimeHandle, options RuntimeExecutionOptions) {
	if len(handles) == 0 || options.RosbagPostTaskGraceSec <= 0 {
		return
	}
	emitRuntimeEvent(options, RuntimeEvent{
		Phase:   "rosbag.post_task_grace",
		Level:   "info",
		Message: fmt.Sprintf("waiting %.1fs after task completion before stopping rosbag", options.RosbagPostTaskGraceSec),
		Payload: map[string]any{"grace_sec": options.RosbagPostTaskGraceSec},
	})
	time.Sleep(time.Duration(options.RosbagPostTaskGraceSec * float64(time.Second)))
}

func finalizeRosbags(backend simruntime.Backend, handles []simruntime.RuntimeHandle, options RuntimeExecutionOptions, result *RuntimeExecutionResult) error {
	finalizer, ok := backend.(simruntime.RosbagFinalizer)
	if !ok {
		return nil
	}
	for index, handle := range handles {
		emitRuntimeEvent(options, componentEvent("rosbag.finalizing", "rosbag", handle.ServiceName, handle.LogPath, "finalizing rosbag"))
		updated, err := finalizer.FinalizeRosbag(handle)
		if index < len(result.RosbagHandles) {
			result.RosbagHandles[index] = updated
		}
		if err != nil {
			captureRuntimeLogs(backend, updated, "rosbag finalize error")
			emitRuntimeEvent(options, componentEvent("rosbag.finalize_failed", "rosbag", handle.ServiceName, handle.LogPath, err.Error()))
			return fmt.Errorf("finalize rosbag %s: %w", handle.ServiceName, err)
		}
		event := componentEvent("rosbag.finalized", "rosbag", updated.ServiceName, updated.LogPath, "rosbag finalized")
		event.Payload = map[string]any{
			"finalize_ok":     updated.FinalizeOK,
			"finalize_status": updated.FinalizeStatus,
			"stop_signal":     updated.StopSignal,
			"wait_exit_code":  updated.WaitExitCode,
			"metadata_path":   updated.MetadataPath,
			"mcap_paths":      updated.MCAPPaths,
		}
		emitRuntimeEvent(options, event)
	}
	return nil
}

func taskRuntimeTimeoutError(options RuntimeExecutionOptions, stage string) error {
	if stage == "" {
		stage = "runtime"
	}
	return fmt.Errorf("%w after %.1fs during %s", errTaskRuntimeTimeout, options.TaskDeadlineSec, stage)
}

func emitRuntimeTimeout(options RuntimeExecutionOptions, stage string) {
	emitRuntimeEvent(options, RuntimeEvent{
		Phase:   "run.timeout",
		Level:   "error",
		Message: taskRuntimeTimeoutError(options, stage).Error(),
		Payload: map[string]any{
			"deadline_sec": options.TaskDeadlineSec,
			"stage":        stage,
		},
	})
}

func writeTaskRuntimeTimeoutMissionSummary(artifactDir string, stage string, deadlineSec float64) {
	if strings.TrimSpace(artifactDir) == "" {
		return
	}
	path := filepath.Join(artifactDir, "mission_summary.json")
	if _, err := os.Stat(path); err == nil {
		return
	}
	payload := map[string]any{
		"ok":                    false,
		"reason":                "task_runtime_timeout",
		"mission_abort_reason":  "task_runtime_timeout",
		"mission_phase_state":   "S_timeout",
		"mission_phase_blocker": "task_runtime_timeout",
		"phases_seen":           []string{},
		"airborne_seen":         false,
		"hover_hold_seen":       false,
		"task_deadline_sec":     deadlineSec,
		"timeout_stage":         stage,
	}
	data, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return
	}
	_ = os.WriteFile(path, append(data, '\n'), 0o644)
}

func captureRuntimeLogs(backend simruntime.Backend, handle simruntime.RuntimeHandle, reason string) {
	if strings.TrimSpace(handle.LogPath) == "" {
		return
	}
	logs, err := backend.Logs(handle, 400)
	if err != nil {
		logs = "failed to collect docker logs: " + err.Error()
	}
	text := "\n--- container logs after " + reason + " ---\n" + logs
	if err := os.MkdirAll(filepath.Dir(handle.LogPath), 0o755); err != nil {
		return
	}
	file, err := os.OpenFile(handle.LogPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return
	}
	defer func() { _ = file.Close() }()
	_, _ = file.WriteString(text)
}

func captureRuntimeHandleLogs(backend simruntime.Backend, handles []simruntime.RuntimeHandle, reason string) {
	for _, handle := range handles {
		captureRuntimeLogs(backend, handle, reason)
	}
}

func stopRuntimeHandles(backend simruntime.Backend, handles []simruntime.RuntimeHandle, component string, result *RuntimeExecutionResult, options RuntimeExecutionOptions) {
	for left, right := 0, len(handles)-1; left < right; left, right = left+1, right-1 {
		handles[left], handles[right] = handles[right], handles[left]
	}
	for _, handle := range handles {
		emitRuntimeEvent(options, componentEvent(component+".stopping", component, handle.ServiceName, handle.LogPath, "stopping "+component))
		if err := backend.Stop(handle); err != nil {
			result.StopErrors = append(result.StopErrors, fmt.Sprintf("%s: %v", handle.ServiceName, err))
			emitRuntimeEvent(options, componentEvent(component+".stop_failed", component, handle.ServiceName, handle.LogPath, err.Error()))
			continue
		}
		emitRuntimeEvent(options, componentEvent(component+".stopped", component, handle.ServiceName, handle.LogPath, component+" stopped"))
	}
}

func componentEvent(phase string, component string, componentID string, logPath string, message string) RuntimeEvent {
	return RuntimeEvent{
		Phase:       phase,
		Component:   component,
		ComponentID: componentID,
		Level:       "info",
		Message:     message,
		Artifact:    logPath,
	}
}

func emitRuntimeEvent(options RuntimeExecutionOptions, event RuntimeEvent) {
	if options.EventSink == nil {
		return
	}
	event.Time = time.Now().UTC()
	event.TaskID = options.TaskID
	event.RunID = options.RunID
	options.EventSink.EmitRuntimeEvent(event)
}
