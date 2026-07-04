package foxglove

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestResolveRunDirFindsLatestSimRunForTask(t *testing.T) {
	repoRoot := t.TempDir()
	artifactRoot := filepath.Join(repoRoot, "artifacts", "sim")
	mustMkdir(t, filepath.Join(artifactRoot, "navigation", "20260614T010000Z"))
	want := filepath.Join(artifactRoot, "navigation", "20260614T020000Z")
	mustMkdir(t, want)
	mustMkdir(t, filepath.Join(artifactRoot, "hover", "20260614T030000Z"))

	got, err := ResolveRunDir(repoRoot, "artifacts/sim", "navigation", "")
	if err != nil {
		t.Fatal(err)
	}
	if got != want {
		t.Fatalf("run dir = %q, want %q", got, want)
	}
}

func TestBuildTargetsRejectsRawUpload(t *testing.T) {
	runDir := makeRun(t, "navigation", "20260614T093531Z")
	mustWrite(t, filepath.Join(runDir, "rosbag", "navigation_rosbag", "navigation_rosbag_0.mcap"), "mcap")
	mustWriteJSON(t, filepath.Join(runDir, "summary.json"), validTaskSummary("navigation"))

	_, err := BuildTargets(runDir, "navigation", false, "navlab/sim")
	if err == nil || !strings.Contains(err.Error(), "raw task MCAP upload is disabled") {
		t.Fatalf("err = %v", err)
	}
}

func TestBuildTargetsUsesLiteMcapAndReplaySummary(t *testing.T) {
	runDir := makeRun(t, "hover", "20260614T010000Z")
	mustWrite(t, filepath.Join(runDir, "rosbag_foxglove", "rosbag_foxglove_0.mcap"), "lite")
	mustWriteJSON(t, filepath.Join(runDir, "summary.json"), validTaskSummary("hover"))
	mustWriteLiteReplaySummary(t, runDir, requiredLiteTopicsByTask["hover"])

	targets, err := BuildTargets(runDir, "hover", true, "navlab/sim")
	if err != nil {
		t.Fatal(err)
	}
	if len(targets) != 3 {
		t.Fatalf("targets = %#v", targets)
	}
	if !strings.HasSuffix(targets[0].Path, "rosbag_foxglove/rosbag_foxglove_0.mcap") {
		t.Fatalf("mcap target = %#v", targets[0])
	}
	wantDigest := fmt.Sprintf("%x", sha256.Sum256([]byte("lite")))[:12]
	if targets[0].Filename != "navlab_hover_20260614T010000Z_lite_"+wantDigest+".mcap" {
		t.Fatalf("filename = %q", targets[0].Filename)
	}
	if targets[0].Key != "navlab/sim/hover/20260614T010000Z/rosbag_foxglove_0_"+wantDigest+".mcap" {
		t.Fatalf("key = %q", targets[0].Key)
	}
	if targets[2].Kind != "replay_summary" {
		t.Fatalf("targets = %#v", targets)
	}
}

func TestBuildTargetsFailsWhenLiteMissing(t *testing.T) {
	runDir := makeRun(t, "navigation", "20260614T010000Z")
	mustWriteJSON(t, filepath.Join(runDir, "summary.json"), validTaskSummary("navigation"))

	_, err := BuildTargets(runDir, "navigation", true, "navlab/sim")
	if err == nil || !strings.Contains(err.Error(), "required lite replay summary missing") {
		t.Fatalf("err = %v", err)
	}
}

func TestBuildTargetsRejectsLegacyRawMcapLayout(t *testing.T) {
	runDir := makeRun(t, "navigation", "20260614T010000Z")
	mustWrite(t, filepath.Join(runDir, "rosbag", "rosbag_0.mcap"), "legacy")
	mustWriteJSON(t, filepath.Join(runDir, "summary.json"), validTaskSummary("navigation"))

	_, err := BuildTargets(runDir, "navigation", false, "navlab/sim")
	if err == nil || !strings.Contains(err.Error(), "raw task MCAP upload is disabled") {
		t.Fatalf("err = %v", err)
	}
}

func TestBuildTargetsRejectsLiteMissingOfficialMazeMap(t *testing.T) {
	runDir := makeRun(t, "hover", "20260614T010000Z")
	mustWrite(t, filepath.Join(runDir, "rosbag_foxglove", "rosbag_foxglove_0.mcap"), "lite")
	mustWriteJSON(t, filepath.Join(runDir, "summary.json"), validTaskSummary("hover"))
	topics := append([]string{}, requiredLiteTopicsByTask["hover"]...)
	topics = removeTopic(topics, "/navlab/official_maze/map")
	mustWriteLiteReplaySummary(t, runDir, topics)

	_, err := BuildTargets(runDir, "hover", true, "navlab/sim")
	if err == nil || !strings.Contains(err.Error(), "/navlab/official_maze/map") {
		t.Fatalf("err = %v", err)
	}
}

func TestBuildTargetsUsesLiteTopicProfile(t *testing.T) {
	runDir := makeRun(t, "hover", "20260614T010000Z")
	mustWriteLiteProfile(t, runDir, "hover", `
overlay /navlab/official_maze/map
required /map interval=all
required /navlab/custom/status interval=all
optional /scan interval=0.10
drop /clock
`)
	mustWrite(t, filepath.Join(runDir, "rosbag_foxglove", "rosbag_foxglove_0.mcap"), "lite")
	mustWriteJSON(t, filepath.Join(runDir, "summary.json"), validTaskSummary("hover"))
	mustWriteLiteReplaySummary(t, runDir, []string{"/navlab/official_maze/map", "/map", "/navlab/custom/status"})

	targets, err := BuildTargets(runDir, "hover", true, "navlab/sim")
	if err != nil {
		t.Fatal(err)
	}
	if len(targets) != 3 {
		t.Fatalf("targets = %#v", targets)
	}
}

func TestUploadForcesLiteSelection(t *testing.T) {
	repoRoot := t.TempDir()
	runDir := filepath.Join(repoRoot, "artifacts", "sim", "hover", "20260614T010000Z")
	mustMkdir(t, runDir)
	mustWrite(t, filepath.Join(runDir, "rosbag_foxglove", "rosbag_foxglove_0.mcap"), "lite")
	mustWriteJSON(t, filepath.Join(runDir, "summary.json"), validTaskSummary("hover"))
	mustWriteLiteReplaySummary(t, runDir, requiredLiteTopicsByTask["hover"])

	result, err := Upload(context.Background(), Options{
		RepoRoot:     repoRoot,
		ArtifactRoot: "artifacts/sim",
		Run:          "20260614T010000Z",
		Task:         "hover",
		DryRun:       true,
		Lite:         false,
		Stdout:       io.Discard,
		Stderr:       io.Discard,
	})
	if err != nil {
		t.Fatal(err)
	}
	if !result.Lite {
		t.Fatalf("result.Lite = false, want true")
	}
}

func TestUploadAutoBuildsLiteReplayWhenMissing(t *testing.T) {
	repoRoot := t.TempDir()
	runDir := filepath.Join(repoRoot, "artifacts", "sim", "hover", "20260614T020000Z")
	mustMkdir(t, runDir)
	mustWriteJSON(t, filepath.Join(runDir, "summary.json"), validTaskSummary("hover"))
	writeTestMCAP(t, filepath.Join(runDir, rawMCAPRelative("hover")), []string{
		"/navlab/official_maze/map",
		"/tf",
		"/tf_static",
		"/map",
		"/scan",
		"/slam/odom",
	})
	mustWriteLiteProfile(t, runDir, "hover", `
overlay /navlab/official_maze/map
required /tf interval=all
required /tf_static interval=all
required /map interval=all
required /scan interval=all
required /slam/odom interval=all
`)

	result, err := Upload(context.Background(), Options{
		RepoRoot:     repoRoot,
		ArtifactRoot: "artifacts/sim",
		Run:          "20260614T020000Z",
		Task:         "hover",
		DryRun:       true,
		Stdout:       io.Discard,
		Stderr:       io.Discard,
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(result.Files) != 3 {
		t.Fatalf("files = %#v", result.Files)
	}
	if !fileExists(filepath.Join(runDir, "rosbag_foxglove", "rosbag_foxglove_0.mcap")) {
		t.Fatal("lite replay MCAP was not generated")
	}
	if !fileExists(filepath.Join(runDir, defaultReplaySummary)) {
		t.Fatal("lite replay summary was not generated")
	}
	if !strings.Contains(result.Files[0].Filename, "_lite_") {
		t.Fatalf("lite target did not get digest suffix: %#v", result.Files[0])
	}
}

func TestPrintTargetsUsesReadableSections(t *testing.T) {
	var stdout strings.Builder
	printTargets(&stdout, "Foxglove Upload Targets", Result{
		RunID:  "20260622T123922Z",
		TaskID: "hover",
		RunDir: "/tmp/navlab/run",
		Lite:   true,
		Files: []UploadTarget{{
			Kind:     "mcap",
			Path:     "/tmp/navlab/run/rosbag_foxglove/rosbag_foxglove_0.mcap",
			Filename: "navlab_hover_20260622T123922Z_lite_8a9ece543cbc.mcap",
			Key:      "navlab/sim/hover/20260622T123922Z/rosbag_foxglove_0_8a9ece543cbc.mcap",
			Bytes:    2_575_812,
		}},
	})
	output := stdout.String()
	for _, want := range []string{
		"Foxglove Upload Targets",
		"run_id=20260622T123922Z",
		"mode=lite",
		"Files",
		"- mcap",
		"2.5 MiB",
		"key=navlab/sim/hover/20260622T123922Z/rosbag_foxglove_0_8a9ece543cbc.mcap",
		"path=/tmp/navlab/run/rosbag_foxglove/rosbag_foxglove_0.mcap",
	} {
		if !strings.Contains(output, want) {
			t.Fatalf("formatted upload targets missing %q:\n%s", want, output)
		}
	}
	if strings.Contains(output, "\tmcap\t") || strings.Contains(output, "\t2575812\t") {
		t.Fatalf("formatted upload targets still look like a tab table:\n%s", output)
	}
}

func TestUploadWritesFailureSummaryOnUploadError(t *testing.T) {
	repoRoot := t.TempDir()
	runDir := filepath.Join(repoRoot, "artifacts", "sim", "hover", "20260614T010000Z")
	mustMkdir(t, runDir)
	mustWrite(t, filepath.Join(runDir, "rosbag_foxglove", "rosbag_foxglove_0.mcap"), "lite")
	mustWriteJSON(t, filepath.Join(runDir, "summary.json"), validTaskSummary("hover"))
	mustWriteLiteReplaySummary(t, runDir, requiredLiteTopicsByTask["hover"])
	t.Setenv(defaultTokenEnv, "test-token")

	_, err := Upload(context.Background(), Options{
		RepoRoot:     repoRoot,
		ArtifactRoot: "artifacts/sim",
		Run:          "20260614T010000Z",
		Task:         "hover",
		Force:        true,
		HTTPClient: &http.Client{Transport: roundTripFunc(func(*http.Request) (*http.Response, error) {
			return nil, errors.New("network closed")
		})},
		Stdout: io.Discard,
		Stderr: io.Discard,
	})
	if err == nil || !strings.Contains(err.Error(), "network closed") {
		t.Fatalf("err = %v", err)
	}

	data, readErr := os.ReadFile(filepath.Join(runDir, defaultUploadSummary))
	if readErr != nil {
		t.Fatal(readErr)
	}
	var summary Result
	if err := json.Unmarshal(data, &summary); err != nil {
		t.Fatal(err)
	}
	if summary.OK || summary.State != "failed" {
		t.Fatalf("summary = %#v", summary)
	}
	if summary.FailedFile == "" || !strings.Contains(summary.Error, "network closed") {
		t.Fatalf("summary = %#v", summary)
	}
}

func TestUploadUsesAPIURLFromDotenv(t *testing.T) {
	repoRoot := t.TempDir()
	runDir := filepath.Join(repoRoot, "artifacts", "sim", "hover", "20260614T010000Z")
	mustMkdir(t, runDir)
	mustWrite(t, filepath.Join(runDir, "rosbag_foxglove", "rosbag_foxglove_0.mcap"), "lite")
	mustWriteJSON(t, filepath.Join(runDir, "summary.json"), validTaskSummary("hover"))
	mustWriteLiteReplaySummary(t, runDir, requiredLiteTopicsByTask["hover"])
	mustWrite(t, filepath.Join(repoRoot, ".env"), "FOXGLOVE_API_URL=https://foxglove.example.test/v1\n")

	result, err := Upload(context.Background(), Options{
		RepoRoot:     repoRoot,
		ArtifactRoot: "artifacts/sim",
		Run:          "20260614T010000Z",
		Task:         "hover",
		DryRun:       true,
		Stdout:       io.Discard,
		Stderr:       io.Discard,
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.APIURL != "https://foxglove.example.test/v1" {
		t.Fatalf("APIURL = %q", result.APIURL)
	}
}

func TestBuildTargetsRejectsBlockedTaskSummary(t *testing.T) {
	runDir := makeRun(t, "hover", "20260614T010000Z")
	mustWrite(t, filepath.Join(runDir, "rosbag_foxglove", "rosbag_foxglove_0.mcap"), "lite")
	mustWriteJSON(t, filepath.Join(runDir, "summary.json"), map[string]any{
		"task_id":      "hover",
		"ok":           false,
		"blocked":      true,
		"blockerCodes": []string{"hover_takeoff_target_altitude_not_reached"},
	})
	mustWriteLiteReplaySummary(t, runDir, requiredLiteTopicsByTask["hover"])

	_, err := BuildTargets(runDir, "hover", true, "navlab/sim")
	if err == nil || !strings.Contains(err.Error(), "task summary is not ok") {
		t.Fatalf("err = %v", err)
	}
}

func TestDefaultHTTPClientDisablesHTTP2(t *testing.T) {
	client := defaultHTTPClient()
	transport, ok := client.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("transport = %T, want *http.Transport", client.Transport)
	}
	if transport.ForceAttemptHTTP2 {
		t.Fatal("ForceAttemptHTTP2 = true, want false")
	}
	if transport.TLSNextProto == nil {
		t.Fatal("TLSNextProto = nil, want empty map to disable HTTP/2")
	}
	if len(transport.TLSNextProto) != 0 {
		t.Fatalf("TLSNextProto = %#v, want empty map", transport.TLSNextProto)
	}
	if transport.TLSClientConfig == nil {
		t.Fatal("TLSClientConfig = nil, want explicit http/1.1 ALPN")
	}
	if got := transport.TLSClientConfig.NextProtos; len(got) != 1 || got[0] != "http/1.1" {
		t.Fatalf("TLSClientConfig.NextProtos = %#v, want [http/1.1]", got)
	}
}

func TestResolveRunDirRejectsLegacyArtifactRoot(t *testing.T) {
	repoRoot := t.TempDir()
	mustMkdir(t, filepath.Join(repoRoot, "artifacts", "sim", "navigation", "20260614T010000Z"))
	legacyRun := filepath.Join(repoRoot, "artifacts", "ros", "navlab_companion_sitl_gazebo", "20260609_110400")
	mustMkdir(t, legacyRun)

	_, err := ResolveRunDir(repoRoot, "artifacts/sim", "", legacyRun)
	if err == nil || !strings.Contains(err.Error(), "run directory not found") {
		t.Fatalf("err = %v", err)
	}
}

func makeRun(t *testing.T, task string, runID string) string {
	t.Helper()
	runDir := filepath.Join(t.TempDir(), "artifacts", "sim", task, runID)
	mustMkdir(t, runDir)
	return runDir
}

func validTaskSummary(task string) map[string]any {
	return map[string]any{
		"task_id": task,
		"ok":      true,
		"blocked": false,
		"status":  "passed",
	}
}

func repoRootFromRunDir(runDir string) string {
	return filepath.Dir(filepath.Dir(filepath.Dir(filepath.Dir(runDir))))
}

func mustWriteLiteProfile(t *testing.T, runDir string, task string, content string) {
	t.Helper()
	filename, ok := liteProfileFilenameByTask[sanitizeTask(task)]
	if !ok {
		t.Fatalf("missing lite profile filename for task %s", task)
	}
	mustWrite(t, filepath.Join(repoRootFromRunDir(runDir), "docker", "profiles", filename), strings.TrimSpace(content)+"\n")
}

func mustWriteLiteReplaySummary(t *testing.T, runDir string, topics []string) {
	t.Helper()
	counts := make(map[string]int, len(topics))
	for _, topic := range topics {
		counts[topic] = 1
	}
	mustWriteJSON(t, filepath.Join(runDir, "foxglove_replay_summary.json"), map[string]any{
		"ok": true,
		"task_summary": map[string]any{
			"path": filepath.Join(runDir, "summary.json"),
			"ok":   true,
		},
		"replay_mcap": map[string]any{
			"message_counts": counts,
		},
	})
}

func removeTopic(topics []string, drop string) []string {
	result := make([]string, 0, len(topics))
	for _, topic := range topics {
		if topic != drop {
			result = append(result, topic)
		}
	}
	return result
}

func mustMkdir(t *testing.T, path string) {
	t.Helper()
	if err := os.MkdirAll(path, 0o755); err != nil {
		t.Fatal(err)
	}
}

func mustWrite(t *testing.T, path string, value string) {
	t.Helper()
	mustMkdir(t, filepath.Dir(path))
	if err := os.WriteFile(path, []byte(value), 0o644); err != nil {
		t.Fatal(err)
	}
}

func mustWriteJSON(t *testing.T, path string, value any) {
	t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		t.Fatal(err)
	}
	mustMkdir(t, filepath.Dir(path))
	if err := os.WriteFile(path, data, 0o644); err != nil {
		t.Fatal(err)
	}
}

type roundTripFunc func(*http.Request) (*http.Response, error)

func (fn roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return fn(request)
}
