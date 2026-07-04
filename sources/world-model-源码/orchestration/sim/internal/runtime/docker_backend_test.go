package runtime

import (
	"context"
	"errors"
	"io"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"

	dockercontainer "github.com/docker/docker/api/types/container"
	dockernetwork "github.com/docker/docker/api/types/network"
	ocispec "github.com/opencontainers/image-spec/specs-go/v1"
)

type fakeDockerRuntimeClient struct {
	createdName    string
	createdConfig  *dockercontainer.Config
	createdHost    *dockercontainer.HostConfig
	createResponse dockercontainer.CreateResponse
	createErr      error
	started        []string
	startErr       error
	stopped        []dockerStopCall
	stopErr        error
	removed        []string
	removeErr      error
	waitCode       int64
	waitErr        error
	logs           string
	logsErr        error
}

type dockerStopCall struct {
	identifier string
	signal     string
	timeout    *int
}

func (client *fakeDockerRuntimeClient) ContainerCreate(ctx context.Context, config *dockercontainer.Config, hostConfig *dockercontainer.HostConfig, networkingConfig *dockernetwork.NetworkingConfig, platform *ocispec.Platform, containerName string) (dockercontainer.CreateResponse, error) {
	_, _, _ = ctx, networkingConfig, platform
	client.createdName = containerName
	client.createdConfig = config
	client.createdHost = hostConfig
	if client.createErr != nil {
		return dockercontainer.CreateResponse{}, client.createErr
	}
	if client.createResponse.ID == "" {
		client.createResponse.ID = "container-id"
	}
	return client.createResponse, nil
}

func (client *fakeDockerRuntimeClient) ContainerStart(ctx context.Context, containerID string, options dockercontainer.StartOptions) error {
	_, _ = ctx, options
	client.started = append(client.started, containerID)
	return client.startErr
}

func (client *fakeDockerRuntimeClient) ContainerStop(ctx context.Context, containerID string, options dockercontainer.StopOptions) error {
	_ = ctx
	client.stopped = append(client.stopped, dockerStopCall{identifier: containerID, signal: options.Signal, timeout: options.Timeout})
	return client.stopErr
}

func (client *fakeDockerRuntimeClient) ContainerWait(ctx context.Context, containerID string, condition dockercontainer.WaitCondition) (<-chan dockercontainer.WaitResponse, <-chan error) {
	_, _, _ = ctx, containerID, condition
	resultC := make(chan dockercontainer.WaitResponse, 1)
	errC := make(chan error, 1)
	if client.waitErr != nil {
		errC <- client.waitErr
		return resultC, errC
	}
	resultC <- dockercontainer.WaitResponse{StatusCode: client.waitCode}
	return resultC, errC
}

func (client *fakeDockerRuntimeClient) ContainerLogs(ctx context.Context, containerID string, options dockercontainer.LogsOptions) (io.ReadCloser, error) {
	_, _, _ = ctx, containerID, options
	if client.logsErr != nil {
		return nil, client.logsErr
	}
	return io.NopCloser(strings.NewReader(client.logs)), nil
}

func (client *fakeDockerRuntimeClient) ContainerRemove(ctx context.Context, containerID string, options dockercontainer.RemoveOptions) error {
	_, _ = ctx, options
	client.removed = append(client.removed, containerID)
	return client.removeErr
}

func TestDockerContainerSpecMapsRuntimeSpecToSDKConfig(t *testing.T) {
	spec, err := DockerContainerSpec(ServiceSpec{
		Name:           "slam",
		Image:          "navlab/slam:latest",
		ContainerName:  "navlab-slam-backend",
		Command:        []string{"bash", "-lc", "echo ok"},
		Env:            map[string]string{"ROS_DOMAIN_ID": "85", "HOME": "/tmp"},
		CWD:            "/workspace",
		User:           "1001:1002",
		Volumes:        []VolumeMount{{Source: "/host/ws", Target: "/workspace", Mode: "rw"}},
		Networks:       []string{"host"},
		Remove:         true,
		ServiceRole:    "slam_backend",
		StopSignal:     "SIGINT",
		StopTimeoutSec: 7,
	})
	if err != nil {
		t.Fatal(err)
	}
	if spec.ContainerName != "navlab-slam-backend" {
		t.Fatalf("container name = %q", spec.ContainerName)
	}
	if spec.Config.Image != "navlab/slam:latest" || !reflect.DeepEqual([]string(spec.Config.Cmd), []string{"bash", "-lc", "echo ok"}) {
		t.Fatalf("config = %#v", spec.Config)
	}
	if spec.Config.User != "1001:1002" || spec.Config.WorkingDir != "/workspace" {
		t.Fatalf("user/cwd = %q/%q", spec.Config.User, spec.Config.WorkingDir)
	}
	if !reflect.DeepEqual(spec.Config.Env, []string{"HOME=/tmp", "ROS_DOMAIN_ID=85"}) {
		t.Fatalf("env = %#v", spec.Config.Env)
	}
	if spec.Config.StopSignal != "SIGINT" || spec.Config.StopTimeout == nil || *spec.Config.StopTimeout != 7 {
		t.Fatalf("stop config = %q/%v", spec.Config.StopSignal, spec.Config.StopTimeout)
	}
	if !reflect.DeepEqual(spec.HostConfig.Binds, []string{"/host/ws:/workspace:rw"}) {
		t.Fatalf("binds = %#v", spec.HostConfig.Binds)
	}
	if string(spec.HostConfig.NetworkMode) != "host" || !spec.HostConfig.AutoRemove {
		t.Fatalf("host config = %#v", spec.HostConfig)
	}
	if spec.Config.Labels["navlab.runtime.backend"] != "docker_sdk" || spec.Config.Labels["navlab.runtime.role"] != "slam_backend" {
		t.Fatalf("labels = %#v", spec.Config.Labels)
	}
}

func TestDockerBackendStartServiceUsesSDKClient(t *testing.T) {
	client := &fakeDockerRuntimeClient{createResponse: dockercontainer.CreateResponse{ID: "abc123"}}
	backend := NewDockerBackend(client)
	backend.Now = func() time.Time { return time.Date(2026, 6, 12, 1, 2, 3, 0, time.UTC) }
	backend.DefaultUser = "1001:1002"

	handle, err := backend.StartService(ServiceSpec{
		Name:          "gazebo_sensor",
		Image:         "sensor:latest",
		ContainerName: "navlab-sensor",
		Command:       []string{"bash", "-lc", "run"},
		Detach:        true,
	})
	if err != nil {
		t.Fatal(err)
	}
	if handle.Identifier != "navlab-sensor" || handle.Backend != "docker_sdk" {
		t.Fatalf("handle = %#v", handle)
	}
	if !reflect.DeepEqual(client.removed, []string{"navlab-sensor"}) {
		t.Fatalf("pre-remove = %#v", client.removed)
	}
	if !reflect.DeepEqual(client.started, []string{"navlab-sensor"}) {
		t.Fatalf("started = %#v", client.started)
	}
	if client.createdConfig.User != "1001:1002" {
		t.Fatalf("created user = %q", client.createdConfig.User)
	}
	for _, want := range []string{"HOME=/tmp", "ROS_LOG_DIR=/tmp/navlab-ros-logs", "XDG_CACHE_HOME=/tmp/navlab-cache"} {
		if !containsString(client.createdConfig.Env, want) {
			t.Fatalf("env missing %s: %#v", want, client.createdConfig.Env)
		}
	}
}

func TestDockerBackendStartServiceKeepsExplicitUser(t *testing.T) {
	client := &fakeDockerRuntimeClient{}
	backend := NewDockerBackend(client)
	backend.DefaultUser = "1001:1002"

	_, err := backend.StartService(ServiceSpec{
		Name:    "root_service",
		Image:   "runtime:latest",
		Command: []string{"true"},
		User:    "0:0",
	})
	if err != nil {
		t.Fatal(err)
	}
	if client.createdConfig.User != "0:0" {
		t.Fatalf("created user = %q", client.createdConfig.User)
	}
}

func TestDockerBackendRunProbeWritesLogAndReturnsFailure(t *testing.T) {
	logPath := filepath.Join(t.TempDir(), "probe.txt")
	client := &fakeDockerRuntimeClient{
		waitCode: 42,
		logs:     "bad",
	}
	backend := NewDockerBackend(client)
	backend.DefaultUser = "1001:1002"

	result, err := backend.RunProbe(ProbeSpec{
		Name:    "rangefinder_probe",
		Image:   "runtime:latest",
		Command: []string{"bash", "-lc", "probe"},
		LogPath: logPath,
	})
	if err == nil {
		t.Fatal("RunProbe error = nil, want failure")
	}
	if result.ReturnCode != 42 {
		t.Fatalf("return code = %d, want 42", result.ReturnCode)
	}
	data, readErr := os.ReadFile(logPath)
	if readErr != nil {
		t.Fatal(readErr)
	}
	if !strings.Contains(string(data), "bad") {
		t.Fatalf("log = %q, want bad", string(data))
	}
	if !reflect.DeepEqual(client.removed, []string{"container-id"}) {
		t.Fatalf("removed = %#v", client.removed)
	}
}

func TestRosbagServiceSpecUsesRuntimeOwnedRecorderLifecycle(t *testing.T) {
	profile := filepath.Join(t.TempDir(), "topics.txt")
	if err := os.WriteFile(profile, []byte("# comment\n/tf\n/scan\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	service, err := RosbagServiceSpec(RosbagSpec{
		Name:          "hover_rosbag",
		Image:         "runtime:latest",
		ContainerName: "navlab-hover-rosbag",
		TopicsProfile: profile,
		OutputPath:    "/workspace/artifacts/rosbag",
		DurationSec:   90,
		Storage:       "mcap",
	})
	if err != nil {
		t.Fatal(err)
	}
	command := strings.Join(service.Command, " ")
	if strings.Contains(command, "timeout --signal=INT") {
		t.Fatalf("rosbag command still uses timeout wrapper: %q", command)
	}
	for _, want := range []string{"exec", "ros2", "bag", "record", "/tf", "/scan"} {
		if !strings.Contains(command, want) {
			t.Fatalf("command missing %q: %q", want, command)
		}
	}
	if service.StopSignal != "SIGINT" || service.StopTimeoutSec <= 0 {
		t.Fatalf("rosbag stop policy = %q/%d", service.StopSignal, service.StopTimeoutSec)
	}
}

func TestDockerBackendFinalizeRosbagStopsWithSIGINTAndRecordsMetadata(t *testing.T) {
	outputDir := filepath.Join(t.TempDir(), "rosbag")
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(outputDir, "metadata.yaml"), []byte("rosbag2_bagfile_information: {}\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	client := &fakeDockerRuntimeClient{waitCode: 0}
	backend := NewDockerBackend(client)
	backend.Now = func() time.Time { return time.Date(2026, 6, 12, 1, 2, 3, 0, time.UTC) }

	updated, err := backend.FinalizeRosbag(RuntimeHandle{
		ServiceName:    "hover_rosbag",
		Identifier:     "rosbag-container",
		StopSignal:     "SIGINT",
		StopTimeoutSec: 3,
		HostOutputPath: outputDir,
	})
	if err != nil {
		t.Fatal(err)
	}
	if !updated.FinalizeOK || updated.FinalizeStatus != "metadata_ready" || updated.MessageCountsSource != "metadata" {
		t.Fatalf("updated = %#v", updated)
	}
	if updated.WaitExitCode == nil || *updated.WaitExitCode != 0 {
		t.Fatalf("wait exit code = %#v", updated.WaitExitCode)
	}
	if len(client.stopped) != 1 || client.stopped[0].signal != "SIGINT" || client.stopped[0].timeout == nil || *client.stopped[0].timeout != 3 {
		t.Fatalf("stopped = %#v", client.stopped)
	}
}

func TestDockerBackendFinalizeRosbagAcceptsMCAPWhenMetadataMissing(t *testing.T) {
	outputDir := filepath.Join(t.TempDir(), "rosbag")
	if err := os.MkdirAll(outputDir, 0o755); err != nil {
		t.Fatal(err)
	}
	mcapPath := filepath.Join(outputDir, "hover_rosbag_0.mcap")
	if err := os.WriteFile(mcapPath, []byte("mcap"), 0o644); err != nil {
		t.Fatal(err)
	}
	client := &fakeDockerRuntimeClient{waitCode: 0}
	backend := NewDockerBackend(client)

	updated, err := backend.FinalizeRosbag(RuntimeHandle{ServiceName: "hover_rosbag", Identifier: "rosbag-container", HostOutputPath: outputDir})
	if err != nil {
		t.Fatal(err)
	}
	if !updated.FinalizeOK || updated.FinalizeStatus != "mcap_ready" || updated.MessageCountsSource != "mcap_presence" || !reflect.DeepEqual(updated.MCAPPaths, []string{mcapPath}) {
		t.Fatalf("updated = %#v", updated)
	}
}

func TestDockerBackendFinalizeRosbagTimesOutWithoutOutput(t *testing.T) {
	client := &fakeDockerRuntimeClient{waitCode: 0}
	backend := NewDockerBackend(client)
	backend.RosbagFinalizeTimeout = time.Millisecond

	updated, err := backend.FinalizeRosbag(RuntimeHandle{ServiceName: "hover_rosbag", Identifier: "rosbag-container", HostOutputPath: t.TempDir()})
	if err == nil || !strings.Contains(err.Error(), "rosbag finalize timeout") {
		t.Fatalf("FinalizeRosbag() error = %v, updated=%#v", err, updated)
	}
	if updated.FinalizeStatus != "finalize_timeout" {
		t.Fatalf("updated = %#v", updated)
	}
}

func TestSpecValidationRejectsMissingImage(t *testing.T) {
	err := ServiceSpec{Name: "bad", Command: []string{"true"}}.ValidateDocker()
	if err == nil || !strings.Contains(err.Error(), "image is required") {
		t.Fatalf("ValidateDocker() = %v, want image error", err)
	}
}

func TestDockerBackendRunProbeReturnsCreateError(t *testing.T) {
	client := &fakeDockerRuntimeClient{createErr: errors.New("daemon down")}
	backend := NewDockerBackend(client)

	result, err := backend.RunProbe(ProbeSpec{Name: "probe", Image: "runtime", Command: []string{"true"}})
	if err == nil || !strings.Contains(err.Error(), "daemon down") {
		t.Fatalf("RunProbe() error = %v", err)
	}
	if result.ReturnCode != 1 || !strings.Contains(result.Stderr, "daemon down") {
		t.Fatalf("result = %#v", result)
	}
}

func containsString(values []string, want string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
}
