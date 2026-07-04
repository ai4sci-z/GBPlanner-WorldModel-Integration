package foxglove

import (
	"bytes"
	"context"
	"crypto/sha256"
	"crypto/tls"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"navlab/orchestration-sim/internal/ui"
)

const (
	defaultAPIURL            = "https://api.foxglove.dev/v1"
	defaultTokenEnv          = "FOXGLOVE_API_TOKEN"
	defaultDeviceName        = "navlab_sim"
	defaultKeyPrefix         = "navlab/sim"
	defaultMaxUploadAttempts = 3
	defaultSummaryFilename   = "summary.json"
	defaultReplaySummary     = "foxglove_replay_summary.json"
	defaultUploadSummary     = "foxglove_upload_summary.json"
)

var requiredLiteTopicsByTask = map[string][]string{
	"hover": {
		"/navlab/official_maze/map",
		"/tf",
		"/tf_static",
		"/map",
		"/scan",
		"/slam/odom",
		"/navlab/hover/status",
		"/navlab/landing/status",
		"/rangefinder/down/range",
	},
	"exploration": {
		"/navlab/official_maze/map",
		"/tf",
		"/tf_static",
		"/map",
		"/scan",
		"/slam/odom",
		"/navlab/exploration/status",
		"/navlab/fcu/controller/status",
		"/navlab/fcu/setpoint/intent",
		"/navlab/fcu/setpoint/output",
		"/rangefinder/down/range",
	},
	"navigation": {
		"/navlab/official_maze/map",
		"/tf",
		"/tf_static",
		"/map",
		"/scan",
		"/slam/odom",
		"/navlab/slam/status",
		"/navlab/fcu/controller/status",
		"/navlab/fcu/setpoint/output",
		"/rangefinder/down/range",
		"/navlab/landing/status",
	},
	"scan-robustness": {
		"/navlab/official_maze/map",
		"/tf",
		"/tf_static",
		"/map",
		"/scan",
		"/slam/odom",
	},
}

var liteProfileFilenameByTask = map[string]string{
	"hover":       "navlab-hover-foxglove-lite-topics.txt",
	"exploration": "navlab-exploration-foxglove-lite-topics.txt",
	"navigation":  "navlab-navigation-foxglove-lite-topics.txt",
}

type liteTopicProfile struct {
	Path          string
	Overlay       []string
	Required      []string
	Optional      []string
	Drop          []string
	FrameRewrites []frameRewriteProfile
	DerivedScans  []derivedScanProfile
	DerivedTFs    []derivedTFProfile
	DerivedMapTFs []derivedMapTFProfile
	Interval      map[string]float64
}

type Options struct {
	RepoRoot     string
	ArtifactRoot string
	Run          string
	Task         string
	DryRun       bool
	Force        bool
	Lite         bool
	EnvPath      string
	APIURL       string
	TokenEnv     string
	ProjectID    string
	DeviceID     string
	DeviceName   string
	KeyPrefix    string
	HTTPClient   *http.Client
	Stdout       io.Writer
	Stderr       io.Writer
}

type UploadTarget struct {
	Kind     string `json:"kind"`
	Path     string `json:"path"`
	Filename string `json:"filename"`
	Key      string `json:"key"`
	Bytes    int64  `json:"bytes"`
}

type Result struct {
	OK          bool           `json:"ok"`
	State       string         `json:"state"`
	Reason      string         `json:"reason"`
	Error       string         `json:"error,omitempty"`
	RunDir      string         `json:"run_dir"`
	TaskID      string         `json:"task_id"`
	RunID       string         `json:"run_id"`
	Lite        bool           `json:"lite"`
	APIURL      string         `json:"api_url,omitempty"`
	TokenEnv    string         `json:"token_env,omitempty"`
	Files       []UploadTarget `json:"files"`
	Uploaded    []UploadedFile `json:"uploaded,omitempty"`
	FailedFile  string         `json:"failed_file,omitempty"`
	GeneratedAt string         `json:"generated_at,omitempty"`
}

type UploadedFile struct {
	Kind      string `json:"kind"`
	Path      string `json:"path"`
	Filename  string `json:"filename"`
	Key       string `json:"key"`
	RequestID string `json:"request_id,omitempty"`
}

type uploadLink struct {
	RequestID string
	URL       string
}

func Upload(ctx context.Context, options Options) (Result, error) {
	options = withDefaults(options)
	if err := loadDotenv(options.EnvPath); err != nil {
		return Result{}, err
	}
	if options.APIURL == defaultAPIURL {
		if apiURL := firstEnv("FOXGLOVE_API_URL", "FOXGLOVE_API_BASE_URL"); apiURL != "" {
			options.APIURL = apiURL
		}
	}
	runDir, err := ResolveRunDir(options.RepoRoot, options.ArtifactRoot, options.Task, options.Run)
	if err != nil {
		return Result{}, err
	}
	taskID := resolveTaskID(runDir, options.Task)
	runID := filepath.Base(runDir)
	options.Lite = true
	if err := ensureLiteReplay(runDir, taskID, options); err != nil {
		return Result{}, err
	}
	targets, err := BuildTargets(runDir, taskID, options.Lite, options.KeyPrefix)
	if err != nil {
		return Result{}, err
	}
	result := Result{
		OK:          true,
		State:       "dry_run",
		Reason:      "resolved upload targets only",
		RunDir:      runDir,
		TaskID:      taskID,
		RunID:       runID,
		Lite:        options.Lite,
		APIURL:      options.APIURL,
		TokenEnv:    options.TokenEnv,
		Files:       targets,
		GeneratedAt: time.Now().UTC().Format(time.RFC3339),
	}
	printTargets(options.Stdout, "Foxglove Upload Targets", result)
	if options.DryRun {
		return result, nil
	}
	if !options.Force {
		return Result{}, errors.New("upload requires --force")
	}
	token := strings.TrimSpace(os.Getenv(options.TokenEnv))
	if token == "" {
		result.OK = false
		result.State = "failed"
		result.Reason = "missing Foxglove API token"
		result.Error = fmt.Sprintf("missing token env %s", options.TokenEnv)
		if writeErr := writeUploadSummary(runDir, options.Stdout, result); writeErr != nil {
			return result, fmt.Errorf("%s; write upload summary: %w", result.Error, writeErr)
		}
		return result, errors.New(result.Error)
	}
	uploaded := make([]UploadedFile, 0, len(targets))
	for _, target := range targets {
		link, err := uploadWithRetries(ctx, options, token, target)
		if err != nil {
			result.OK = false
			result.State = "failed"
			result.Reason = "upload failed"
			result.Error = fmt.Sprintf("upload %s: %v", target.Filename, err)
			result.FailedFile = target.Filename
			result.Uploaded = uploaded
			if writeErr := writeUploadSummary(runDir, options.Stdout, result); writeErr != nil {
				return result, fmt.Errorf("%s; write upload summary: %w", result.Error, writeErr)
			}
			return result, errors.New(result.Error)
		}
		uploaded = append(uploaded, UploadedFile{
			Kind:      target.Kind,
			Path:      target.Path,
			Filename:  target.Filename,
			Key:       target.Key,
			RequestID: link.RequestID,
		})
	}
	result.State = "uploaded"
	result.Reason = "uploaded to Foxglove cloud"
	result.Uploaded = uploaded
	if err := writeUploadSummary(runDir, options.Stdout, result); err != nil {
		return Result{}, fmt.Errorf("write upload summary: %w", err)
	}
	return result, nil
}

func ensureLiteReplay(runDir string, taskID string, options Options) error {
	if fileExists(filepath.Join(runDir, defaultReplaySummary)) && fileExists(filepath.Join(runDir, defaultLiteRelativePath)) {
		return nil
	}
	_, err := BuildReplay(ReplayOptions{
		RepoRoot:     options.RepoRoot,
		ArtifactRoot: options.ArtifactRoot,
		Run:          runDir,
		Task:         taskID,
		Stdout:       options.Stdout,
	})
	if err != nil {
		return fmt.Errorf("auto-build lite replay: %w", err)
	}
	return nil
}

func writeUploadSummary(runDir string, stdout io.Writer, result Result) error {
	summaryPath := filepath.Join(runDir, defaultUploadSummary)
	if err := writeJSON(summaryPath, result); err != nil {
		return err
	}
	_, _ = fmt.Fprintf(stdout, "\n%s\n", ui.Subtitle("Summary"))
	_, _ = fmt.Fprintf(stdout, "  %s\n", ui.KeyValue("upload_summary", summaryPath))
	return nil
}

func ResolveRunDir(repoRoot string, artifactRoot string, task string, run string) (string, error) {
	if strings.TrimSpace(repoRoot) == "" {
		repoRoot = "."
	}
	repoRoot, _ = filepath.Abs(repoRoot)
	artifactRoot = resolvePath(repoRoot, artifactRoot)
	if strings.TrimSpace(run) != "" {
		if path, ok := existingDir(resolvePath(repoRoot, run)); ok && pathInsideRoot(path, artifactRoot) {
			return path, nil
		}
		if strings.TrimSpace(task) != "" {
			if path, ok := existingDir(filepath.Join(artifactRoot, sanitizeTask(task), run)); ok {
				return path, nil
			}
		}
		matches, err := findRunMatches(artifactRoot, run)
		if err != nil {
			return "", err
		}
		if len(matches) == 1 {
			return matches[0], nil
		}
		if len(matches) > 1 {
			return "", fmt.Errorf("run id %q is ambiguous; pass --task", run)
		}
		return "", fmt.Errorf("run directory not found: %s", run)
	}
	if strings.TrimSpace(task) != "" {
		return latestRunDir(filepath.Join(artifactRoot, sanitizeTask(task)))
	}
	return latestRunAcrossTasks(artifactRoot)
}

func BuildTargets(runDir string, taskID string, lite bool, keyPrefix string) ([]UploadTarget, error) {
	if !lite {
		return nil, errors.New("foxglove upload requires lite MCAP; raw task MCAP upload is disabled")
	}
	gate, err := readTaskSummaryGate(runDir)
	if err != nil {
		return nil, err
	}
	if !gate.OK {
		return nil, fmt.Errorf("task summary is not ok: %s", gate.reason())
	}
	runID := filepath.Base(runDir)
	taskKind := sanitizeTask(taskID)
	if taskKind == "" {
		taskKind = "run"
	}
	if keyPrefix == "" {
		keyPrefix = defaultKeyPrefix
	}
	baseKey := strings.TrimRight(keyPrefix, "/") + "/" + taskKind + "/" + runID
	mcapPath, mcapSourceName, err := resolveMCAPPath(runDir, taskID, lite)
	if err != nil {
		return nil, err
	}
	targets := []UploadTarget{
		newMCAPTarget(mcapPath, taskKind, runID, lite, baseKey, mcapSourceName),
		newTarget("summary", filepath.Join(runDir, defaultSummaryFilename), fmt.Sprintf("navlab_%s_%s_summary.json", taskKind, runID), baseKey+"/attachments/"+defaultSummaryFilename),
	}
	replaySummary := filepath.Join(runDir, defaultReplaySummary)
	if !fileExists(replaySummary) {
		return nil, fmt.Errorf("required lite replay summary missing: %s", replaySummary)
	}
	if err := validateLiteReplaySummary(replaySummary, taskKind); err != nil {
		return nil, err
	}
	targets = append(targets, newTarget("replay_summary", replaySummary, fmt.Sprintf("navlab_%s_%s_foxglove_replay_summary.json", taskKind, runID), baseKey+"/attachments/"+defaultReplaySummary))
	for _, target := range targets {
		if !fileExists(target.Path) {
			return nil, fmt.Errorf("required upload file missing: %s", target.Path)
		}
	}
	return targets, nil
}

func resolveMCAPPath(runDir string, taskID string, lite bool) (string, string, error) {
	_ = lite
	_ = taskID
	path := filepath.Join(runDir, "rosbag_foxglove", "rosbag_foxglove_0.mcap")
	return path, "rosbag_foxglove_0.mcap", nil
}

func validateLiteReplaySummary(path string, taskID string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read lite replay summary: %w", err)
	}
	var payload map[string]any
	if err := json.Unmarshal(data, &payload); err != nil {
		return fmt.Errorf("parse lite replay summary: %w", err)
	}
	if ok, _ := payload["ok"].(bool); !ok {
		return fmt.Errorf("lite replay summary is not ok: %s", path)
	}
	taskSummary, ok := payload["task_summary"].(map[string]any)
	if !ok {
		return fmt.Errorf("lite replay summary missing task_summary: %s", path)
	}
	if summaryPath, _ := taskSummary["path"].(string); summaryPath == "" {
		return fmt.Errorf("lite replay summary missing task_summary.path: %s", path)
	}
	if ok, _ := taskSummary["ok"].(bool); !ok {
		return fmt.Errorf("lite replay summary task_summary is not ok: %s", path)
	}
	replay, ok := payload["replay_mcap"].(map[string]any)
	if !ok {
		return fmt.Errorf("lite replay summary missing replay_mcap: %s", path)
	}
	counts, ok := replay["message_counts"].(map[string]any)
	if !ok {
		return fmt.Errorf("lite replay summary missing replay_mcap.message_counts: %s", path)
	}
	required, err := liteUploadRequiredTopics(filepath.Dir(path), taskID)
	if err != nil {
		return err
	}
	var missing []string
	for _, topic := range required {
		if numericCount(counts[topic]) <= 0 {
			missing = append(missing, topic)
		}
	}
	if len(missing) > 0 {
		return fmt.Errorf("lite replay summary missing required topics %s: %s", strings.Join(missing, ", "), path)
	}
	return nil
}

func liteUploadRequiredTopics(runDir string, taskID string) ([]string, error) {
	taskKind := sanitizeTask(taskID)
	if profilePath, ok := liteProfilePath(runDir, taskKind); ok {
		profile, err := readLiteTopicProfile(profilePath)
		if err != nil {
			return nil, err
		}
		required := uniqueStrings(append(append([]string{}, profile.Overlay...), profile.Required...))
		if len(required) == 0 {
			return nil, fmt.Errorf("lite topic profile has no overlay or required topics: %s", profilePath)
		}
		return required, nil
	}
	required := requiredLiteTopicsByTask[taskKind]
	if len(required) == 0 {
		required = []string{"/navlab/official_maze/map", "/tf", "/tf_static", "/map", "/scan", "/slam/odom"}
	}
	return required, nil
}

func liteProfilePath(runDir string, taskID string) (string, bool) {
	filename := liteProfileFilenameByTask[sanitizeTask(taskID)]
	if filename == "" {
		return "", false
	}
	repoRoot, ok := discoverRepoRoot(runDir)
	if !ok {
		return "", false
	}
	path := filepath.Join(repoRoot, "docker", "profiles", filename)
	if !fileExists(path) {
		return "", false
	}
	return path, true
}

func readLiteTopicProfile(path string) (liteTopicProfile, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return liteTopicProfile{}, fmt.Errorf("read lite topic profile: %w", err)
	}
	profile := liteTopicProfile{Path: path, Interval: map[string]float64{}}
	for index, rawLine := range strings.Split(string(data), "\n") {
		line := strings.TrimSpace(strings.SplitN(rawLine, "#", 2)[0])
		if line == "" {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) < 2 {
			return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: %q", index+1, path, rawLine)
		}
		topic := fields[1]
		if !strings.HasPrefix(topic, "/") {
			return liteTopicProfile{}, fmt.Errorf("lite topic profile line %d topic must be absolute in %s: %q", index+1, path, topic)
		}
		switch fields[0] {
		case "overlay":
			profile.Overlay = append(profile.Overlay, topic)
		case "required":
			interval, err := parseLiteProfileInterval(fields)
			if err != nil {
				return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: %w", index+1, path, err)
			}
			profile.Required = append(profile.Required, topic)
			profile.Interval[topic] = interval
		case "optional":
			interval, err := parseLiteProfileInterval(fields)
			if err != nil {
				return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: %w", index+1, path, err)
			}
			profile.Optional = append(profile.Optional, topic)
			profile.Interval[topic] = interval
		case "drop":
			profile.Drop = append(profile.Drop, topic)
		case "rewrite_frame":
			spec := frameRewriteProfile{Topic: topic}
			for _, field := range fields[2:] {
				key, value, ok := strings.Cut(field, "=")
				if !ok || value == "" {
					return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: rewrite_frame fields must be key=value", index+1, path)
				}
				switch key {
				case "frame":
					spec.FrameID = value
				case "flip_x":
					enabled, err := strconv.ParseBool(value)
					if err != nil {
						return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: flip_x must be bool", index+1, path)
					}
					spec.FlipX = enabled
				case "flip_y":
					enabled, err := strconv.ParseBool(value)
					if err != nil {
						return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: flip_y must be bool", index+1, path)
					}
					spec.FlipY = enabled
				case "scan_free_space":
					enabled, err := strconv.ParseBool(value)
					if err != nil {
						return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: scan_free_space must be bool", index+1, path)
					}
					spec.ScanFreeSpace = enabled
				case "scan_crop":
					enabled, err := strconv.ParseBool(value)
					if err != nil {
						return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: scan_crop must be bool", index+1, path)
					}
					spec.ScanCrop = enabled
				case "crop_to_known":
					enabled, err := strconv.ParseBool(value)
					if err != nil {
						return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: crop_to_known must be bool", index+1, path)
					}
					spec.CropToKnown = enabled
				case "crop_margin_m":
					margin, err := strconv.ParseFloat(value, 64)
					if err != nil || margin < 0 {
						return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: crop_margin_m must be a non-negative number", index+1, path)
					}
					spec.CropMarginM = margin
				case "role":
					spec.Role = value
				default:
					return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: unknown rewrite_frame field %q", index+1, path, key)
				}
			}
			profile.FrameRewrites = append(profile.FrameRewrites, normalizeFrameRewriteProfile(spec))
		case "derive_scan":
			spec := derivedScanProfile{Topic: topic}
			for _, field := range fields[2:] {
				key, value, ok := strings.Cut(field, "=")
				if !ok || value == "" {
					return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: derive_scan fields must be key=value", index+1, path)
				}
				switch key {
				case "source":
					spec.Source = value
				case "frame":
					spec.FrameID = value
				case "fixed_frame":
					spec.FixedFrame = value
				case "points_topic":
					spec.PointsTopic = value
				case "role":
					spec.Role = value
				default:
					return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: unknown derive_scan field %q", index+1, path, key)
				}
			}
			profile.DerivedScans = append(profile.DerivedScans, normalizeDerivedScanProfile(spec))
		case "derive_display_tf":
			spec := derivedTFProfile{Topic: topic}
			for _, field := range fields[2:] {
				key, value, ok := strings.Cut(field, "=")
				if !ok || value == "" {
					return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: derive_display_tf fields must be key=value", index+1, path)
				}
				switch key {
				case "source":
					spec.Source = value
				case "parent":
					spec.Parent = value
				case "child":
					spec.Child = value
				case "mode":
					spec.Mode = value
				case "coordinate_mode":
					spec.CoordinateMode = value
				case "role":
					spec.Role = value
				default:
					return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: unknown derive_display_tf field %q", index+1, path, key)
				}
			}
			profile.DerivedTFs = append(profile.DerivedTFs, normalizeDerivedTFProfile(spec))
		case "derive_map_tf":
			spec := derivedMapTFProfile{Topic: topic}
			for _, field := range fields[2:] {
				key, value, ok := strings.Cut(field, "=")
				if !ok || value == "" {
					return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: derive_map_tf fields must be key=value", index+1, path)
				}
				switch key {
				case "display_source":
					spec.DisplaySource = value
				case "slam_source":
					spec.SlamSource = value
				case "parent":
					spec.Parent = value
				case "child":
					spec.Child = value
				case "display_parent":
					spec.DisplayParent = value
				case "display_child":
					spec.DisplayChild = value
				case "slam_parent":
					spec.SlamParent = value
				case "slam_child":
					spec.SlamChild = value
				case "coordinate_mode":
					spec.CoordinateMode = value
				case "role":
					spec.Role = value
				default:
					return liteTopicProfile{}, fmt.Errorf("malformed lite topic profile line %d in %s: unknown derive_map_tf field %q", index+1, path, key)
				}
			}
			profile.DerivedMapTFs = append(profile.DerivedMapTFs, normalizeDerivedMapTFProfile(spec))
		default:
			return liteTopicProfile{}, fmt.Errorf("unknown lite topic profile directive %q on line %d in %s", fields[0], index+1, path)
		}
	}
	return profile, nil
}

func parseLiteProfileInterval(fields []string) (float64, error) {
	if len(fields) != 3 || !strings.HasPrefix(fields[2], "interval=") {
		return 0, errors.New("required and optional lines must be `required TOPIC interval=SECONDS|all`")
	}
	value := strings.TrimPrefix(fields[2], "interval=")
	if value == "all" {
		return 0, nil
	}
	seconds, err := strconv.ParseFloat(value, 64)
	if err != nil || seconds <= 0 {
		return 0, fmt.Errorf("interval must be a positive number or all: %s", value)
	}
	return seconds, nil
}

func discoverRepoRoot(path string) (string, bool) {
	absPath, err := filepath.Abs(path)
	if err != nil {
		return "", false
	}
	info, err := os.Stat(absPath)
	if err == nil && !info.IsDir() {
		absPath = filepath.Dir(absPath)
	}
	for {
		if _, ok := existingDir(filepath.Join(absPath, "docker", "profiles")); ok {
			return absPath, true
		}
		parent := filepath.Dir(absPath)
		if parent == absPath {
			return "", false
		}
		absPath = parent
	}
}

func uniqueStrings(values []string) []string {
	seen := make(map[string]bool, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		if value == "" || seen[value] {
			continue
		}
		seen[value] = true
		result = append(result, value)
	}
	return result
}

func numericCount(value any) int {
	switch typed := value.(type) {
	case int:
		return typed
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	case json.Number:
		count, _ := typed.Int64()
		return int(count)
	default:
		return 0
	}
}

func resolveTaskID(runDir string, override string) string {
	if strings.TrimSpace(override) != "" {
		return sanitizeTask(override)
	}
	summaryPath := filepath.Join(runDir, defaultSummaryFilename)
	data, err := os.ReadFile(summaryPath)
	if err == nil {
		var payload map[string]any
		if json.Unmarshal(data, &payload) == nil {
			if value, ok := payload["task_id"].(string); ok && value != "" {
				return sanitizeTask(value)
			}
			if value, ok := payload["taskId"].(string); ok && value != "" {
				return sanitizeTask(value)
			}
		}
	}
	parent := filepath.Base(filepath.Dir(runDir))
	if parent != "." && parent != string(filepath.Separator) {
		return sanitizeTask(parent)
	}
	return "run"
}

func uploadWithRetries(ctx context.Context, options Options, token string, target UploadTarget) (uploadLink, error) {
	var lastErr error
	attempts := defaultMaxUploadAttempts
	for attempt := 1; attempt <= attempts; attempt++ {
		link, err := uploadOne(ctx, options, token, target)
		if err == nil {
			return link, nil
		}
		lastErr = err
		if attempt < attempts {
			_, _ = fmt.Fprintf(options.Stderr, "retry %s after error: %v\n", target.Filename, err)
			time.Sleep(time.Duration(attempt) * time.Second)
		}
	}
	return uploadLink{}, lastErr
}

func uploadOne(ctx context.Context, options Options, token string, target UploadTarget) (uploadLink, error) {
	payload := map[string]string{
		"filename": target.Filename,
		"key":      target.Key,
	}
	if options.ProjectID != "" {
		payload["projectId"] = options.ProjectID
	}
	if options.DeviceID != "" {
		payload["deviceId"] = options.DeviceID
	} else if envDeviceID := strings.TrimSpace(os.Getenv("FOXGLOVE_DEVICE_ID")); envDeviceID != "" {
		payload["deviceId"] = envDeviceID
	} else if options.DeviceName != "" {
		payload["deviceName"] = options.DeviceName
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return uploadLink{}, err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(options.APIURL, "/")+"/data/upload", bytes.NewReader(body))
	if err != nil {
		return uploadLink{}, err
	}
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("Content-Type", "application/json")
	response, err := options.HTTPClient.Do(request)
	if err != nil {
		return uploadLink{}, err
	}
	defer func() { _ = response.Body.Close() }()
	responseBody, _ := io.ReadAll(response.Body)
	if response.StatusCode >= 400 {
		return uploadLink{}, fmt.Errorf("request upload link: HTTP %d %s", response.StatusCode, strings.TrimSpace(string(responseBody)))
	}
	var linkPayload map[string]any
	if err := json.Unmarshal(responseBody, &linkPayload); err != nil {
		return uploadLink{}, err
	}
	link := uploadLink{
		RequestID: firstString(linkPayload, "requestId", "request_id"),
		URL:       firstString(linkPayload, "link", "uploadUrl", "upload_url", "url"),
	}
	if link.URL == "" {
		return uploadLink{}, errors.New("upload URL missing in Foxglove response")
	}
	if err := putFile(ctx, options.HTTPClient, link.URL, target); err != nil {
		return uploadLink{}, err
	}
	return link, nil
}

func putFile(ctx context.Context, client *http.Client, url string, target UploadTarget) error {
	file, err := os.Open(target.Path)
	if err != nil {
		return err
	}
	defer func() { _ = file.Close() }()
	request, err := http.NewRequestWithContext(ctx, http.MethodPut, url, file)
	if err != nil {
		return err
	}
	request.Header.Set("Content-Type", "application/octet-stream")
	request.ContentLength = target.Bytes
	response, err := client.Do(request)
	if err != nil {
		return err
	}
	defer func() { _ = response.Body.Close() }()
	responseBody, _ := io.ReadAll(response.Body)
	if response.StatusCode >= 400 {
		return fmt.Errorf("PUT failed: HTTP %d %s", response.StatusCode, strings.TrimSpace(string(responseBody)))
	}
	return nil
}

func withDefaults(options Options) Options {
	if strings.TrimSpace(options.RepoRoot) == "" {
		options.RepoRoot = "."
	}
	absRoot, err := filepath.Abs(options.RepoRoot)
	if err == nil {
		options.RepoRoot = absRoot
	}
	if strings.TrimSpace(options.EnvPath) == "" {
		options.EnvPath = filepath.Join(options.RepoRoot, ".env")
	} else {
		options.EnvPath = resolvePath(options.RepoRoot, options.EnvPath)
	}
	if strings.TrimSpace(options.APIURL) == "" {
		options.APIURL = firstEnv("FOXGLOVE_API_URL", "FOXGLOVE_API_BASE_URL")
	}
	if strings.TrimSpace(options.APIURL) == "" {
		options.APIURL = defaultAPIURL
	}
	if strings.TrimSpace(options.TokenEnv) == "" {
		options.TokenEnv = defaultTokenEnv
	}
	if strings.TrimSpace(options.DeviceName) == "" {
		options.DeviceName = defaultDeviceName
	}
	if strings.TrimSpace(options.KeyPrefix) == "" {
		options.KeyPrefix = defaultKeyPrefix
	}
	if options.HTTPClient == nil {
		options.HTTPClient = defaultHTTPClient()
	}
	if options.Stdout == nil {
		options.Stdout = io.Discard
	}
	if options.Stderr == nil {
		options.Stderr = io.Discard
	}
	return options
}

func firstEnv(keys ...string) string {
	for _, key := range keys {
		if value := strings.TrimSpace(os.Getenv(key)); value != "" {
			return value
		}
	}
	return ""
}

func defaultHTTPClient() *http.Client {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.ForceAttemptHTTP2 = false
	if transport.TLSClientConfig == nil {
		transport.TLSClientConfig = &tls.Config{NextProtos: []string{"http/1.1"}}
	} else {
		transport.TLSClientConfig = transport.TLSClientConfig.Clone()
		transport.TLSClientConfig.NextProtos = []string{"http/1.1"}
	}
	transport.TLSNextProto = map[string]func(string, *tls.Conn) http.RoundTripper{}
	return &http.Client{
		Timeout:   30 * time.Second,
		Transport: transport,
	}
}

func latestRunAcrossTasks(artifactRoot string) (string, error) {
	entries, err := os.ReadDir(artifactRoot)
	if err != nil {
		return "", fmt.Errorf("artifact root not found: %s", artifactRoot)
	}
	var candidates []string
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		runs, err := os.ReadDir(filepath.Join(artifactRoot, entry.Name()))
		if err != nil {
			continue
		}
		for _, run := range runs {
			if run.IsDir() {
				candidates = append(candidates, filepath.Join(artifactRoot, entry.Name(), run.Name()))
			}
		}
	}
	if len(candidates) == 0 {
		return "", fmt.Errorf("no run directories under: %s", artifactRoot)
	}
	sort.Strings(candidates)
	return candidates[len(candidates)-1], nil
}

func latestRunDir(root string) (string, error) {
	entries, err := os.ReadDir(root)
	if err != nil {
		return "", fmt.Errorf("artifact task root not found: %s", root)
	}
	var candidates []string
	for _, entry := range entries {
		if entry.IsDir() {
			candidates = append(candidates, filepath.Join(root, entry.Name()))
		}
	}
	if len(candidates) == 0 {
		return "", fmt.Errorf("no run directories under: %s", root)
	}
	sort.Strings(candidates)
	return candidates[len(candidates)-1], nil
}

func findRunMatches(artifactRoot string, run string) ([]string, error) {
	entries, err := os.ReadDir(artifactRoot)
	if err != nil {
		return nil, fmt.Errorf("artifact root not found: %s", artifactRoot)
	}
	var matches []string
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		path := filepath.Join(artifactRoot, entry.Name(), run)
		if _, ok := existingDir(path); ok {
			matches = append(matches, path)
		}
	}
	sort.Strings(matches)
	return matches, nil
}

func newTarget(kind string, path string, filename string, key string) UploadTarget {
	var size int64
	if info, err := os.Stat(path); err == nil {
		size = info.Size()
	}
	return UploadTarget{Kind: kind, Path: path, Filename: filename, Key: filepath.ToSlash(key), Bytes: size}
}

func newMCAPTarget(path string, taskKind string, runID string, lite bool, baseKey string, sourceName string) UploadTarget {
	filename := fmt.Sprintf("navlab_%s_%s.mcap", taskKind, runID)
	key := baseKey + "/" + sourceName
	if lite {
		if digest, err := shortFileSHA256(path, 12); err == nil && digest != "" {
			filename = fmt.Sprintf("navlab_%s_%s_lite_%s.mcap", taskKind, runID, digest)
			key = baseKey + "/" + strings.TrimSuffix(sourceName, filepath.Ext(sourceName)) + "_" + digest + filepath.Ext(sourceName)
		}
	}
	return newTarget("mcap", path, filename, key)
}

func shortFileSHA256(path string, length int) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer func() { _ = file.Close() }()
	digest := sha256.New()
	if _, err := io.Copy(digest, file); err != nil {
		return "", err
	}
	value := hex.EncodeToString(digest.Sum(nil))
	if length <= 0 || length >= len(value) {
		return value, nil
	}
	return value[:length], nil
}

func printTargets(writer io.Writer, title string, result Result) {
	_, _ = fmt.Fprintln(writer, ui.Title(title))
	_, _ = fmt.Fprintf(writer, "  %s\n", ui.KeyValue("run_id", result.RunID))
	_, _ = fmt.Fprintf(writer, "  %s\n", ui.KeyValue("task_id", result.TaskID))
	_, _ = fmt.Fprintf(writer, "  %s\n", ui.KeyValue("run_dir", result.RunDir))
	_, _ = fmt.Fprintf(writer, "  %s\n", ui.KeyValue("mode", uploadMode(result.Lite)))
	_, _ = fmt.Fprintf(writer, "\n%s\n", ui.Subtitle("Files"))
	for _, target := range result.Files {
		_, _ = fmt.Fprintf(writer, "  - %s  %s  %s\n", target.Kind, target.Filename, formatUploadBytes(target.Bytes))
		_, _ = fmt.Fprintf(writer, "    %s\n", ui.KeyValue("key", target.Key))
		_, _ = fmt.Fprintf(writer, "    %s\n", ui.KeyValue("path", target.Path))
	}
}

func uploadMode(lite bool) string {
	if lite {
		return "lite"
	}
	return "raw"
}

func formatUploadBytes(bytes int64) string {
	const unit = 1024.0
	if bytes < 0 {
		return "unknown"
	}
	if bytes < 1024 {
		return fmt.Sprintf("%d B", bytes)
	}
	value := float64(bytes)
	for _, suffix := range []string{"KiB", "MiB", "GiB"} {
		value /= unit
		if value < unit {
			return fmt.Sprintf("%.1f %s", value, suffix)
		}
	}
	return fmt.Sprintf("%.1f TiB", value/unit)
}

func loadDotenv(path string) error {
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	for _, rawLine := range strings.Split(string(data), "\n") {
		line := strings.TrimSpace(rawLine)
		if line == "" || strings.HasPrefix(line, "#") || !strings.Contains(line, "=") {
			continue
		}
		key, value, _ := strings.Cut(line, "=")
		key = strings.TrimSpace(key)
		value = strings.Trim(strings.TrimSpace(value), `"'`)
		if key != "" {
			if err := os.Setenv(key, value); err != nil {
				return err
			}
		}
	}
	return nil
}

func firstString(values map[string]any, keys ...string) string {
	for _, key := range keys {
		if value, ok := values[key]; ok && value != nil {
			return fmt.Sprint(value)
		}
	}
	return ""
}

func writeJSON(path string, value any) error {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, append(data, '\n'), 0o644)
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}

func existingDir(path string) (string, bool) {
	info, err := os.Stat(path)
	if err == nil && info.IsDir() {
		abs, absErr := filepath.Abs(path)
		if absErr == nil {
			return abs, true
		}
		return path, true
	}
	return "", false
}

func pathInsideRoot(path string, root string) bool {
	relativePath, err := filepath.Rel(root, path)
	if err != nil {
		return false
	}
	return relativePath == "." || (!strings.HasPrefix(relativePath, "..") && !filepath.IsAbs(relativePath))
}

func resolvePath(repoRoot string, path string) string {
	if strings.TrimSpace(path) == "" {
		return repoRoot
	}
	if filepath.IsAbs(path) {
		return filepath.Clean(path)
	}
	return filepath.Clean(filepath.Join(repoRoot, path))
}

func sanitizeTask(value string) string {
	value = strings.TrimSpace(strings.ToLower(value))
	value = strings.ReplaceAll(value, "_", "-")
	return value
}
