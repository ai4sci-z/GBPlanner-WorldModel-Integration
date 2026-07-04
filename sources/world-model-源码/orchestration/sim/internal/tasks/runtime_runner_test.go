package tasks

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
	"navlab/orchestration-sim/internal/config"
	simruntime "navlab/orchestration-sim/internal/runtime"
)

type fakeRuntimeBackend struct {
	events           []string
	failService      string
	probeResults     map[string]simruntime.ProbeResult
	probeSequences   map[string][]simruntime.ProbeResult
	probeErrors      map[string]error
	probeDelays      map[string]time.Duration
	waitReturnCodes  map[string]int
	waitErrors       map[string]error
	stopErrors       map[string]error
	serviceStartTime time.Time
}

type captureEventSink struct {
	events []RuntimeEvent
}

type finalizingFakeRuntimeBackend struct {
	*fakeRuntimeBackend
	finalizeErr error
}

func (sink *captureEventSink) EmitRuntimeEvent(event RuntimeEvent) {
	sink.events = append(sink.events, event)
}

func (backend *fakeRuntimeBackend) StartService(spec simruntime.ServiceSpec) (simruntime.RuntimeHandle, error) {
	backend.events = append(backend.events, "start-service:"+spec.Name)
	if spec.Name == backend.failService {
		return simruntime.RuntimeHandle{}, errors.New("boom")
	}
	return simruntime.RuntimeHandle{
		Backend:     "fake",
		ServiceName: spec.Name,
		Identifier:  spec.Name,
		StartedAt:   backend.serviceStartTime,
		LogPath:     spec.LogPath,
	}, nil
}

func (backend *fakeRuntimeBackend) StartRosbag(spec simruntime.RosbagSpec) (simruntime.RuntimeHandle, error) {
	backend.events = append(backend.events, "start-rosbag:"+spec.Name)
	return simruntime.RuntimeHandle{
		Backend:     "fake",
		ServiceName: spec.Name,
		Identifier:  spec.Name,
		StartedAt:   backend.serviceStartTime,
		LogPath:     spec.LogPath,
	}, nil
}

func (backend *fakeRuntimeBackend) RunProbe(spec simruntime.ProbeSpec) (simruntime.ProbeResult, error) {
	backend.events = append(backend.events, "probe:"+spec.Name)
	if delay := backend.probeDelays[spec.Name]; delay > 0 {
		time.Sleep(delay)
	}
	if sequence := backend.probeSequences[spec.Name]; len(sequence) > 0 {
		result := sequence[0]
		backend.probeSequences[spec.Name] = sequence[1:]
		return result, backend.probeErrors[spec.Name]
	}
	if result, ok := backend.probeResults[spec.Name]; ok {
		return result, backend.probeErrors[spec.Name]
	}
	return simruntime.ProbeResult{Backend: "fake", Name: spec.Name, ReturnCode: 0}, backend.probeErrors[spec.Name]
}

func (backend *fakeRuntimeBackend) Wait(handle simruntime.RuntimeHandle) (int, error) {
	backend.events = append(backend.events, "wait:"+handle.ServiceName)
	return backend.waitReturnCodes[handle.ServiceName], backend.waitErrors[handle.ServiceName]
}

func (backend *fakeRuntimeBackend) Stop(handle simruntime.RuntimeHandle) error {
	backend.events = append(backend.events, "stop:"+handle.ServiceName)
	return backend.stopErrors[handle.ServiceName]
}

func (backend *fakeRuntimeBackend) Logs(handle simruntime.RuntimeHandle, tail int) (string, error) {
	backend.events = append(backend.events, "logs:"+handle.ServiceName)
	return "", nil
}

func (backend *finalizingFakeRuntimeBackend) FinalizeRosbag(handle simruntime.RuntimeHandle) (simruntime.RuntimeHandle, error) {
	backend.events = append(backend.events, "finalize-rosbag:"+handle.ServiceName)
	if backend.finalizeErr != nil {
		handle.FinalizeStatus = "finalize_timeout"
		return handle, backend.finalizeErr
	}
	exitCode := 0
	handle.FinalizeOK = true
	handle.FinalizeStatus = "metadata_ready"
	handle.StopSignal = "SIGINT"
	handle.WaitExitCode = &exitCode
	handle.MetadataPath = "rosbag/metadata.yaml"
	handle.MessageCountsSource = "metadata"
	return handle, nil
}

func TestExecuteRuntimeSpecsStartsRunsWaitsAndCleansUp(t *testing.T) {
	backend := newFakeRuntimeBackend()
	result, err := ExecuteRuntimeSpecs(backend, RuntimeSpecBundle{
		Services: []simruntime.ServiceSpec{
			{Name: "gazebo"},
			{Name: "slam"},
		},
		Rosbags: []simruntime.RosbagSpec{
			{Name: "hover_rosbag"},
		},
		Probes: []simruntime.ProbeSpec{
			{Name: "frame_probe", Required: true},
		},
	}, RuntimeExecutionOptions{WaitForRosbags: true})
	if err != nil {
		t.Fatalf("ExecuteRuntimeSpecs() error = %v", err)
	}
	if len(result.ServiceHandles) != 2 || len(result.RosbagHandles) != 1 || len(result.ProbeResults) != 1 {
		t.Fatalf("result = %#v", result)
	}
	assertEvents(t, backend.events, []string{
		"start-service:gazebo",
		"start-service:slam",
		"start-rosbag:hover_rosbag",
		"probe:frame_probe",
		"wait:hover_rosbag",
		"stop:hover_rosbag",
		"stop:slam",
		"stop:gazebo",
	})
}

func TestExecuteRuntimeSpecsFinalizesRosbagAfterPostTaskGrace(t *testing.T) {
	backend := &finalizingFakeRuntimeBackend{fakeRuntimeBackend: newFakeRuntimeBackend()}
	sink := &captureEventSink{}
	result, err := ExecuteRuntimeSpecs(backend, RuntimeSpecBundle{
		Rosbags: []simruntime.RosbagSpec{{Name: "hover_rosbag"}},
		Probes:  []simruntime.ProbeSpec{{Name: "slam_hover_probe", Required: true}},
	}, RuntimeExecutionOptions{
		WaitForRosbags:         true,
		RosbagPostTaskGraceSec: 0.001,
		TaskID:                 "hover",
		EventSink:              sink,
	})
	if err != nil {
		t.Fatalf("ExecuteRuntimeSpecs() error = %v", err)
	}
	assertEvents(t, backend.events, []string{
		"start-rosbag:hover_rosbag",
		"probe:slam_hover_probe",
		"finalize-rosbag:hover_rosbag",
		"stop:hover_rosbag",
	})
	if len(result.RosbagHandles) != 1 || !result.RosbagHandles[0].FinalizeOK || result.RosbagHandles[0].FinalizeStatus != "metadata_ready" {
		t.Fatalf("rosbag handles = %#v", result.RosbagHandles)
	}
	phases := make([]string, 0, len(sink.events))
	for _, event := range sink.events {
		phases = append(phases, event.Phase)
	}
	for _, want := range []string{"rosbag.post_task_grace", "rosbag.finalizing", "rosbag.finalized"} {
		if !containsString(phases, want) {
			t.Fatalf("phases missing %q: %#v", want, phases)
		}
	}
}

func TestExecuteRuntimeSpecsBlocksOnRosbagFinalizeFailure(t *testing.T) {
	backend := &finalizingFakeRuntimeBackend{
		fakeRuntimeBackend: newFakeRuntimeBackend(),
		finalizeErr:        errors.New("rosbag finalize timeout"),
	}
	logPath := filepath.Join(t.TempDir(), "hover_rosbag.log")
	_, err := ExecuteRuntimeSpecs(backend, RuntimeSpecBundle{
		Rosbags: []simruntime.RosbagSpec{{Name: "hover_rosbag", LogPath: logPath}},
		Probes:  []simruntime.ProbeSpec{{Name: "slam_hover_probe", Required: true}},
	}, RuntimeExecutionOptions{
		WaitForRosbags:         true,
		RosbagPostTaskGraceSec: 0.001,
	})
	if err == nil || !strings.Contains(err.Error(), "finalize rosbag hover_rosbag") {
		t.Fatalf("ExecuteRuntimeSpecs() error = %v, want finalize failure", err)
	}
	assertEvents(t, backend.events, []string{
		"start-rosbag:hover_rosbag",
		"probe:slam_hover_probe",
		"finalize-rosbag:hover_rosbag",
		"logs:hover_rosbag",
		"stop:hover_rosbag",
	})
}

func TestExecuteRuntimeSpecsEmitsRuntimeEvents(t *testing.T) {
	backend := newFakeRuntimeBackend()
	sink := &captureEventSink{}
	logDir := t.TempDir()
	_, err := ExecuteRuntimeSpecs(backend, RuntimeSpecBundle{
		Services: []simruntime.ServiceSpec{{Name: "gazebo", LogPath: filepath.Join(logDir, "gazebo.log")}},
		Rosbags:  []simruntime.RosbagSpec{{Name: "hover_rosbag", LogPath: filepath.Join(logDir, "rosbag.log"), OutputPath: "hover.mcap"}},
		Probes:   []simruntime.ProbeSpec{{Name: "frame_probe", Required: true, LogPath: filepath.Join(logDir, "probe.log")}},
	}, RuntimeExecutionOptions{WaitForRosbags: true, TaskID: "hover", RunID: "run", EventSink: sink})
	if err != nil {
		t.Fatalf("ExecuteRuntimeSpecs() error = %v", err)
	}
	phases := make([]string, 0, len(sink.events))
	for _, event := range sink.events {
		phases = append(phases, event.Phase)
		if event.TaskID != "hover" || event.RunID != "run" {
			t.Fatalf("event task/run = %q/%q", event.TaskID, event.RunID)
		}
	}
	for _, want := range []string{
		"run.started",
		"service.starting",
		"service.started",
		"rosbag.starting",
		"rosbag.started",
		"probe.running",
		"probe.finished",
		"rosbag.waiting",
		"rosbag.finished",
		"rosbag.stopping",
		"service.stopping",
		"run.completed",
	} {
		if !containsString(phases, want) {
			t.Fatalf("phases missing %q: %#v", want, phases)
		}
	}
}

func TestExecuteRuntimeSpecsStopsRosbagAfterPostTaskGrace(t *testing.T) {
	backend := newFakeRuntimeBackend()
	sink := &captureEventSink{}
	_, err := ExecuteRuntimeSpecs(backend, RuntimeSpecBundle{
		Rosbags: []simruntime.RosbagSpec{{Name: "hover_rosbag"}},
		Probes:  []simruntime.ProbeSpec{{Name: "slam_hover_probe", Required: true}},
	}, RuntimeExecutionOptions{
		WaitForRosbags:         true,
		RosbagPostTaskGraceSec: 0.001,
		TaskID:                 "hover",
		EventSink:              sink,
	})
	if err != nil {
		t.Fatalf("ExecuteRuntimeSpecs() error = %v", err)
	}
	assertEvents(t, backend.events, []string{
		"start-rosbag:hover_rosbag",
		"probe:slam_hover_probe",
		"stop:hover_rosbag",
	})
	phases := make([]string, 0, len(sink.events))
	for _, event := range sink.events {
		phases = append(phases, event.Phase)
	}
	if !containsString(phases, "rosbag.post_task_grace") {
		t.Fatalf("phases missing rosbag.post_task_grace: %#v", phases)
	}
}

func TestExecuteRuntimeSpecsTimesOutWhenProbeDoesNotFinishBeforeDeadline(t *testing.T) {
	backend := newFakeRuntimeBackend()
	backend.probeDelays["slam_hover_probe"] = 50 * time.Millisecond
	sink := &captureEventSink{}
	artifactDir := t.TempDir()
	_, err := ExecuteRuntimeSpecs(backend, RuntimeSpecBundle{
		Services: []simruntime.ServiceSpec{{Name: "hover_mission", LogPath: artifactDir + "/hover_mission.log"}},
		Rosbags:  []simruntime.RosbagSpec{{Name: "hover_rosbag"}},
		Probes:   []simruntime.ProbeSpec{{Name: "slam_hover_probe", Required: true}},
	}, RuntimeExecutionOptions{
		WaitForRosbags:  true,
		TaskDeadlineSec: 0.005,
		TaskID:          "hover",
		ArtifactDir:     artifactDir,
		EventSink:       sink,
	})
	if err == nil || !strings.Contains(err.Error(), "task_runtime_timeout") {
		t.Fatalf("ExecuteRuntimeSpecs() error = %v, want task runtime timeout", err)
	}
	assertEvents(t, backend.events, []string{
		"start-service:hover_mission",
		"start-rosbag:hover_rosbag",
		"probe:slam_hover_probe",
		"logs:hover_mission",
		"stop:hover_rosbag",
		"stop:hover_mission",
	})
	phases := make([]string, 0, len(sink.events))
	for _, event := range sink.events {
		phases = append(phases, event.Phase)
	}
	if !containsString(phases, "run.timeout") {
		t.Fatalf("phases missing run.timeout: %#v", phases)
	}
	missionData, readErr := os.ReadFile(filepath.Join(artifactDir, "mission_summary.json"))
	if readErr != nil {
		t.Fatalf("read timeout mission summary: %v", readErr)
	}
	if !strings.Contains(string(missionData), "task_runtime_timeout") {
		t.Fatalf("mission summary missing timeout reason:\n%s", missionData)
	}
}

func TestTaskRuntimeTimeoutSummaryDoesNotOverwritePythonDurationTimeout(t *testing.T) {
	artifactDir := t.TempDir()
	path := filepath.Join(artifactDir, "mission_summary.json")
	existing := `{"ok":false,"reason":"duration_timeout","mission_abort_reason":"duration_timeout"}`
	if err := os.WriteFile(path, []byte(existing+"\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	writeTaskRuntimeTimeoutMissionSummary(artifactDir, "probes:slam_hover_probe", 90)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if strings.TrimSpace(string(data)) != existing {
		t.Fatalf("mission summary overwritten:\n%s", data)
	}
	blockers := hoverMissionBlockers(map[string]any{
		"ok":                   false,
		"reason":               "duration_timeout",
		"mission_abort_reason": "duration_timeout",
	})
	if !stringSliceContains(blockers, "hover_mission_not_ok") ||
		!stringSliceContains(blockers, "hover_mission_abort:duration_timeout") {
		t.Fatalf("duration timeout blockers = %#v", blockers)
	}
}

func TestExecuteRuntimeSpecsDoesNotFailCompletedRunOnCleanupWarning(t *testing.T) {
	backend := newFakeRuntimeBackend()
	backend.stopErrors["slam"] = errors.New("could not kill container")
	sink := &captureEventSink{}

	result, err := ExecuteRuntimeSpecs(backend, RuntimeSpecBundle{
		Services: []simruntime.ServiceSpec{{Name: "slam"}},
		Probes:   []simruntime.ProbeSpec{{Name: "frame_probe", Required: true}},
	}, RuntimeExecutionOptions{EventSink: sink})
	if err != nil {
		t.Fatalf("ExecuteRuntimeSpecs() error = %v, want cleanup warning only", err)
	}
	if len(result.StopErrors) != 1 || !strings.Contains(result.StopErrors[0], "could not kill container") {
		t.Fatalf("StopErrors = %#v", result.StopErrors)
	}
	phases := make([]string, 0, len(sink.events))
	for _, event := range sink.events {
		phases = append(phases, event.Phase)
	}
	if !containsString(phases, "run.cleanup_warning") || !containsString(phases, "run.completed") {
		t.Fatalf("phases = %#v", phases)
	}
}

func TestExecuteRuntimeSpecsFailsRequiredProbeAndCleansUp(t *testing.T) {
	backend := newFakeRuntimeBackend()
	backend.probeResults["frame_probe"] = simruntime.ProbeResult{Backend: "fake", Name: "frame_probe", ReturnCode: 42}
	logPath := t.TempDir() + "/gazebo.log"

	_, err := ExecuteRuntimeSpecs(backend, RuntimeSpecBundle{
		Services: []simruntime.ServiceSpec{{Name: "gazebo", LogPath: logPath}},
		Probes:   []simruntime.ProbeSpec{{Name: "frame_probe", Required: true}},
	}, RuntimeExecutionOptions{})
	if err == nil || !strings.Contains(err.Error(), "required probes failed") {
		t.Fatalf("ExecuteRuntimeSpecs() error = %v, want required probe failure", err)
	}
	assertEvents(t, backend.events, []string{
		"start-service:gazebo",
		"probe:frame_probe",
		"logs:gazebo",
		"stop:gazebo",
	})
}

func TestExecuteRuntimeSpecsDelaysHoverMissionUntilStartupReadiness(t *testing.T) {
	backend := newFakeRuntimeBackend()
	backend.probeResults["startup_readiness_probe"] = simruntime.ProbeResult{
		Backend:    "fake",
		Name:       "startup_readiness_probe",
		ReturnCode: 0,
		Stdout:     startupReadinessProbePayload(true, true, true, 10),
	}
	_, err := ExecuteRuntimeSpecs(backend, RuntimeSpecBundle{
		Services: []simruntime.ServiceSpec{
			{Name: "gazebo_sensor", Restartable: true},
			{Name: "hover_mission"},
		},
		StartupReadinessProbe: &simruntime.ProbeSpec{Name: "startup_readiness_probe"},
	}, RuntimeExecutionOptions{
		TaskID:                 "hover",
		ArtifactDir:            t.TempDir(),
		StartupReadinessPolicy: configStartupReadinessPolicyForTest(0),
	})
	if err != nil {
		t.Fatalf("ExecuteRuntimeSpecs() error = %v", err)
	}
	assertEvents(t, backend.events, []string{
		"start-service:gazebo_sensor",
		"probe:startup_readiness_probe",
		"start-service:hover_mission",
		"stop:hover_mission",
		"stop:gazebo_sensor",
	})
}

func TestExecuteRuntimeSpecsWritesStartupReadinessArtifactAndBlocks(t *testing.T) {
	backend := newFakeRuntimeBackend()
	backend.probeResults["startup_readiness_probe"] = simruntime.ProbeResult{
		Backend:    "fake",
		Name:       "startup_readiness_probe",
		ReturnCode: 20,
		Stdout:     startupReadinessProbePayload(false, false, false, 0),
	}
	artifactDir := t.TempDir()
	_, err := ExecuteRuntimeSpecs(backend, RuntimeSpecBundle{
		Services:              []simruntime.ServiceSpec{{Name: "gazebo_sensor", Restartable: true, LogPath: artifactDir + "/gazebo.log"}, {Name: "hover_mission"}},
		StartupReadinessProbe: &simruntime.ProbeSpec{Name: "startup_readiness_probe"},
	}, RuntimeExecutionOptions{
		TaskID:                 "hover",
		ArtifactDir:            artifactDir,
		StartupReadinessPolicy: configStartupReadinessPolicyForTest(0),
	})
	if err == nil || !strings.Contains(err.Error(), "startup readiness blocked") {
		t.Fatalf("ExecuteRuntimeSpecs() error = %v, want startup readiness blocked", err)
	}
	data, readErr := os.ReadFile(artifactlayout.Audit(artifactDir, "startup_readiness_runtime.json"))
	if readErr != nil {
		t.Fatalf("read startup readiness artifact: %v", readErr)
	}
	text := string(data)
	for _, expected := range []string{"startup_readiness_no_progress", "gazebo_sensor"} {
		if !strings.Contains(text, expected) {
			t.Fatalf("startup readiness artifact missing %q:\n%s", expected, text)
		}
	}
	missionData, missionErr := os.ReadFile(artifactDir + "/mission_summary.json")
	if missionErr != nil {
		t.Fatalf("read mission summary: %v", missionErr)
	}
	if !strings.Contains(string(missionData), "startup_readiness_failed") ||
		!strings.Contains(string(missionData), "startup_readiness_no_progress") {
		t.Fatalf("mission summary missing startup readiness reason:\n%s", missionData)
	}
	assertEvents(t, backend.events, []string{
		"start-service:gazebo_sensor",
		"probe:startup_readiness_probe",
		"probe:startup_readiness_probe",
		"logs:gazebo_sensor",
		"stop:gazebo_sensor",
	})
}

func TestExecuteRuntimeSpecsRestartsLeafBeforeHoverMissionWhenAllowed(t *testing.T) {
	backend := newFakeRuntimeBackend()
	backend.probeSequences["startup_readiness_probe"] = []simruntime.ProbeResult{
		{Backend: "fake", Name: "startup_readiness_probe", ReturnCode: 20, Stdout: startupReadinessProbePayload(false, false, false, 0)},
		{Backend: "fake", Name: "startup_readiness_probe", ReturnCode: 20, Stdout: startupReadinessProbePayload(false, false, false, 0)},
		{Backend: "fake", Name: "startup_readiness_probe", ReturnCode: 0, Stdout: startupReadinessProbePayload(true, true, true, 1)},
	}
	_, err := ExecuteRuntimeSpecs(backend, RuntimeSpecBundle{
		Services:              []simruntime.ServiceSpec{{Name: "gazebo_sensor", Restartable: true}, {Name: "hover_mission"}},
		StartupReadinessProbe: &simruntime.ProbeSpec{Name: "startup_readiness_probe"},
	}, RuntimeExecutionOptions{
		TaskID:                 "hover",
		ArtifactDir:            t.TempDir(),
		StartupReadinessPolicy: configStartupReadinessPolicyForTest(1),
	})
	if err != nil {
		t.Fatalf("ExecuteRuntimeSpecs() error = %v", err)
	}
	assertEvents(t, backend.events, []string{
		"start-service:gazebo_sensor",
		"probe:startup_readiness_probe",
		"probe:startup_readiness_probe",
		"stop:gazebo_sensor",
		"start-service:gazebo_sensor",
		"probe:startup_readiness_probe",
		"start-service:hover_mission",
		"stop:hover_mission",
		"stop:gazebo_sensor",
	})
}

func TestExecuteRuntimeSpecsWaitsForRosbagBeforeProbeFailureCleanup(t *testing.T) {
	backend := newFakeRuntimeBackend()
	backend.probeResults["frame_probe"] = simruntime.ProbeResult{Backend: "fake", Name: "frame_probe", ReturnCode: 42}
	logPath := t.TempDir() + "/gazebo.log"

	_, err := ExecuteRuntimeSpecs(backend, RuntimeSpecBundle{
		Services: []simruntime.ServiceSpec{{Name: "gazebo", LogPath: logPath}},
		Rosbags:  []simruntime.RosbagSpec{{Name: "hover_rosbag"}},
		Probes:   []simruntime.ProbeSpec{{Name: "frame_probe", Required: true}},
	}, RuntimeExecutionOptions{WaitForRosbags: true})
	if err == nil || !strings.Contains(err.Error(), "required probes failed") {
		t.Fatalf("ExecuteRuntimeSpecs() error = %v, want required probe failure", err)
	}
	assertEvents(t, backend.events, []string{
		"start-service:gazebo",
		"start-rosbag:hover_rosbag",
		"probe:frame_probe",
		"wait:hover_rosbag",
		"logs:gazebo",
		"stop:hover_rosbag",
		"stop:gazebo",
	})
}

func TestExecuteRuntimeSpecsCapturesRosbagLogsOnWaitFailure(t *testing.T) {
	backend := newFakeRuntimeBackend()
	backend.waitReturnCodes["hover_rosbag"] = 1
	logPath := t.TempDir() + "/hover_rosbag.log"

	_, err := ExecuteRuntimeSpecs(backend, RuntimeSpecBundle{
		Rosbags: []simruntime.RosbagSpec{{Name: "hover_rosbag", LogPath: logPath}},
	}, RuntimeExecutionOptions{WaitForRosbags: true})
	if err == nil || !strings.Contains(err.Error(), "wait rosbag hover_rosbag") {
		t.Fatalf("ExecuteRuntimeSpecs() error = %v, want rosbag wait failure", err)
	}
	assertEvents(t, backend.events, []string{
		"start-rosbag:hover_rosbag",
		"wait:hover_rosbag",
		"logs:hover_rosbag",
		"stop:hover_rosbag",
	})
}

func TestExecuteRuntimeSpecsCleansUpAfterServiceStartFailure(t *testing.T) {
	backend := newFakeRuntimeBackend()
	backend.failService = "slam"

	_, err := ExecuteRuntimeSpecs(backend, RuntimeSpecBundle{
		Services: []simruntime.ServiceSpec{
			{Name: "gazebo"},
			{Name: "slam"},
		},
	}, RuntimeExecutionOptions{})
	if err == nil || !strings.Contains(err.Error(), "start service slam") {
		t.Fatalf("ExecuteRuntimeSpecs() error = %v, want start service failure", err)
	}
	assertEvents(t, backend.events, []string{
		"start-service:gazebo",
		"start-service:slam",
		"stop:gazebo",
	})
}

func newFakeRuntimeBackend() *fakeRuntimeBackend {
	return &fakeRuntimeBackend{
		probeResults:     map[string]simruntime.ProbeResult{},
		probeSequences:   map[string][]simruntime.ProbeResult{},
		probeErrors:      map[string]error{},
		probeDelays:      map[string]time.Duration{},
		waitReturnCodes:  map[string]int{},
		waitErrors:       map[string]error{},
		stopErrors:       map[string]error{},
		serviceStartTime: time.Date(2026, 6, 12, 1, 2, 3, 0, time.UTC),
	}
}

func configStartupReadinessPolicyForTest(restartLimit int) config.StartupReadinessPolicyConfig {
	return config.StartupReadinessPolicyConfig{
		TimeoutSec:        0.004,
		GraceSec:          0.0005,
		ProgressWindowSec: 0.001,
		RestartLimit:      restartLimit,
	}
}

func startupReadinessProbePayload(rangeReady bool, rangeSampleOK bool, heightReady bool, inputCount int) string {
	readyText := "false"
	if rangeReady {
		readyText = "true"
	}
	rangeOKText := "false"
	rangeReturnCode := "124"
	if rangeSampleOK {
		rangeOKText = "true"
		rangeReturnCode = "0"
	}
	heightOKText := "false"
	if heightReady {
		heightOKText = "true"
	}
	return `{"ok":` + rangeOKText + `,"samples":{` +
		`"/rangefinder/down/status":{"ok":true,"parsed":{"ready":` + readyText + `,"input_count":` + fmt.Sprint(inputCount) + `}},` +
		`"/rangefinder/down/range":{"ok":` + rangeOKText + `,"return_code":` + rangeReturnCode + `},` +
		`"/height/estimate":{"ok":` + heightOKText + `},` +
		`"/external_nav/status":{"ok":true,"parsed":{"height":{"ready":` + heightOKText + `}}}` +
		`}}`
}

func assertEvents(t *testing.T, got []string, want []string) {
	t.Helper()
	if strings.Join(got, "\n") != strings.Join(want, "\n") {
		t.Fatalf("events = %#v, want %#v", got, want)
	}
}

func containsString(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}
