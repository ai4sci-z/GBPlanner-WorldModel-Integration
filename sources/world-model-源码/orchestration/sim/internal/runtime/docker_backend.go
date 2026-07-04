package runtime

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	dockercontainer "github.com/docker/docker/api/types/container"
	dockernetwork "github.com/docker/docker/api/types/network"
	dockerclient "github.com/docker/docker/client"
	"github.com/docker/docker/pkg/stdcopy"
	ocispec "github.com/opencontainers/image-spec/specs-go/v1"
)

const (
	dockerSDKBackendName          = "docker_sdk"
	defaultContainerStopTimeout   = 15
	defaultRosbagFinalizeTimeout  = 10 * time.Second
	defaultProbeTimeoutReturnCode = 124
)

type DockerRuntimeClient interface {
	ContainerCreate(ctx context.Context, config *dockercontainer.Config, hostConfig *dockercontainer.HostConfig, networkingConfig *dockernetwork.NetworkingConfig, platform *ocispec.Platform, containerName string) (dockercontainer.CreateResponse, error)
	ContainerStart(ctx context.Context, containerID string, options dockercontainer.StartOptions) error
	ContainerStop(ctx context.Context, containerID string, options dockercontainer.StopOptions) error
	ContainerWait(ctx context.Context, containerID string, condition dockercontainer.WaitCondition) (<-chan dockercontainer.WaitResponse, <-chan error)
	ContainerLogs(ctx context.Context, containerID string, options dockercontainer.LogsOptions) (io.ReadCloser, error)
	ContainerRemove(ctx context.Context, containerID string, options dockercontainer.RemoveOptions) error
}

type DockerBackend struct {
	Client                 DockerRuntimeClient
	Now                    func() time.Time
	DefaultUser            string
	RosbagFinalizeTimeout  time.Duration
	ContainerStopTimeout   int
	ProbeTimeoutReturnCode int
}

type dockerContainerSpec struct {
	Config        *dockercontainer.Config
	HostConfig    *dockercontainer.HostConfig
	Network       *dockernetwork.NetworkingConfig
	ContainerName string
}

func NewDockerBackend(client DockerRuntimeClient) DockerBackend {
	if client == nil {
		client = mustNewSDKDockerRuntimeClient()
	}
	return DockerBackend{
		Client:                 client,
		Now:                    time.Now,
		DefaultUser:            CurrentUserSpec(),
		RosbagFinalizeTimeout:  defaultRosbagFinalizeTimeout,
		ContainerStopTimeout:   defaultContainerStopTimeout,
		ProbeTimeoutReturnCode: defaultProbeTimeoutReturnCode,
	}
}

func NewSDKDockerRuntimeClient() (*dockerclient.Client, error) {
	return dockerclient.NewClientWithOpts(
		dockerclient.FromEnv,
		dockerclient.WithAPIVersionNegotiation(),
	)
}

func mustNewSDKDockerRuntimeClient() DockerRuntimeClient {
	client, err := NewSDKDockerRuntimeClient()
	if err != nil {
		return failingDockerRuntimeClient{err: err}
	}
	return client
}

type failingDockerRuntimeClient struct {
	err error
}

func (client failingDockerRuntimeClient) ContainerCreate(context.Context, *dockercontainer.Config, *dockercontainer.HostConfig, *dockernetwork.NetworkingConfig, *ocispec.Platform, string) (dockercontainer.CreateResponse, error) {
	return dockercontainer.CreateResponse{}, client.err
}

func (client failingDockerRuntimeClient) ContainerStart(context.Context, string, dockercontainer.StartOptions) error {
	return client.err
}

func (client failingDockerRuntimeClient) ContainerStop(context.Context, string, dockercontainer.StopOptions) error {
	return client.err
}

func (client failingDockerRuntimeClient) ContainerWait(context.Context, string, dockercontainer.WaitCondition) (<-chan dockercontainer.WaitResponse, <-chan error) {
	resultC := make(chan dockercontainer.WaitResponse)
	errC := make(chan error, 1)
	errC <- client.err
	return resultC, errC
}

func (client failingDockerRuntimeClient) ContainerLogs(context.Context, string, dockercontainer.LogsOptions) (io.ReadCloser, error) {
	return nil, client.err
}

func (client failingDockerRuntimeClient) ContainerRemove(context.Context, string, dockercontainer.RemoveOptions) error {
	return client.err
}

func (backend DockerBackend) StartService(spec ServiceSpec) (RuntimeHandle, error) {
	if err := spec.ValidateDocker(); err != nil {
		return RuntimeHandle{}, err
	}
	spec = backend.withDefaultUser(spec)
	containerSpec, err := DockerContainerSpec(spec)
	if err != nil {
		return RuntimeHandle{}, err
	}
	if spec.ContainerName != "" {
		_ = backend.client().ContainerRemove(context.Background(), spec.ContainerName, dockercontainer.RemoveOptions{Force: true, RemoveVolumes: true})
	}
	created, err := backend.client().ContainerCreate(context.Background(), containerSpec.Config, containerSpec.HostConfig, containerSpec.Network, nil, containerSpec.ContainerName)
	if err != nil {
		_ = writeLog(spec.LogPath, "", err.Error())
		return RuntimeHandle{}, fmt.Errorf("docker sdk create service %s failed: %w", spec.Name, err)
	}
	identifier := identifier(spec.ContainerName, created.ID)
	if err := backend.client().ContainerStart(context.Background(), identifier, dockercontainer.StartOptions{}); err != nil {
		_ = writeLog(spec.LogPath, "", err.Error())
		_ = backend.client().ContainerRemove(context.Background(), identifier, dockercontainer.RemoveOptions{Force: true, RemoveVolumes: true})
		return RuntimeHandle{}, fmt.Errorf("docker sdk start service %s failed: %w", spec.Name, err)
	}
	return RuntimeHandle{
		Backend:        dockerSDKBackendName,
		ServiceName:    spec.Name,
		Identifier:     identifier,
		Command:        append([]string(nil), spec.Command...),
		StartedAt:      backend.now(),
		LogPath:        spec.LogPath,
		ContainerName:  spec.ContainerName,
		StopSignal:     spec.StopSignal,
		StopTimeoutSec: spec.StopTimeoutSec,
	}, nil
}

func (backend DockerBackend) StartRosbag(spec RosbagSpec) (RuntimeHandle, error) {
	service, err := RosbagServiceSpec(spec)
	if err != nil {
		return RuntimeHandle{}, err
	}
	handle, err := backend.StartService(service)
	if err != nil {
		return RuntimeHandle{}, err
	}
	handle.OutputPath = spec.OutputPath
	handle.HostOutputPath = hostPathForContainerPath(spec.OutputPath, spec.Volumes)
	handle.FinalizeTimeoutSec = backend.rosbagFinalizeTimeout().Seconds()
	return handle, nil
}

func (backend DockerBackend) RunProbe(spec ProbeSpec) (ProbeResult, error) {
	if err := spec.ValidateDocker(); err != nil {
		return ProbeResult{}, err
	}
	service := backend.withDefaultUser(ProbeServiceSpec(spec))
	containerSpec, err := DockerContainerSpec(service)
	if err != nil {
		return ProbeResult{}, err
	}
	ctx := context.Background()
	if spec.TimeoutSec > 0 {
		var cancel context.CancelFunc
		ctx, cancel = context.WithTimeout(ctx, time.Duration(spec.TimeoutSec*float64(time.Second)))
		defer cancel()
	}
	if service.ContainerName != "" {
		_ = backend.client().ContainerRemove(context.Background(), service.ContainerName, dockercontainer.RemoveOptions{Force: true, RemoveVolumes: true})
	}
	created, err := backend.client().ContainerCreate(ctx, containerSpec.Config, containerSpec.HostConfig, containerSpec.Network, nil, containerSpec.ContainerName)
	if err != nil {
		probe := ProbeResult{Backend: dockerSDKBackendName, Name: spec.Name, ReturnCode: 1, Stderr: err.Error(), LogPath: spec.LogPath}
		_ = writeLog(spec.LogPath, probe.Stdout, probe.Stderr)
		return probe, fmt.Errorf("docker sdk create probe %s failed: %w", spec.Name, err)
	}
	identifier := identifier(service.ContainerName, created.ID)
	defer func() {
		_ = backend.client().ContainerRemove(context.Background(), identifier, dockercontainer.RemoveOptions{Force: true, RemoveVolumes: true})
	}()
	if err := backend.client().ContainerStart(ctx, identifier, dockercontainer.StartOptions{}); err != nil {
		probe := ProbeResult{Backend: dockerSDKBackendName, Name: spec.Name, ReturnCode: 1, Stderr: err.Error(), LogPath: spec.LogPath}
		_ = writeLog(spec.LogPath, probe.Stdout, probe.Stderr)
		return probe, fmt.Errorf("docker sdk start probe %s failed: %w", spec.Name, err)
	}
	code, waitErr := backend.waitContainer(ctx, identifier)
	stdout, stderr := backend.containerLogs(context.Background(), identifier, 0)
	if errors.Is(ctx.Err(), context.DeadlineExceeded) {
		_ = backend.stopContainer(context.Background(), RuntimeHandle{Identifier: identifier, ServiceName: spec.Name}, "SIGTERM", 2)
		code = backend.probeTimeoutReturnCode()
		waitErr = ctx.Err()
	}
	_ = writeLog(spec.LogPath, stdout, stderr)
	probe := ProbeResult{
		Backend:    dockerSDKBackendName,
		Name:       spec.Name,
		ReturnCode: code,
		Stdout:     stdout,
		Stderr:     stderr,
		LogPath:    spec.LogPath,
	}
	if waitErr != nil {
		return probe, fmt.Errorf("docker sdk probe %s failed: %w", spec.Name, waitErr)
	}
	if code != 0 {
		return probe, fmt.Errorf("docker sdk probe %s returned code %d", spec.Name, code)
	}
	return probe, nil
}

func (backend DockerBackend) Wait(handle RuntimeHandle) (int, error) {
	code, err := backend.waitContainer(context.Background(), handle.Identifier)
	if err != nil {
		return code, fmt.Errorf("docker sdk wait %s failed: %w", handle.ServiceName, err)
	}
	return code, nil
}

func (backend DockerBackend) FinalizeRosbag(handle RuntimeHandle) (RuntimeHandle, error) {
	handle.StopRequestedAt = backend.now().UTC().Format(time.RFC3339Nano)
	signal := defaultString(handle.StopSignal, "SIGINT")
	timeout := handle.StopTimeoutSec
	if timeout <= 0 {
		timeout = backend.containerStopTimeout()
	}
	handle.StopSignal = signal
	handle.StopTimeoutSec = timeout
	if err := backend.stopContainer(context.Background(), handle, signal, timeout); err != nil {
		handle.FinalizeStatus = "stop_failed"
		return handle, fmt.Errorf("docker sdk stop rosbag %s failed: %w", handle.ServiceName, err)
	}
	code, err := backend.waitContainer(context.Background(), handle.Identifier)
	handle.WaitExitCode = &code
	handle.StoppedAt = backend.now().UTC().Format(time.RFC3339Nano)
	if err != nil {
		handle.FinalizeStatus = "wait_failed"
		return handle, fmt.Errorf("docker sdk wait rosbag %s failed: %w", handle.ServiceName, err)
	}
	if err := backend.waitForRosbagOutput(&handle); err != nil {
		handle.FinalizeStatus = "finalize_timeout"
		return handle, err
	}
	handle.FinalizeOK = true
	return handle, nil
}

func (backend DockerBackend) Stop(handle RuntimeHandle) error {
	if handle.FinalizeOK || handle.FinalizeStatus != "" {
		if err := backend.client().ContainerRemove(context.Background(), handle.Identifier, dockercontainer.RemoveOptions{Force: true, RemoveVolumes: true}); err != nil {
			return fmt.Errorf("docker sdk remove %s failed: %w", handle.ServiceName, err)
		}
		return nil
	}
	signal := handle.StopSignal
	timeout := handle.StopTimeoutSec
	if timeout <= 0 {
		timeout = backend.containerStopTimeout()
	}
	if err := backend.stopContainer(context.Background(), handle, signal, timeout); err != nil {
		_ = backend.client().ContainerRemove(context.Background(), handle.Identifier, dockercontainer.RemoveOptions{Force: true, RemoveVolumes: true})
		return fmt.Errorf("docker sdk stop %s failed: %w", handle.ServiceName, err)
	}
	if err := backend.client().ContainerRemove(context.Background(), handle.Identifier, dockercontainer.RemoveOptions{Force: true, RemoveVolumes: true}); err != nil {
		return fmt.Errorf("docker sdk remove %s failed: %w", handle.ServiceName, err)
	}
	return nil
}

func (backend DockerBackend) Logs(handle RuntimeHandle, tail int) (string, error) {
	stdout, stderr := backend.containerLogs(context.Background(), handle.Identifier, tail)
	text := stdout
	if stderr != "" {
		if text != "" {
			text += "\n"
		}
		text += stderr
	}
	if text == "" {
		return "", nil
	}
	return text, nil
}

func DockerContainerSpec(spec ServiceSpec) (dockerContainerSpec, error) {
	if err := spec.ValidateDocker(); err != nil {
		return dockerContainerSpec{}, err
	}
	binds, err := dockerBinds(spec.Volumes)
	if err != nil {
		return dockerContainerSpec{}, err
	}
	hostConfig := &dockercontainer.HostConfig{
		AutoRemove: spec.Remove,
		Binds:      binds,
	}
	if len(spec.Networks) > 0 {
		hostConfig.NetworkMode = dockercontainer.NetworkMode(spec.Networks[0])
	}
	stopTimeout := spec.StopTimeoutSec
	config := &dockercontainer.Config{
		Image:        spec.Image,
		Cmd:          append([]string(nil), spec.Command...),
		Env:          dockerEnv(spec.Env),
		User:         spec.User,
		WorkingDir:   spec.CWD,
		Labels:       dockerLabels(spec),
		StopSignal:   spec.StopSignal,
		StopTimeout:  nil,
		AttachStdout: true,
		AttachStderr: true,
	}
	if stopTimeout > 0 {
		config.StopTimeout = &stopTimeout
	}
	networkingConfig := &dockernetwork.NetworkingConfig{}
	return dockerContainerSpec{
		Config:        config,
		HostConfig:    hostConfig,
		Network:       networkingConfig,
		ContainerName: spec.ContainerName,
	}, nil
}

func ProbeServiceSpec(spec ProbeSpec) ServiceSpec {
	return ServiceSpec{
		Name:          spec.Name,
		Command:       spec.Command,
		Image:         spec.Image,
		ContainerName: spec.ContainerName,
		Env:           spec.Env,
		CWD:           spec.CWD,
		Volumes:       spec.Volumes,
		Networks:      spec.Networks,
		Detach:        false,
		Remove:        false,
		Required:      spec.Required,
		LogPath:       spec.LogPath,
		ServiceRole:   spec.ServiceRole,
	}
}

func CurrentUserSpec() string {
	uid := os.Getuid()
	gid := os.Getgid()
	if uid == 0 {
		return ""
	}
	return fmt.Sprintf("%d:%d", uid, gid)
}

func RosbagServiceSpec(spec RosbagSpec) (ServiceSpec, error) {
	topics, err := spec.Topics()
	if err != nil {
		return ServiceSpec{}, err
	}
	storage := spec.Storage
	if storage == "" {
		storage = "mcap"
	}
	command := []string{"ros2", "bag", "record", "-s", storage, "--compression-mode", "file", "--compression-format", "zstd", "-o", spec.OutputPath, "--topics"}
	command = append(command, topics...)
	outputParent := pathDir(spec.OutputPath)
	shellCommand := fmt.Sprintf(
		"rm -rf %s && mkdir -p %s && exec %s",
		shellQuote(spec.OutputPath),
		shellQuote(outputParent),
		shellJoin(command),
	)
	return ServiceSpec{
		Name:           spec.Name,
		Command:        []string{"bash", "-lc", shellCommand},
		Image:          spec.Image,
		ContainerName:  spec.ContainerName,
		Env:            spec.Env,
		CWD:            spec.CWD,
		Volumes:        spec.Volumes,
		Networks:       spec.Networks,
		Detach:         true,
		Remove:         false,
		Required:       spec.Required,
		LogPath:        spec.LogPath,
		ServiceRole:    spec.ServiceRole,
		StopSignal:     "SIGINT",
		StopTimeoutSec: defaultContainerStopTimeout,
	}, nil
}

func (backend DockerBackend) withDefaultUser(spec ServiceSpec) ServiceSpec {
	if spec.User != "" {
		return spec
	}
	if backend.DefaultUser == "" {
		return spec
	}
	spec.User = backend.DefaultUser
	spec.Env = withWritableRuntimeEnv(spec.Env)
	return spec
}

func (backend DockerBackend) waitContainer(ctx context.Context, identifier string) (int, error) {
	resultC, errC := backend.client().ContainerWait(ctx, identifier, dockercontainer.WaitConditionNotRunning)
	select {
	case result := <-resultC:
		if result.Error != nil {
			return int(result.StatusCode), errors.New(result.Error.Message)
		}
		return int(result.StatusCode), nil
	case err := <-errC:
		if err == nil {
			return 0, nil
		}
		return 1, err
	case <-ctx.Done():
		return 1, ctx.Err()
	}
}

func (backend DockerBackend) stopContainer(ctx context.Context, handle RuntimeHandle, signal string, timeout int) error {
	options := dockercontainer.StopOptions{Signal: signal}
	if timeout > 0 {
		options.Timeout = &timeout
	}
	return backend.client().ContainerStop(ctx, handle.Identifier, options)
}

func (backend DockerBackend) containerLogs(ctx context.Context, identifier string, tail int) (string, string) {
	if tail <= 0 {
		tail = 400
	}
	reader, err := backend.client().ContainerLogs(ctx, identifier, dockercontainer.LogsOptions{
		ShowStdout: true,
		ShowStderr: true,
		Tail:       fmt.Sprint(tail),
	})
	if err != nil {
		return "", err.Error()
	}
	defer func() { _ = reader.Close() }()
	data, readErr := io.ReadAll(reader)
	if readErr != nil {
		return "", readErr.Error()
	}
	stdout := &bytes.Buffer{}
	stderr := &bytes.Buffer{}
	if _, err := stdcopy.StdCopy(stdout, stderr, bytes.NewReader(data)); err != nil {
		if stdout.Len() == 0 && stderr.Len() == 0 && len(data) > 0 {
			return string(data), ""
		}
		if stderr.Len() == 0 {
			stderr.WriteString(err.Error())
		}
	}
	if stdout.Len() == 0 && stderr.Len() == 0 && len(data) > 0 {
		return string(data), ""
	}
	return stdout.String(), stderr.String()
}

func (backend DockerBackend) waitForRosbagOutput(handle *RuntimeHandle) error {
	hostOutput := handle.HostOutputPath
	if strings.TrimSpace(hostOutput) == "" {
		handle.FinalizeStatus = "host_output_path_unavailable"
		return nil
	}
	deadline := time.Now().Add(backend.rosbagFinalizeTimeout())
	for {
		metadataPath := filepath.Join(hostOutput, "metadata.yaml")
		if _, err := os.Stat(metadataPath); err == nil {
			handle.MetadataPath = metadataPath
			handle.FinalizeStatus = "metadata_ready"
			handle.MessageCountsSource = "metadata"
			return nil
		}
		mcapPaths := findMCAPPaths(hostOutput)
		if len(mcapPaths) > 0 {
			handle.MCAPPaths = mcapPaths
			handle.FinalizeStatus = "mcap_ready"
			handle.MessageCountsSource = "mcap_presence"
			return nil
		}
		if time.Now().After(deadline) {
			return fmt.Errorf("rosbag finalize timeout for %s: no metadata.yaml or mcap under %s", handle.ServiceName, hostOutput)
		}
		time.Sleep(250 * time.Millisecond)
	}
}

func (backend DockerBackend) client() DockerRuntimeClient {
	if backend.Client != nil {
		return backend.Client
	}
	return mustNewSDKDockerRuntimeClient()
}

func (backend DockerBackend) now() time.Time {
	if backend.Now != nil {
		return backend.Now()
	}
	return time.Now()
}

func (backend DockerBackend) rosbagFinalizeTimeout() time.Duration {
	if backend.RosbagFinalizeTimeout > 0 {
		return backend.RosbagFinalizeTimeout
	}
	return defaultRosbagFinalizeTimeout
}

func (backend DockerBackend) containerStopTimeout() int {
	if backend.ContainerStopTimeout > 0 {
		return backend.ContainerStopTimeout
	}
	return defaultContainerStopTimeout
}

func (backend DockerBackend) probeTimeoutReturnCode() int {
	if backend.ProbeTimeoutReturnCode > 0 {
		return backend.ProbeTimeoutReturnCode
	}
	return defaultProbeTimeoutReturnCode
}

func withWritableRuntimeEnv(env map[string]string) map[string]string {
	if env == nil {
		env = map[string]string{}
	} else {
		copied := make(map[string]string, len(env)+3)
		for key, value := range env {
			copied[key] = value
		}
		env = copied
	}
	if env["HOME"] == "" {
		env["HOME"] = "/tmp"
	}
	if env["ROS_LOG_DIR"] == "" {
		env["ROS_LOG_DIR"] = "/tmp/navlab-ros-logs"
	}
	if env["XDG_CACHE_HOME"] == "" {
		env["XDG_CACHE_HOME"] = "/tmp/navlab-cache"
	}
	return env
}

func dockerEnv(env map[string]string) []string {
	keys := make([]string, 0, len(env))
	for key := range env {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	result := make([]string, 0, len(keys))
	for _, key := range keys {
		result = append(result, key+"="+env[key])
	}
	return result
}

func dockerBinds(volumes []VolumeMount) ([]string, error) {
	binds := make([]string, 0, len(volumes))
	for _, mount := range volumes {
		value, err := mount.DockerArg()
		if err != nil {
			return nil, err
		}
		binds = append(binds, value)
	}
	return binds, nil
}

func dockerLabels(spec ServiceSpec) map[string]string {
	labels := map[string]string{
		"navlab.runtime.backend": "docker_sdk",
		"navlab.runtime.service": spec.Name,
	}
	if spec.ServiceRole != "" {
		labels["navlab.runtime.role"] = spec.ServiceRole
	}
	return labels
}

func hostPathForContainerPath(containerPath string, volumes []VolumeMount) string {
	containerPath = filepath.Clean(containerPath)
	bestTarget := ""
	bestSource := ""
	for _, volume := range volumes {
		target := filepath.Clean(volume.Target)
		if target == "." || target == string(filepath.Separator) {
			continue
		}
		if containerPath == target || strings.HasPrefix(containerPath, target+string(filepath.Separator)) {
			if len(target) > len(bestTarget) {
				bestTarget = target
				bestSource = filepath.Clean(volume.Source)
			}
		}
	}
	if bestTarget == "" {
		return ""
	}
	rel, err := filepath.Rel(bestTarget, containerPath)
	if err != nil {
		return ""
	}
	return filepath.Join(bestSource, rel)
}

func findMCAPPaths(root string) []string {
	matches := []string{}
	for _, pattern := range []string{"*.mcap", "*.mcap.zstd"} {
		found, _ := filepath.Glob(filepath.Join(root, pattern))
		matches = append(matches, found...)
	}
	sort.Strings(matches)
	return matches
}

func identifier(containerName string, fallback string) string {
	if containerName != "" {
		return containerName
	}
	return fallback
}

func defaultString(value string, fallback string) string {
	if strings.TrimSpace(value) != "" {
		return value
	}
	return fallback
}

func shellJoin(args []string) string {
	quoted := make([]string, 0, len(args))
	for _, arg := range args {
		quoted = append(quoted, shellQuote(arg))
	}
	return strings.Join(quoted, " ")
}

func shellQuote(value string) string {
	if value == "" {
		return "''"
	}
	return "'" + strings.ReplaceAll(value, "'", "'\"'\"'") + "'"
}

func pathDir(value string) string {
	cleaned := strings.TrimRight(value, "/")
	if cleaned == "" {
		return "."
	}
	index := strings.LastIndex(cleaned, "/")
	if index <= 0 {
		return "."
	}
	return cleaned[:index]
}
