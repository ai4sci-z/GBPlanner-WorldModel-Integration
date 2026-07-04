package runtime

import (
	"context"
	"errors"
	"strings"

	"github.com/docker/docker/api/types/network"
	"github.com/docker/docker/client"
)

var ErrNilDockerResourceProbeClient = errors.New("nil docker resource probe client")

type DockerResourceProbeClient interface {
	ProbeDaemon(ctx context.Context) (DockerDaemonProbe, error)
	InspectImage(ctx context.Context, imageRef string) (DockerImageProbe, error)
	InspectNetwork(ctx context.Context, network string) (DockerNetworkProbe, error)
}

type DockerResourceProbeCloser interface {
	Close() error
}

type DockerDaemonProbe struct {
	Host            string
	ServerVersion   string
	APIVersion      string
	MinAPIVersion   string
	OSType          string
	OperatingSystem string
	Architecture    string
	DockerRootDir   string
	SecurityOptions []string
	Rootless        bool
	Warnings        []string
}

type DockerImageProbe struct {
	Image       string
	ID          string
	RepoTags    []string
	RepoDigests []string
	Created     string
	SizeBytes   int64
	OS          string
	Arch        string
}

type DockerNetworkProbe struct {
	Name   string
	ID     string
	Driver string
	Scope  string
}

type SDKDockerResourceProbeClient struct {
	client *client.Client
}

func NewSDKDockerResourceProbeClient() (*SDKDockerResourceProbeClient, error) {
	dockerClient, err := client.NewClientWithOpts(
		client.FromEnv,
		client.WithAPIVersionNegotiation(),
	)
	if err != nil {
		return nil, err
	}
	return &SDKDockerResourceProbeClient{client: dockerClient}, nil
}

func (probe *SDKDockerResourceProbeClient) ProbeDaemon(ctx context.Context) (DockerDaemonProbe, error) {
	result := DockerDaemonProbe{}
	if probe == nil || probe.client == nil {
		return result, ErrNilDockerResourceProbeClient
	}
	result.Host = probe.client.DaemonHost()
	ping, err := probe.client.Ping(ctx)
	if err != nil {
		return result, err
	}
	result.APIVersion = ping.APIVersion
	result.OSType = ping.OSType
	version, err := probe.client.ServerVersion(ctx)
	if err != nil {
		return result, err
	}
	result.ServerVersion = version.Version
	result.MinAPIVersion = version.MinAPIVersion
	if result.APIVersion == "" {
		result.APIVersion = version.APIVersion
	}
	if result.OSType == "" {
		result.OSType = version.Os
	}
	result.Architecture = version.Arch

	info, err := probe.client.Info(ctx)
	if err != nil {
		result.Warnings = append(result.Warnings, "docker info unavailable: "+err.Error())
		return result, nil
	}
	result.OperatingSystem = info.OperatingSystem
	result.Architecture = firstNonEmpty(result.Architecture, info.Architecture)
	result.DockerRootDir = info.DockerRootDir
	result.SecurityOptions = append([]string(nil), info.SecurityOptions...)
	result.Rootless = dockerSecurityOptionsClaimRootless(info.SecurityOptions)
	return result, nil
}

func (probe *SDKDockerResourceProbeClient) InspectImage(ctx context.Context, imageRef string) (DockerImageProbe, error) {
	if probe == nil || probe.client == nil {
		return DockerImageProbe{}, ErrNilDockerResourceProbeClient
	}
	inspect, _, err := probe.client.ImageInspectWithRaw(ctx, imageRef)
	if err != nil {
		return DockerImageProbe{}, err
	}
	return DockerImageProbe{
		Image:       imageRef,
		ID:          inspect.ID,
		RepoTags:    append([]string(nil), inspect.RepoTags...),
		RepoDigests: append([]string(nil), inspect.RepoDigests...),
		Created:     inspect.Created,
		SizeBytes:   inspect.Size,
		OS:          inspect.Os,
		Arch:        inspect.Architecture,
	}, nil
}

func (probe *SDKDockerResourceProbeClient) InspectNetwork(ctx context.Context, networkName string) (DockerNetworkProbe, error) {
	if probe == nil || probe.client == nil {
		return DockerNetworkProbe{}, ErrNilDockerResourceProbeClient
	}
	inspect, err := probe.client.NetworkInspect(ctx, networkName, networkInspectOptions())
	if err != nil {
		return DockerNetworkProbe{}, err
	}
	return DockerNetworkProbe{
		Name:   firstNonEmpty(inspect.Name, networkName),
		ID:     inspect.ID,
		Driver: inspect.Driver,
		Scope:  inspect.Scope,
	}, nil
}

func (probe *SDKDockerResourceProbeClient) Close() error {
	if probe == nil || probe.client == nil {
		return nil
	}
	return probe.client.Close()
}

func dockerSecurityOptionsClaimRootless(options []string) bool {
	for _, option := range options {
		normalized := strings.ToLower(strings.TrimSpace(option))
		if normalized == "name=rootless" || normalized == "rootless" || strings.Contains(normalized, "rootless") {
			return true
		}
	}
	return false
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func networkInspectOptions() network.InspectOptions {
	return network.InspectOptions{}
}
