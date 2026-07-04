package images

import (
	"bytes"
	"context"
	"errors"
	"io"
	"reflect"
	"strings"
	"testing"

	dockertypes "github.com/docker/docker/api/types"

	"navlab/orchestration-sim/internal/config"
)

type fakeDockerBuildClient struct {
	calls []dockertypes.ImageBuildOptions
	err   error
}

func (client *fakeDockerBuildClient) ImageBuild(ctx context.Context, buildContext io.Reader, options dockertypes.ImageBuildOptions) (dockertypes.ImageBuildResponse, error) {
	_, _ = ctx, buildContext
	client.calls = append(client.calls, options)
	if client.err != nil {
		return dockertypes.ImageBuildResponse{}, client.err
	}
	return dockertypes.ImageBuildResponse{Body: io.NopCloser(strings.NewReader("sdk build output\n"))}, nil
}

func TestResolveBuildSpecsAllUsesConfiguredImages(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	project := testProject()

	specs, err := ResolveBuildSpecsWithOptions(project, BuildOptions{Kind: KindAll, Tag: "test-tag"})
	if err != nil {
		t.Fatal(err)
	}
	if len(specs) != 9 {
		t.Fatalf("specs len = %d", len(specs))
	}
	kinds := make([]string, 0, len(specs))
	for _, spec := range specs {
		kinds = append(kinds, spec.Kind)
	}
	wantKinds := []string{
		KindRosBase, KindArduPilotSITL, KindMAVLinkRouter, KindGazeboHeadless, KindFastLIO,
		KindCompanion, KindSlam, KindGazeboSensor, KindOfficialBaseline,
	}
	if !reflect.DeepEqual(kinds, wantKinds) {
		t.Fatalf("kinds = %#v", kinds)
	}
	first := specs[0]
	if first.Image != "navlab/ros-base:test-tag" || first.Group != KindBase {
		t.Fatalf("image = %q", first.Image)
	}
	wantCommand := []string{
		"docker-sdk", "build",
		"-f", "docker/images/base/ros-base.Dockerfile",
		"--build-arg", "INFRA_TAG=test-tag",
		"--build-arg", "ROS_DISTRO=humble",
		"-t", "navlab/ros-base:test-tag",
		"/workspace",
	}
	if !reflect.DeepEqual(first.Command, wantCommand) {
		t.Fatalf("command = %#v", first.Command)
	}
}

func TestResolveBuildSpecsRuntimeGroupUsesRuntimeImages(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	specs, err := ResolveBuildSpecsWithOptions(testProject(), BuildOptions{Kind: KindRuntime, Tag: "local"})
	if err != nil {
		t.Fatal(err)
	}
	kinds := []string{specs[0].Kind, specs[1].Kind, specs[2].Kind, specs[3].Kind}
	if !reflect.DeepEqual(kinds, []string{KindCompanion, KindSlam, KindGazeboSensor, KindOfficialBaseline}) {
		t.Fatalf("kinds = %#v", kinds)
	}
	if specs[0].Group != GroupRuntime || specs[0].Dockerfile != "/workspace/docker/images/runtime/companion.Dockerfile" {
		t.Fatalf("runtime spec = %#v", specs[0])
	}
}

func TestResolveBuildSpecsInfraGroupExcludesBase(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	specs, err := ResolveBuildSpecsWithOptions(testProject(), BuildOptions{Kind: KindInfra, Tag: "local"})
	if err != nil {
		t.Fatal(err)
	}
	kinds := make([]string, 0, len(specs))
	for _, spec := range specs {
		kinds = append(kinds, spec.Kind)
	}
	wantKinds := []string{KindArduPilotSITL, KindMAVLinkRouter, KindGazeboHeadless, KindFastLIO}
	if !reflect.DeepEqual(kinds, wantKinds) {
		t.Fatalf("kinds = %#v", kinds)
	}
}

func TestResolveBuildSpecsSingleInfraImage(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	specs, err := ResolveBuildSpecsWithOptions(testProject(), BuildOptions{
		Kind:  KindInfra,
		Image: KindGazeboHeadless,
		Tag:   "local",
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(specs) != 1 || specs[0].Kind != KindGazeboHeadless || specs[0].Group != GroupInfra {
		t.Fatalf("specs = %#v", specs)
	}
	if specs[0].Image != "navlab/gazebo-headless:local" {
		t.Fatalf("image = %q", specs[0].Image)
	}
}

func TestResolveBuildSpecsBaseGroupBuildsRosBase(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	specs, err := ResolveBuildSpecsWithOptions(testProject(), BuildOptions{Kind: KindBase, Tag: "local"})
	if err != nil {
		t.Fatal(err)
	}
	if len(specs) != 1 || specs[0].ConfigKey != "ros_base" || specs[0].Image != "navlab/ros-base:local" {
		t.Fatalf("specs = %#v", specs)
	}
}

func TestResolveBuildSpecsRejectsImageWithBaseGroup(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	_, err := ResolveBuildSpecsWithOptions(testProject(), BuildOptions{
		Kind:  KindBase,
		Image: KindRosBase,
		Tag:   "local",
	})
	if err == nil || !strings.Contains(err.Error(), "--image can only be used with infra or runtime") {
		t.Fatalf("err = %v", err)
	}
}

func TestResolveBuildSpecsRejectsImageAsBuildGroup(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	_, err := ResolveBuildSpecsWithOptions(testProject(), BuildOptions{Kind: KindRosBase, Tag: "local"})
	if err == nil || !strings.Contains(err.Error(), "invalid image group") {
		t.Fatalf("err = %v", err)
	}
}

func TestResolveBuildSpecsRejectsImageFromWrongGroup(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	_, err := ResolveBuildSpecsWithOptions(testProject(), BuildOptions{
		Kind:  KindInfra,
		Image: KindCompanion,
		Tag:   "local",
	})
	if err == nil || !strings.Contains(err.Error(), "belongs to runtime, not infra") {
		t.Fatalf("err = %v", err)
	}
}

func TestResolveBuildSpecsRejectsBaseImageFromInfraGroup(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	_, err := ResolveBuildSpecsWithOptions(testProject(), BuildOptions{
		Kind:  KindInfra,
		Image: KindRosBase,
		Tag:   "local",
	})
	if err == nil || !strings.Contains(err.Error(), "belongs to base, not infra") {
		t.Fatalf("err = %v", err)
	}
}

func TestResolveBuildSpecsUsesEnvDistroAndFallback(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	project := testProject()
	specs, err := ResolveBuildSpecsWithOptions(project, BuildOptions{Kind: KindBase, Tag: "local"})
	if err != nil {
		t.Fatal(err)
	}
	if specs[0].Distro != "humble" || !strings.Contains(strings.Join(specs[0].Command, " "), "ROS_DISTRO=humble") {
		t.Fatalf("spec = %#v", specs[0])
	}

	t.Setenv("NAVLAB_SIM_DISTRO", "jazzy")
	specs, err = ResolveBuildSpecsWithOptions(project, BuildOptions{Kind: KindBase, Tag: "local"})
	if err != nil {
		t.Fatal(err)
	}
	if specs[0].Distro != "jazzy" || !strings.Contains(strings.Join(specs[0].Command, " "), "ROS_DISTRO=jazzy") {
		t.Fatalf("spec = %#v", specs[0])
	}
}

func TestResolveBuildSpecsRejectsDistroPrefixedTagMismatch(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "jazzy")
	_, err := ResolveBuildSpecsWithOptions(testProject(), BuildOptions{Kind: KindRuntime, Tag: "humble-latest"})
	if err == nil || !strings.Contains(err.Error(), `image tag "humble-latest" targets ROS distro "humble" but selected distro is "jazzy"`) {
		t.Fatalf("err = %v", err)
	}
}

func TestResolveBuildSpecsRejectsUnsupportedDistro(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "iron")
	_, err := ResolveBuildSpecsWithOptions(testProject(), BuildOptions{Kind: KindBase, Tag: "local"})
	if err == nil || !strings.Contains(err.Error(), "unsupported ROS distro") {
		t.Fatalf("err = %v", err)
	}
}

func TestResolveBuildSpecsRejectsUnsupportedTagPolicy(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	project := testProject()
	project.Navlab.Images.TagPolicy = "latest"
	_, err := ResolveBuildSpecsWithOptions(project, BuildOptions{Kind: KindBase})
	if err == nil || !strings.Contains(err.Error(), "expected distro-git-commit, distro-datetime, or distro-latest") {
		t.Fatalf("err = %v", err)
	}
}

func TestBuildDryRunDoesNotRunDocker(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	client := &fakeDockerBuildClient{}
	result, err := Build(context.Background(), testProject(), BuildOptions{
		Kind:   KindRuntime,
		Image:  KindSlam,
		Tag:    "local",
		DryRun: true,
		Client: client,
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(result.Specs) != 1 || result.Specs[0].Kind != KindSlam {
		t.Fatalf("result = %#v", result)
	}
	if len(client.calls) != 0 {
		t.Fatalf("client calls = %#v", client.calls)
	}
}

func TestBuildRunsDockerSDKBuild(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	client := &fakeDockerBuildClient{}
	var stdout bytes.Buffer
	_, err := Build(context.Background(), testProject(), BuildOptions{
		Kind:   KindRuntime,
		Image:  KindGazeboSensor,
		Tag:    "local",
		Client: client,
		Stdout: &stdout,
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(client.calls) != 1 {
		t.Fatalf("client calls = %#v", client.calls)
	}
	call := client.calls[0]
	if !reflect.DeepEqual(call.Tags, []string{"navlab/gazebo-sensor:local"}) {
		t.Fatalf("tags = %#v", call.Tags)
	}
	if call.Dockerfile != "docker/images/runtime/gazebo-sensor.Dockerfile" {
		t.Fatalf("dockerfile = %q", call.Dockerfile)
	}
	if call.BuildArgs["ROS_DISTRO"] == nil || *call.BuildArgs["ROS_DISTRO"] != "humble" {
		t.Fatalf("build args = %#v", call.BuildArgs)
	}
	if !strings.Contains(stdout.String(), "Building NavLab gazebo-sensor image") {
		t.Fatalf("stdout = %q", stdout.String())
	}
	if !strings.Contains(stdout.String(), "sdk build output") {
		t.Fatalf("stdout missing SDK output = %q", stdout.String())
	}
}

func TestBuildReturnsSDKError(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	client := &fakeDockerBuildClient{err: errors.New("docker sdk failed")}
	_, err := Build(context.Background(), testProject(), BuildOptions{
		Kind:   KindRuntime,
		Image:  KindCompanion,
		Client: client,
	})
	if err == nil || !strings.Contains(err.Error(), "docker sdk failed") {
		t.Fatalf("err = %v", err)
	}
}

func TestResolveBuildSpecsRejectsInvalidKind(t *testing.T) {
	t.Setenv("NAVLAB_SIM_DISTRO", "")
	_, err := ResolveBuildSpecsWithOptions(testProject(), BuildOptions{Kind: "bad"})
	if err == nil || !strings.Contains(err.Error(), "invalid image group") {
		t.Fatalf("err = %v", err)
	}
}

func testProject() config.ProjectConfig {
	return config.ProjectConfig{
		Paths: config.PathConfig{WorkspaceRoot: "/workspace"},
		Navlab: config.NavlabConfig{Images: config.ImageCatalog{
			TagPolicy: "distro-latest",
		}},
		Images: map[string]config.Image{
			"ros_base": {
				Group:      KindBase,
				Repository: "navlab/ros-base",
				Dockerfile: "docker/images/base/ros-base.Dockerfile",
				Context:    ".",
			},
			"ardupilot_sitl": {
				Group:      GroupInfra,
				Repository: "navlab/ardupilot-sitl",
				Dockerfile: "docker/images/infra/ardupilot-sitl.Dockerfile",
				Context:    ".",
			},
			"mavlink_router": {
				Group:      GroupInfra,
				Repository: "navlab/mavlink-router",
				Dockerfile: "docker/images/infra/mavlink-router.Dockerfile",
				Context:    ".",
			},
			"gazebo_headless": {
				Group:      GroupInfra,
				Repository: "navlab/gazebo-headless",
				Dockerfile: "docker/images/infra/gazebo-headless.Dockerfile",
				Context:    ".",
			},
			"fast_lio": {
				Group:      GroupInfra,
				Repository: "navlab/fast-lio",
				Dockerfile: "docker/images/infra/fast-lio.Dockerfile",
				Context:    ".",
			},
			"companion": {
				Group:      GroupRuntime,
				Repository: "navlab/companion",
				Dockerfile: "docker/images/runtime/companion.Dockerfile",
				Context:    ".",
				Target:     "navlab-companion",
			},
			"slam": {
				Group:      GroupRuntime,
				Repository: "navlab/slam-cartographer",
				Dockerfile: "docker/images/runtime/slam.Dockerfile",
				Context:    ".",
				Target:     "navlab-slam-cartographer",
			},
			"gazebo_sensor": {
				Group:      GroupRuntime,
				Repository: "navlab/gazebo-sensor",
				Dockerfile: "docker/images/runtime/gazebo-sensor.Dockerfile",
				Context:    ".",
				Target:     "navlab-gazebo-sensor",
			},
			"official_baseline": {
				Group:      GroupRuntime,
				Repository: "navlab/official-baseline",
				Dockerfile: "docker/images/runtime/official-baseline.Dockerfile",
				Context:    ".",
				Target:     "navlab-official-baseline",
			},
		},
	}
}
