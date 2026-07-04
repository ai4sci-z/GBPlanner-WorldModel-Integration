package runtime

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

type ServiceSpec struct {
	Name           string
	Command        []string
	Image          string
	ContainerName  string
	Env            map[string]string
	CWD            string
	Volumes        []VolumeMount
	Networks       []string
	User           string
	Detach         bool
	Remove         bool
	Required       bool
	Restartable    bool
	LogPath        string
	ServiceRole    string
	StopSignal     string
	StopTimeoutSec int
}

type VolumeMount struct {
	Source string
	Target string
	Mode   string
}

type RosbagSpec struct {
	Name          string
	Image         string
	ContainerName string
	TopicsProfile string
	OutputPath    string
	DurationSec   float64
	Storage       string
	Env           map[string]string
	CWD           string
	Volumes       []VolumeMount
	Networks      []string
	LogPath       string
	Required      bool
	ServiceRole   string
}

type ProbeSpec struct {
	Name          string
	Command       []string
	Image         string
	ContainerName string
	Env           map[string]string
	CWD           string
	Volumes       []VolumeMount
	Networks      []string
	OutputPath    string
	TimeoutSec    float64
	LogPath       string
	Required      bool
	ServiceRole   string
}

type RuntimeHandle struct {
	Backend             string    `json:"backend"`
	ServiceName         string    `json:"service_name"`
	Identifier          string    `json:"identifier"`
	Command             []string  `json:"command"`
	StartedAt           time.Time `json:"started_at"`
	LogPath             string    `json:"log_path,omitempty"`
	ContainerName       string    `json:"container_name,omitempty"`
	StopSignal          string    `json:"stop_signal,omitempty"`
	StopTimeoutSec      int       `json:"stop_timeout_sec,omitempty"`
	OutputPath          string    `json:"output_path,omitempty"`
	HostOutputPath      string    `json:"host_output_path,omitempty"`
	StopRequestedAt     string    `json:"stop_requested_at,omitempty"`
	StoppedAt           string    `json:"stopped_at,omitempty"`
	WaitExitCode        *int      `json:"wait_exit_code,omitempty"`
	FinalizeOK          bool      `json:"finalize_ok,omitempty"`
	FinalizeStatus      string    `json:"finalize_status,omitempty"`
	FinalizeTimeoutSec  float64   `json:"finalize_timeout_sec,omitempty"`
	MetadataPath        string    `json:"metadata_path,omitempty"`
	MCAPPaths           []string  `json:"mcap_paths,omitempty"`
	MessageCountsSource string    `json:"message_counts_source,omitempty"`
}

type ProbeResult struct {
	Backend    string `json:"backend"`
	Name       string `json:"name"`
	ReturnCode int    `json:"return_code"`
	Stdout     string `json:"stdout"`
	Stderr     string `json:"stderr,omitempty"`
	LogPath    string `json:"log_path,omitempty"`
}

func (result ProbeResult) OK() bool {
	return result.ReturnCode == 0
}

type Backend interface {
	StartService(spec ServiceSpec) (RuntimeHandle, error)
	StartRosbag(spec RosbagSpec) (RuntimeHandle, error)
	RunProbe(spec ProbeSpec) (ProbeResult, error)
	Wait(handle RuntimeHandle) (int, error)
	Stop(handle RuntimeHandle) error
	Logs(handle RuntimeHandle, tail int) (string, error)
}

type RosbagFinalizer interface {
	FinalizeRosbag(handle RuntimeHandle) (RuntimeHandle, error)
}

func (spec ServiceSpec) ValidateDocker() error {
	if strings.TrimSpace(spec.Name) == "" {
		return errors.New("service name is required")
	}
	if strings.TrimSpace(spec.Image) == "" {
		return fmt.Errorf("service %s: docker image is required", spec.Name)
	}
	if len(spec.Command) == 0 {
		return fmt.Errorf("service %s: command is required", spec.Name)
	}
	return validateEnv(spec.Name, spec.Env)
}

func (spec ProbeSpec) ValidateDocker() error {
	if strings.TrimSpace(spec.Name) == "" {
		return errors.New("probe name is required")
	}
	if strings.TrimSpace(spec.Image) == "" {
		return fmt.Errorf("probe %s: docker image is required", spec.Name)
	}
	if len(spec.Command) == 0 {
		return fmt.Errorf("probe %s: command is required", spec.Name)
	}
	if spec.TimeoutSec < 0 {
		return fmt.Errorf("probe %s: timeout_sec cannot be negative", spec.Name)
	}
	return validateEnv(spec.Name, spec.Env)
}

func (spec RosbagSpec) Validate() error {
	if strings.TrimSpace(spec.Name) == "" {
		return errors.New("rosbag name is required")
	}
	if strings.TrimSpace(spec.TopicsProfile) == "" {
		return fmt.Errorf("rosbag %s: topics profile is required", spec.Name)
	}
	if strings.TrimSpace(spec.OutputPath) == "" {
		return fmt.Errorf("rosbag %s: output path is required", spec.Name)
	}
	if spec.DurationSec < 0 {
		return fmt.Errorf("rosbag %s: duration_sec cannot be negative", spec.Name)
	}
	if _, err := os.Stat(spec.TopicsProfile); err != nil {
		return fmt.Errorf("rosbag %s: topics profile %s: %w", spec.Name, spec.TopicsProfile, err)
	}
	return validateEnv(spec.Name, spec.Env)
}

func (spec RosbagSpec) Topics() ([]string, error) {
	if err := spec.Validate(); err != nil {
		return nil, err
	}
	data, err := os.ReadFile(spec.TopicsProfile)
	if err != nil {
		return nil, err
	}
	var topics []string
	for _, line := range strings.Split(string(data), "\n") {
		cleaned := strings.TrimSpace(line)
		if cleaned == "" || strings.HasPrefix(cleaned, "#") {
			continue
		}
		topics = append(topics, cleaned)
	}
	if len(topics) == 0 {
		return nil, fmt.Errorf("rosbag %s: topics profile %s is empty", spec.Name, spec.TopicsProfile)
	}
	return topics, nil
}

func (mount VolumeMount) DockerArg() (string, error) {
	if strings.TrimSpace(mount.Source) == "" {
		return "", errors.New("volume source is required")
	}
	if strings.TrimSpace(mount.Target) == "" {
		return "", errors.New("volume target is required")
	}
	source := filepath.Clean(mount.Source)
	value := source + ":" + mount.Target
	if mount.Mode != "" {
		value += ":" + mount.Mode
	}
	return value, nil
}

func writeLog(path string, stdout string, stderr string) error {
	if path == "" {
		return nil
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	text := stdout
	if stderr != "" {
		text += "\n--- stderr ---\n" + stderr
	}
	return os.WriteFile(path, []byte(text), 0o644)
}

func validateEnv(name string, env map[string]string) error {
	for key, value := range env {
		if strings.TrimSpace(key) == "" {
			return fmt.Errorf("%s: env key cannot be empty", name)
		}
		if strings.Contains(key, "=") {
			return fmt.Errorf("%s: env key %q cannot contain =", name, key)
		}
		if value == "" {
			continue
		}
	}
	return nil
}
