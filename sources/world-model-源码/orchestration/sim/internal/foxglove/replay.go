package foxglove

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/foxglove/mcap/go/mcap"
	"github.com/klauspost/compress/zstd"
)

const (
	defaultReplayResolutionM = 0.10
	defaultMazeRelativePath  = "../ardupilot_gz/ardupilot_gz_gazebo/worlds/maze.sdf"
	defaultLiteRelativePath  = "rosbag_foxglove/rosbag_foxglove_0.mcap"
)

var rawMCAPRelativeByTask = map[string]string{
	"hover":           "rosbag/hover_rosbag/hover_rosbag_0.mcap",
	"exploration":     "rosbag/exploration_rosbag/exploration_rosbag_0.mcap",
	"navigation":      "rosbag/navigation_rosbag/navigation_rosbag_0.mcap",
	"scan-robustness": "rosbag/scan_robustness_rosbag/scan_robustness_rosbag_0.mcap",
}

type ReplayOptions struct {
	RepoRoot     string
	ArtifactRoot string
	Run          string
	Task         string
	MazePath     string
	ProfilePath  string
	ResolutionM  float64
	DryRun       bool
	Stdout       io.Writer
}

type ReplayResult struct {
	OK             bool                `json:"ok"`
	Blocked        bool                `json:"blocked"`
	Blockers       []string            `json:"blockers"`
	RunID          string              `json:"run_id"`
	TaskID         string              `json:"task_id"`
	RunDir         string              `json:"run_dir"`
	RawMCAP        string              `json:"raw_mcap"`
	ReplayMCAP     string              `json:"replay_mcap_path"`
	TaskSummary    TaskSummaryGate     `json:"task_summary"`
	ProfilePath    string              `json:"topic_profile"`
	DryRun         bool                `json:"dry_run"`
	OfficialMaze   OfficialMazeSummary `json:"official_maze"`
	Overlay        OverlaySummary      `json:"overlay"`
	Crop           CropSummary         `json:"crop"`
	ReplayMCAPInfo ReplayMCAPSummary   `json:"replay_mcap"`
	TruthBoundary  TruthBoundary       `json:"truth_boundary"`
}

type OfficialMazeSummary struct {
	Source        string             `json:"source"`
	SHA256        string             `json:"sha256"`
	WallCount     int                `json:"wall_count"`
	ExtentM       map[string]float64 `json:"extent_m"`
	ResolutionM   float64            `json:"resolution_m"`
	OccupiedCells int                `json:"occupied_cells"`
}

type OverlaySummary struct {
	Topic         string  `json:"topic"`
	FrameID       string  `json:"frame_id"`
	Role          string  `json:"role"`
	Scale         float64 `json:"scale"`
	ResolutionM   float64 `json:"resolution_m"`
	Width         int     `json:"width"`
	Height        int     `json:"height"`
	OccupiedCells int     `json:"occupied_cells"`
}

type CropSummary struct {
	Mode    string             `json:"mode"`
	MarginM float64            `json:"margin_m"`
	BBoxM   map[string]float64 `json:"bbox_m"`
}

type ReplayMCAPSummary struct {
	Path                  string                `json:"path"`
	RawMCAPPath           string                `json:"raw_mcap_path"`
	RawMCAPSizeBytes      int64                 `json:"raw_mcap_size_bytes"`
	FoxgloveMCAPSizeBytes int64                 `json:"foxglove_mcap_size_bytes"`
	SizeReductionRatio    float64               `json:"size_reduction_ratio"`
	RequiredTopics        []string              `json:"required_topics"`
	MissingTopics         []string              `json:"missing_topics"`
	PresentTopics         []string              `json:"present_topics"`
	MessageCounts         map[string]int        `json:"message_counts"`
	ConfiguredDropTopics  []string              `json:"configured_drop_topics"`
	RetainedTopics        []string              `json:"retained_topics"`
	FrameRewrites         []frameRewriteProfile `json:"frame_rewrites,omitempty"`
	DerivedTopics         []derivedScanProfile  `json:"derived_topics,omitempty"`
	DerivedDisplayTFs     []derivedTFProfile    `json:"derived_display_tfs,omitempty"`
	DerivedMapTFs         []derivedMapTFProfile `json:"derived_map_tfs,omitempty"`
	DownsampledTopics     map[string]any        `json:"downsampled_topics"`
}

type TruthBoundary struct {
	UsesOfficialMazeAsInput bool   `json:"uses_official_maze_as_input"`
	UsesGazeboTruthAsInput  bool   `json:"uses_gazebo_truth_as_input"`
	OfficialMazeLayerRole   string `json:"official_maze_layer_role"`
	GazeboTruthLayerRole    string `json:"gazebo_truth_layer_role,omitempty"`
}

type TaskSummaryGate struct {
	Path     string   `json:"path"`
	OK       bool     `json:"ok"`
	Status   string   `json:"status,omitempty"`
	Blocked  bool     `json:"blocked,omitempty"`
	Blockers []string `json:"blockers,omitempty"`
}

func (gate TaskSummaryGate) reason() string {
	if len(gate.Blockers) > 0 {
		return fmt.Sprintf("%s blockers=%s", gate.Path, strings.Join(gate.Blockers, ", "))
	}
	if gate.Status != "" {
		return fmt.Sprintf("%s status=%s", gate.Path, gate.Status)
	}
	return gate.Path
}

type replayInputScan struct {
	RawCounts     map[string]int
	PresentTopics []string
}

type occupancyGridInfo struct {
	FrameID    string
	Width      uint32
	Height     uint32
	Resolution float32
	OriginX    float64
	OriginY    float64
	DataHash   string
	Occupied   int
}

type mcapReadCloser struct {
	reader *mcap.Reader
	close  func()
}

func BuildReplay(options ReplayOptions) (ReplayResult, error) {
	options = withReplayDefaults(options)
	runDir, err := ResolveRunDir(options.RepoRoot, options.ArtifactRoot, options.Task, options.Run)
	if err != nil {
		return ReplayResult{}, err
	}
	taskID := resolveTaskID(runDir, options.Task)
	taskSummary, summaryErr := readTaskSummaryGate(runDir)
	rawPath := resolveRawMCAPPath(runDir, taskID)
	outputPath := filepath.Join(runDir, defaultLiteRelativePath)
	profilePath, err := resolveReplayProfilePath(options, runDir, taskID)
	if err != nil {
		return ReplayResult{}, err
	}
	profile, err := readLiteTopicProfile(profilePath)
	if err != nil {
		return ReplayResult{}, err
	}

	requiredTopics := uniqueStrings(append(append([]string{}, profile.Overlay...), profile.Required...))
	retainedTopics := uniqueStrings(append(append(append([]string{}, profile.Overlay...), profile.Required...), profile.Optional...))
	mazePath := resolvePath(options.RepoRoot, options.MazePath)
	result := ReplayResult{
		RunID:       filepath.Base(runDir),
		TaskID:      sanitizeTask(taskID),
		RunDir:      runDir,
		RawMCAP:     rawPath,
		ReplayMCAP:  outputPath,
		TaskSummary: taskSummary,
		ProfilePath: profilePath,
		DryRun:      options.DryRun,
		OfficialMaze: OfficialMazeSummary{
			Source:      mazePath,
			SHA256:      optionalFileSHA256(mazePath),
			ResolutionM: options.ResolutionM,
		},
		Overlay: OverlaySummary{
			Topic:       firstOverlayTopic(profile),
			FrameID:     "map",
			Role:        "visualization_only",
			Scale:       1.0,
			ResolutionM: options.ResolutionM,
		},
		Crop: CropSummary{
			Mode:    "none_live_overlay_copy",
			MarginM: 0,
			BBoxM:   map[string]float64{},
		},
		TruthBoundary: TruthBoundary{
			UsesOfficialMazeAsInput: false,
			UsesGazeboTruthAsInput:  profileUsesGazeboDisplayTF(profile),
			OfficialMazeLayerRole:   "visualization_only",
			GazeboTruthLayerRole:    gazeboTruthLayerRole(profile),
		},
		ReplayMCAPInfo: ReplayMCAPSummary{
			Path:                 outputPath,
			RawMCAPPath:          rawPath,
			RequiredTopics:       sortedStrings(requiredTopics),
			ConfiguredDropTopics: sortedStrings(profile.Drop),
			RetainedTopics:       sortedStrings(retainedTopics),
			DownsampledTopics:    profileDownsampleIntervals(profile),
		},
	}

	if summaryErr != nil {
		result.Blockers = append(result.Blockers, summaryErr.Error())
	} else if !taskSummary.OK {
		result.Blockers = append(result.Blockers, "task summary is not ok: "+taskSummary.reason())
	}
	if !fileExists(rawPath) {
		result.Blockers = append(result.Blockers, "raw MCAP missing")
	}
	if options.ResolutionM <= 0 {
		result.Blockers = append(result.Blockers, "overlay resolution must be positive")
	}
	if len(result.Blockers) == 0 {
		result, err = buildReplayUnchecked(result, profile, options)
		if err != nil {
			result.Blockers = append(result.Blockers, err.Error())
		}
	}

	result.Blocked = len(result.Blockers) > 0
	result.OK = !result.Blocked
	if err := writeJSON(filepath.Join(runDir, defaultReplaySummary), result); err != nil {
		return result, fmt.Errorf("write replay summary: %w", err)
	}
	printReplayResult(options.Stdout, result)
	if result.Blocked {
		return result, fmt.Errorf("foxglove replay blocked: %s", strings.Join(result.Blockers, ", "))
	}
	return result, nil
}

func readTaskSummaryGate(runDir string) (TaskSummaryGate, error) {
	path := filepath.Join(runDir, defaultSummaryFilename)
	gate := TaskSummaryGate{Path: path}
	data, err := os.ReadFile(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return gate, fmt.Errorf("run summary missing: %s", path)
		}
		return gate, fmt.Errorf("read run summary: %w", err)
	}
	var payload map[string]any
	if err := json.Unmarshal(data, &payload); err != nil {
		return gate, fmt.Errorf("parse run summary: %w", err)
	}
	ok, hasOK := payload["ok"].(bool)
	gate.OK = ok
	if status, _ := payload["status"].(string); status != "" {
		gate.Status = status
	}
	if blocked, ok := payload["blocked"].(bool); ok {
		gate.Blocked = blocked
	}
	gate.Blockers = summaryBlockers(payload["blockers"])
	if len(gate.Blockers) == 0 {
		gate.Blockers = summaryBlockers(payload["blockerCodes"])
	}
	if !hasOK {
		gate.Blockers = append(gate.Blockers, "missing ok field")
	}
	if gate.Blocked && len(gate.Blockers) == 0 {
		gate.Blockers = append(gate.Blockers, "summary marked blocked")
	}
	return gate, nil
}

func summaryBlockers(value any) []string {
	values, ok := value.([]any)
	if !ok {
		return nil
	}
	result := make([]string, 0, len(values))
	for _, item := range values {
		switch typed := item.(type) {
		case string:
			if typed != "" {
				result = append(result, typed)
			}
		case map[string]any:
			code, _ := typed["code"].(string)
			message, _ := typed["message"].(string)
			switch {
			case code != "" && message != "":
				result = append(result, code+": "+message)
			case code != "":
				result = append(result, code)
			case message != "":
				result = append(result, message)
			}
		}
	}
	return result
}

func buildReplayUnchecked(result ReplayResult, profile liteTopicProfile, options ReplayOptions) (ReplayResult, error) {
	scan, err := scanRawMCAP(result.RawMCAP)
	if err != nil {
		return result, err
	}
	result.ReplayMCAPInfo.RawMCAPSizeBytes = fileSize(result.RawMCAP)
	result.ReplayMCAPInfo.PresentTopics = scan.PresentTopics
	rawMissing := missingTopics(result.ReplayMCAPInfo.RequiredTopics, scan.RawCounts)
	if len(rawMissing) > 0 {
		result.ReplayMCAPInfo.MissingTopics = rawMissing
		result.Blockers = append(result.Blockers, "raw MCAP missing required Foxglove-lite topics: "+strings.Join(rawMissing, ", "))
		return result, nil
	}

	if !options.DryRun {
		if err := os.MkdirAll(filepath.Dir(result.ReplayMCAP), 0o755); err != nil {
			return result, err
		}
		derivedTopics, derivedTFs, derivedMapTFs, err := writeLiteMCAP(result.RawMCAP, result.ReplayMCAP, profile)
		if err != nil {
			return result, err
		}
		result.ReplayMCAPInfo.FrameRewrites = profile.FrameRewrites
		result.ReplayMCAPInfo.DerivedTopics = derivedTopics
		result.ReplayMCAPInfo.DerivedDisplayTFs = derivedTFs
		result.ReplayMCAPInfo.DerivedMapTFs = derivedMapTFs
	}

	var counts map[string]int
	if options.DryRun {
		counts = projectedLiteCounts(scan.RawCounts, profile)
	} else {
		counts, err = inspectMCAPCounts(result.ReplayMCAP)
		if err != nil {
			return result, err
		}
	}
	result.ReplayMCAPInfo.MessageCounts = counts
	result.ReplayMCAPInfo.PresentTopics = sortedMapKeys(counts)
	result.ReplayMCAPInfo.FoxgloveMCAPSizeBytes = fileSize(result.ReplayMCAP)
	if result.ReplayMCAPInfo.FoxgloveMCAPSizeBytes > 0 {
		result.ReplayMCAPInfo.SizeReductionRatio = float64(result.ReplayMCAPInfo.RawMCAPSizeBytes) / float64(result.ReplayMCAPInfo.FoxgloveMCAPSizeBytes)
	}
	result.ReplayMCAPInfo.MissingTopics = missingTopics(result.ReplayMCAPInfo.RequiredTopics, counts)
	if len(result.ReplayMCAPInfo.MissingTopics) > 0 && !options.DryRun {
		result.Blockers = append(result.Blockers, "Foxglove-lite MCAP missing required topics: "+strings.Join(result.ReplayMCAPInfo.MissingTopics, ", "))
	}
	if !options.DryRun {
		overlay, err := inspectOverlayOccupancyGrid(result.ReplayMCAP, result.Overlay.Topic)
		if err == nil {
			result.Overlay.Width = overlay.Width
			result.Overlay.Height = overlay.Height
			result.Overlay.ResolutionM = overlay.ResolutionM
			result.Overlay.OccupiedCells = overlay.OccupiedCells
			result.OfficialMaze.ResolutionM = overlay.ResolutionM
			result.OfficialMaze.OccupiedCells = overlay.OccupiedCells
			if overlay.Width > 0 && overlay.Height > 0 && overlay.ResolutionM > 0 {
				result.OfficialMaze.ExtentM = map[string]float64{
					"x_min": 0,
					"y_min": 0,
					"x_max": float64(overlay.Width) * overlay.ResolutionM,
					"y_max": float64(overlay.Height) * overlay.ResolutionM,
				}
			}
		}
	}
	return result, nil
}

func inspectOverlayOccupancyGrid(path string, topic string) (OverlaySummary, error) {
	file, err := os.Open(path)
	if err != nil {
		return OverlaySummary{}, err
	}
	defer func() { _ = file.Close() }()
	reader, err := mcap.NewReader(file)
	if err != nil {
		return OverlaySummary{}, err
	}
	defer reader.Close()
	it, err := reader.Messages()
	if err != nil {
		return OverlaySummary{}, err
	}
	for {
		_, channel, message, err := it.Next(nil) //nolint:staticcheck
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return OverlaySummary{}, err
		}
		if channel.Topic != topic {
			continue
		}
		grid, err := parseOccupancyGridInfoCDR(message.Data)
		if err != nil {
			return OverlaySummary{}, err
		}
		return OverlaySummary{
			Topic:         topic,
			FrameID:       grid.FrameID,
			Role:          "visualization_only",
			Scale:         1,
			ResolutionM:   float64(grid.Resolution),
			Width:         int(grid.Width),
			Height:        int(grid.Height),
			OccupiedCells: grid.Occupied,
		}, nil
	}
	return OverlaySummary{}, fmt.Errorf("overlay topic not found: %s", topic)
}

func parseOccupancyGridInfoCDR(data []byte) (occupancyGridInfo, error) {
	cursor := cdrCursor{data: data}
	if err := cursor.skip(4); err != nil {
		return occupancyGridInfo{}, err
	}
	if _, err := cursor.int32(); err != nil {
		return occupancyGridInfo{}, err
	}
	if _, err := cursor.uint32(); err != nil {
		return occupancyGridInfo{}, err
	}
	frameID, err := cursor.stringValue()
	if err != nil {
		return occupancyGridInfo{}, err
	}
	if _, err := cursor.int32(); err != nil {
		return occupancyGridInfo{}, err
	}
	if _, err := cursor.uint32(); err != nil {
		return occupancyGridInfo{}, err
	}
	resolution, err := cursor.float32()
	if err != nil {
		return occupancyGridInfo{}, err
	}
	width, err := cursor.uint32()
	if err != nil {
		return occupancyGridInfo{}, err
	}
	height, err := cursor.uint32()
	if err != nil {
		return occupancyGridInfo{}, err
	}
	originX, err := cursor.float64()
	if err != nil {
		return occupancyGridInfo{}, err
	}
	originY, err := cursor.float64()
	if err != nil {
		return occupancyGridInfo{}, err
	}
	if _, err := cursor.float64(); err != nil {
		return occupancyGridInfo{}, err
	}
	for index := 0; index < 4; index++ {
		if _, err := cursor.float64(); err != nil {
			return occupancyGridInfo{}, err
		}
	}
	dataLen, err := cursor.uint32()
	if err != nil {
		return occupancyGridInfo{}, err
	}
	if dataLen != width*height {
		return occupancyGridInfo{}, fmt.Errorf("occupancy grid data length %d does not match %dx%d", dataLen, width, height)
	}
	if int(dataLen) > cursor.remaining() {
		return occupancyGridInfo{}, io.ErrUnexpectedEOF
	}
	cells := cursor.data[cursor.off : cursor.off+int(dataLen)]
	occupied := 0
	for _, value := range cells {
		if int8(value) > 50 {
			occupied++
		}
	}
	digest := sha256.Sum256(cells)
	return occupancyGridInfo{
		FrameID:    frameID,
		Width:      width,
		Height:     height,
		Resolution: resolution,
		OriginX:    originX,
		OriginY:    originY,
		DataHash:   hex.EncodeToString(digest[:]),
		Occupied:   occupied,
	}, nil
}

func collectOverlayGridFingerprints(rawPath string, topics []string) map[string]bool {
	topicSet := map[string]bool{}
	for _, topic := range topics {
		topicSet[topic] = true
	}
	if len(topicSet) == 0 {
		return nil
	}
	source, err := openMCAP(rawPath)
	if err != nil {
		return nil
	}
	defer source.close()
	fingerprints := map[string]bool{}
	it, err := source.reader.Messages(mcap.UsingIndex(false))
	if err != nil {
		return nil
	}
	for {
		_, channel, message, err := it.Next(nil) //nolint:staticcheck
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return fingerprints
		}
		if channel == nil || !topicSet[channel.Topic] {
			continue
		}
		grid, err := parseOccupancyGridInfoCDR(message.Data)
		if err != nil {
			continue
		}
		fingerprints[occupancyGridFingerprint(grid)] = true
	}
	return fingerprints
}

func isOfficialMapAlias(topic string, data []byte, overlayGridFingerprints map[string]bool) bool {
	if topic != "/map" || len(overlayGridFingerprints) == 0 {
		return false
	}
	grid, err := parseOccupancyGridInfoCDR(data)
	if err != nil {
		return false
	}
	return overlayGridFingerprints[occupancyGridFingerprint(grid)]
}

func occupancyGridFingerprint(grid occupancyGridInfo) string {
	return fmt.Sprintf("%s|%d|%d|%.9g|%.6f|%.6f|%s",
		grid.FrameID,
		grid.Width,
		grid.Height,
		grid.Resolution,
		grid.OriginX,
		grid.OriginY,
		grid.DataHash,
	)
}

func alignCDROffset(offset int, size int) int {
	if size <= 1 {
		return offset
	}
	base := 4
	if remainder := (offset - base) % size; remainder != 0 {
		return offset + size - remainder
	}
	return offset
}

type cdrCursor struct {
	data []byte
	off  int
}

func (cursor *cdrCursor) remaining() int {
	return len(cursor.data) - cursor.off
}

func (cursor *cdrCursor) align(size int) {
	if size <= 1 {
		return
	}
	base := 4
	remainder := (cursor.off - base) % size
	if remainder < 0 {
		remainder += size
	}
	if remainder != 0 {
		cursor.off += size - remainder
	}
}

func (cursor *cdrCursor) skip(size int) error {
	if cursor.off+size > len(cursor.data) {
		return io.ErrUnexpectedEOF
	}
	cursor.off += size
	return nil
}

func (cursor *cdrCursor) uint32() (uint32, error) {
	cursor.align(4)
	if cursor.off+4 > len(cursor.data) {
		return 0, io.ErrUnexpectedEOF
	}
	value := binary.LittleEndian.Uint32(cursor.data[cursor.off : cursor.off+4])
	cursor.off += 4
	return value, nil
}

func (cursor *cdrCursor) int32() (int32, error) {
	value, err := cursor.uint32()
	return int32(value), err
}

func (cursor *cdrCursor) string() error {
	_, err := cursor.stringValue()
	return err
}

func (cursor *cdrCursor) stringValue() (string, error) {
	length, err := cursor.uint32()
	if err != nil {
		return "", err
	}
	if int(length) > cursor.remaining() {
		return "", fmt.Errorf("string length %d exceeds remaining %d", length, cursor.remaining())
	}
	raw := cursor.data[cursor.off : cursor.off+int(length)]
	cursor.off += int(length)
	cursor.align(4)
	if len(raw) > 0 && raw[len(raw)-1] == 0 {
		raw = raw[:len(raw)-1]
	}
	return string(raw), nil
}

func writeLiteMCAP(rawPath string, outputPath string, profile liteTopicProfile) ([]derivedScanProfile, []derivedTFProfile, []derivedMapTFProfile, error) {
	overlayGridFingerprints := collectOverlayGridFingerprints(rawPath, profile.Overlay)
	source, err := openMCAP(rawPath)
	if err != nil {
		return nil, nil, nil, err
	}
	defer source.close()
	dst, err := os.Create(outputPath)
	if err != nil {
		return nil, nil, nil, err
	}
	defer func() { _ = dst.Close() }()
	writer, err := mcap.NewWriter(dst, &mcap.WriterOptions{Chunked: true, Compression: mcap.CompressionLZ4})
	if err != nil {
		return nil, nil, nil, err
	}
	header := source.reader.Header()
	if header == nil {
		header = &mcap.Header{}
	}
	if err := writer.WriteHeader(&mcap.Header{Profile: header.Profile, Library: "navlab-sim foxglove-lite"}); err != nil {
		return nil, nil, nil, err
	}

	retain := retainIntervals(profile)
	derivedStates := newDerivedScanStates(profile)
	derivedTFStates := newDerivedTFStates(profile)
	derivedMapTFStates := newDerivedMapTFStates(profile)
	frameRewrites := frameRewriteMap(profile.FrameRewrites)
	replaceEdges := derivedTFReplaceEdges(derivedTFStates)
	writtenSchemas := map[uint16]bool{}
	writtenChannels := map[uint16]bool{}
	lastWritten := map[string]uint64{}
	var latestScan *laserScanCDR
	var latestSlamBase *decodedTransform
	var maxSchemaID uint16
	var maxChannelID uint16
	it, err := source.reader.Messages(mcap.UsingIndex(false))
	if err != nil {
		return nil, nil, nil, err
	}
	for {
		schema, channel, message, err := it.Next(nil) //nolint:staticcheck
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return nil, nil, nil, err
		}
		if schema != nil && schema.ID > maxSchemaID {
			maxSchemaID = schema.ID
		}
		if channel != nil && channel.ID > maxChannelID {
			maxChannelID = channel.ID
		}
		for _, state := range derivedTFStates {
			if err := state.maybeCollect(channel, message); err != nil {
				return nil, nil, nil, err
			}
		}
		for _, state := range derivedMapTFStates {
			if err := state.maybeCollect(channel, message); err != nil {
				return nil, nil, nil, err
			}
		}
		if channel.Topic == "/scan" {
			scan, err := parseLaserScanCDR(message.Data)
			if err == nil {
				latestScan = &scan
			}
		}
		if channel.Topic == "/navlab/slam/tf" {
			transforms, err := decodeTFMessageCDR(message.Data)
			if err == nil {
				for _, transform := range transforms {
					if transform.Parent == "map" && transform.Child == "base_link" {
						current := transform
						latestSlamBase = &current
					}
				}
			}
		}
		interval, ok := retain[channel.Topic]
		if !ok {
			continue
		}
		if interval > 0 {
			if previous, ok := lastWritten[channel.Topic]; ok && message.LogTime-previous < uint64(interval*1e9) {
				continue
			}
		}
		data := append([]byte(nil), message.Data...)
		if isOfficialMapAlias(channel.Topic, data, overlayGridFingerprints) {
			continue
		}
		if rewrite, ok := frameRewrites[channel.Topic]; ok {
			rewritten, err := rewriteFrameData(data, rewrite, latestScan, latestSlamBase)
			if err != nil {
				return nil, nil, nil, fmt.Errorf("rewrite frame for %s: %w", channel.Topic, err)
			}
			data = rewritten
		}
		if edges := replaceEdges[channel.Topic]; len(edges) > 0 {
			filtered, keep, err := filterTFMessageCDR(data, edges)
			if err != nil {
				return nil, nil, nil, err
			}
			if !keep {
				continue
			}
			data = filtered
		}
		if schema != nil && !writtenSchemas[schema.ID] {
			if err := writer.WriteSchema(copySchema(schema, schema.ID)); err != nil {
				return nil, nil, nil, err
			}
			writtenSchemas[schema.ID] = true
		}
		if !writtenChannels[channel.ID] {
			if err := writer.WriteChannel(copyChannel(channel, channel.ID)); err != nil {
				return nil, nil, nil, err
			}
			writtenChannels[channel.ID] = true
		}
		if err := writer.WriteMessage(&mcap.Message{
			ChannelID:   channel.ID,
			Sequence:    message.Sequence,
			LogTime:     message.LogTime,
			PublishTime: message.PublishTime,
			Data:        data,
		}); err != nil {
			return nil, nil, nil, err
		}
		for _, state := range derivedStates {
			if err := state.maybeCollect(schema, channel, message); err != nil {
				return nil, nil, nil, err
			}
		}
		lastWritten[channel.Topic] = message.LogTime
	}
	derivedTopics, nextSchemaID, nextChannelID, err := writeDerivedScanOutputs(writer, derivedStates, maxSchemaID+1, maxChannelID+1)
	if err != nil {
		return nil, nil, nil, err
	}
	derivedTFs, err := writeDerivedTFOutputs(writer, derivedTFStates, nextSchemaID, nextChannelID)
	if err != nil {
		return nil, nil, nil, err
	}
	derivedMapTFs, err := writeDerivedMapTFOutputs(writer, derivedMapTFStates, nextSchemaID+uint16(len(derivedTFStates)), nextChannelID+uint16(len(derivedTFStates)))
	if err != nil {
		return nil, nil, nil, err
	}
	return derivedTopics, derivedTFs, derivedMapTFs, writer.Close()
}

func frameRewriteMap(rewrites []frameRewriteProfile) map[string]frameRewriteProfile {
	values := map[string]frameRewriteProfile{}
	for _, rewrite := range rewrites {
		if rewrite.Topic != "" && (rewrite.FrameID != "" || rewrite.FlipX || rewrite.FlipY || rewrite.ScanFreeSpace) {
			values[rewrite.Topic] = rewrite
		}
	}
	return values
}

func rewriteFrameData(data []byte, rewrite frameRewriteProfile, scan *laserScanCDR, slamBase *decodedTransform) ([]byte, error) {
	if rewrite.FlipX || rewrite.FlipY || rewrite.ScanFreeSpace || rewrite.ScanCrop || rewrite.CropToKnown {
		return rewriteOccupancyGridFrameAndData(data, rewrite, scan, slamBase)
	}
	if rewrite.FrameID == "" {
		return data, nil
	}
	return replaceROS2HeaderFrameID(data, rewrite.FrameID)
}

func rewriteOccupancyGridFrameAndData(data []byte, rewrite frameRewriteProfile, scan *laserScanCDR, slamBase *decodedTransform) ([]byte, error) {
	out := append([]byte(nil), data...)
	var err error
	if rewrite.FrameID != "" {
		out, err = replaceROS2HeaderFrameID(out, rewrite.FrameID)
		if err != nil {
			return nil, err
		}
	}
	cursor := cdrCursor{data: out}
	if err := cursor.skip(4); err != nil {
		return nil, err
	}
	if _, err := cursor.int32(); err != nil {
		return nil, err
	}
	if _, err := cursor.uint32(); err != nil {
		return nil, err
	}
	if _, err := cursor.stringValue(); err != nil {
		return nil, err
	}
	if _, err := cursor.int32(); err != nil {
		return nil, err
	}
	if _, err := cursor.uint32(); err != nil {
		return nil, err
	}
	cursor.align(4)
	resolution, err := cursor.float32()
	if err != nil {
		return nil, err
	}
	cursor.align(4)
	widthOffset := cursor.off
	width, err := cursor.uint32()
	if err != nil {
		return nil, err
	}
	cursor.align(4)
	heightOffset := cursor.off
	height, err := cursor.uint32()
	if err != nil {
		return nil, err
	}
	cursor.align(8)
	originXOffset := cursor.off
	originX, err := cursor.float64()
	if err != nil {
		return nil, err
	}
	originYOffset := cursor.off
	originY, err := cursor.float64()
	if err != nil {
		return nil, err
	}
	if _, err := cursor.float64(); err != nil {
		return nil, err
	}
	for index := 0; index < 4; index++ {
		if _, err := cursor.float64(); err != nil {
			return nil, err
		}
	}
	cursor.align(4)
	dataLenOffset := cursor.off
	dataLen, err := cursor.uint32()
	if err != nil {
		return nil, err
	}
	dataStart := cursor.off
	if dataLen != width*height {
		return nil, fmt.Errorf("occupancy grid data length %d does not match %dx%d", dataLen, width, height)
	}
	if int(dataLen) > cursor.remaining() {
		return nil, io.ErrUnexpectedEOF
	}
	cells := cursor.data[dataStart : dataStart+int(dataLen)]
	rewritten := append([]byte(nil), cells...)
	for y := uint32(0); y < height; y++ {
		for x := uint32(0); x < width; x++ {
			sourceX, sourceY := x, y
			if rewrite.FlipX {
				sourceX = width - 1 - sourceX
			}
			if rewrite.FlipY {
				sourceY = height - 1 - sourceY
			}
			rewritten[y*width+x] = cells[sourceY*width+sourceX]
		}
	}
	copy(cells, rewritten)
	if rewrite.FlipX {
		originX = -originX - float64(width)*float64(resolution)
		binary.LittleEndian.PutUint64(out[originXOffset:originXOffset+8], math.Float64bits(originX))
	}
	if rewrite.FlipY {
		originY = -originY - float64(height)*float64(resolution)
		binary.LittleEndian.PutUint64(out[originYOffset:originYOffset+8], math.Float64bits(originY))
	}
	if rewrite.ScanFreeSpace && scan != nil && slamBase != nil {
		applyScanFreeSpaceToGrid(cells, width, height, float64(resolution), originX, originY, *scan, *slamBase)
	}
	if rewrite.ScanCrop && scan != nil && slamBase != nil {
		applyScanCropToGrid(cells, width, height, float64(resolution), originX, originY, *scan, *slamBase, rewrite.CropMarginM)
	}
	if rewrite.CropToKnown {
		cropped, croppedWidth, croppedHeight, croppedOriginX, croppedOriginY, changed := cropGridToKnown(cells, width, height, float64(resolution), originX, originY, rewrite.CropMarginM)
		if changed {
			binary.LittleEndian.PutUint32(out[widthOffset:widthOffset+4], croppedWidth)
			binary.LittleEndian.PutUint32(out[heightOffset:heightOffset+4], croppedHeight)
			binary.LittleEndian.PutUint64(out[originXOffset:originXOffset+8], math.Float64bits(croppedOriginX))
			binary.LittleEndian.PutUint64(out[originYOffset:originYOffset+8], math.Float64bits(croppedOriginY))
			binary.LittleEndian.PutUint32(out[dataLenOffset:dataLenOffset+4], uint32(len(cropped)))
			next := append([]byte(nil), out[:dataStart]...)
			next = append(next, cropped...)
			out = next
		}
	}
	return out, nil
}

func applyScanFreeSpaceToGrid(cells []byte, width uint32, height uint32, resolution float64, originX float64, originY float64, scan laserScanCDR, slamBase decodedTransform) {
	for index, value := range cells {
		if int8(value) >= 0 && int8(value) <= 50 {
			cells[index] = 0xff
		}
	}
	if width == 0 || height == 0 || resolution <= 0 {
		return
	}
	yaw := yawFromQuaternion(slamBase.QX, slamBase.QY, slamBase.QZ, slamBase.QW)
	c, s := math.Cos(yaw), math.Sin(yaw)
	originGX, originGY, ok := gridCellForPoint(slamBase.X, slamBase.Y, originX, originY, resolution, width, height)
	if !ok {
		return
	}
	rangeMin := math.Max(float64(scan.RangeMin), 0.05)
	rangeMax := float64(scan.RangeMax) - 0.05
	for index, raw := range scan.Ranges {
		distance := float64(raw)
		if math.IsNaN(distance) || math.IsInf(distance, 0) || distance < rangeMin || distance >= rangeMax {
			continue
		}
		angle := float64(scan.AngleMin) + float64(index)*float64(scan.AngleIncrement)
		localX := distance * math.Cos(angle)
		localY := distance * math.Sin(angle)
		hitX := slamBase.X + c*localX - s*localY
		hitY := slamBase.Y + s*localX + c*localY
		hitGX, hitGY, ok := gridCellForPoint(hitX, hitY, originX, originY, resolution, width, height)
		if !ok {
			continue
		}
		markFreeRay(cells, width, height, originGX, originGY, hitGX, hitGY)
	}
}

func applyScanCropToGrid(cells []byte, width uint32, height uint32, resolution float64, originX float64, originY float64, scan laserScanCDR, slamBase decodedTransform, marginM float64) {
	if width == 0 || height == 0 || resolution <= 0 {
		return
	}
	yaw := yawFromQuaternion(slamBase.QX, slamBase.QY, slamBase.QZ, slamBase.QW)
	c, s := math.Cos(yaw), math.Sin(yaw)
	minX, maxX := slamBase.X, slamBase.X
	minY, maxY := slamBase.Y, slamBase.Y
	found := false
	rangeMin := math.Max(float64(scan.RangeMin), 0.05)
	rangeMax := float64(scan.RangeMax) - 0.05
	for index, raw := range scan.Ranges {
		distance := float64(raw)
		if math.IsNaN(distance) || math.IsInf(distance, 0) || distance < rangeMin || distance >= rangeMax {
			continue
		}
		angle := float64(scan.AngleMin) + float64(index)*float64(scan.AngleIncrement)
		localX := distance * math.Cos(angle)
		localY := distance * math.Sin(angle)
		hitX := slamBase.X + c*localX - s*localY
		hitY := slamBase.Y + s*localX + c*localY
		minX = math.Min(minX, hitX)
		maxX = math.Max(maxX, hitX)
		minY = math.Min(minY, hitY)
		maxY = math.Max(maxY, hitY)
		found = true
	}
	if !found {
		return
	}
	marginCells := int(math.Ceil(math.Max(marginM, 0) / resolution))
	minGX := int(math.Floor((minX-originX)/resolution)) - marginCells
	maxGX := int(math.Floor((maxX-originX)/resolution)) + marginCells
	minGY := int(math.Floor((minY-originY)/resolution)) - marginCells
	maxGY := int(math.Floor((maxY-originY)/resolution)) + marginCells
	if minGX < 0 {
		minGX = 0
	}
	if minGY < 0 {
		minGY = 0
	}
	if maxGX >= int(width) {
		maxGX = int(width) - 1
	}
	if maxGY >= int(height) {
		maxGY = int(height) - 1
	}
	for y := 0; y < int(height); y++ {
		for x := 0; x < int(width); x++ {
			if x < minGX || x > maxGX || y < minGY || y > maxGY {
				cells[y*int(width)+x] = 0xff
			}
		}
	}
}

func cropGridToKnown(cells []byte, width uint32, height uint32, resolution float64, originX float64, originY float64, marginM float64) ([]byte, uint32, uint32, float64, float64, bool) {
	if width == 0 || height == 0 || resolution <= 0 {
		return cells, width, height, originX, originY, false
	}
	minX, minY := int(width), int(height)
	maxX, maxY := -1, -1
	for y := 0; y < int(height); y++ {
		for x := 0; x < int(width); x++ {
			if cells[y*int(width)+x] == 0xff {
				continue
			}
			if x < minX {
				minX = x
			}
			if x > maxX {
				maxX = x
			}
			if y < minY {
				minY = y
			}
			if y > maxY {
				maxY = y
			}
		}
	}
	if maxX < minX || maxY < minY {
		return cells, width, height, originX, originY, false
	}
	marginCells := int(math.Ceil(math.Max(marginM, 0) / resolution))
	minX = intMax(0, minX-marginCells)
	minY = intMax(0, minY-marginCells)
	maxX = intMin(int(width)-1, maxX+marginCells)
	maxY = intMin(int(height)-1, maxY+marginCells)
	newWidth := maxX - minX + 1
	newHeight := maxY - minY + 1
	if newWidth == int(width) && newHeight == int(height) {
		return cells, width, height, originX, originY, false
	}
	cropped := make([]byte, newWidth*newHeight)
	for y := 0; y < newHeight; y++ {
		copy(cropped[y*newWidth:(y+1)*newWidth], cells[(minY+y)*int(width)+minX:(minY+y)*int(width)+minX+newWidth])
	}
	return cropped, uint32(newWidth), uint32(newHeight), originX + float64(minX)*resolution, originY + float64(minY)*resolution, true
}

func gridCellForPoint(x float64, y float64, originX float64, originY float64, resolution float64, width uint32, height uint32) (int, int, bool) {
	gx := int(math.Floor((x - originX) / resolution))
	gy := int(math.Floor((y - originY) / resolution))
	if gx < 0 || gy < 0 || gx >= int(width) || gy >= int(height) {
		return 0, 0, false
	}
	return gx, gy, true
}

func markFreeRay(cells []byte, width uint32, height uint32, x0 int, y0 int, x1 int, y1 int) {
	dx := intAbs(x1 - x0)
	dy := -intAbs(y1 - y0)
	sx := -1
	if x0 < x1 {
		sx = 1
	}
	sy := -1
	if y0 < y1 {
		sy = 1
	}
	err := dx + dy
	x, y := x0, y0
	for {
		if x == x1 && y == y1 {
			return
		}
		if x >= 0 && y >= 0 && x < int(width) && y < int(height) {
			offset := y*int(width) + x
			if int8(cells[offset]) <= 50 {
				cells[offset] = 0
			}
		}
		e2 := 2 * err
		if e2 >= dy {
			err += dy
			x += sx
		}
		if e2 <= dx {
			err += dx
			y += sy
		}
	}
}

func intAbs(value int) int {
	if value < 0 {
		return -value
	}
	return value
}

func intMin(left int, right int) int {
	if left < right {
		return left
	}
	return right
}

func intMax(left int, right int) int {
	if left > right {
		return left
	}
	return right
}

func scanRawMCAP(path string) (replayInputScan, error) {
	source, err := openMCAP(path)
	if err != nil {
		return replayInputScan{}, err
	}
	defer source.close()
	scan := replayInputScan{RawCounts: map[string]int{}}
	it, err := source.reader.Messages(mcap.UsingIndex(false))
	if err != nil {
		return replayInputScan{}, err
	}
	for {
		_, channel, _, err := it.Next(nil) //nolint:staticcheck
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return replayInputScan{}, err
		}
		scan.RawCounts[channel.Topic]++
	}
	scan.PresentTopics = sortedMapKeys(scan.RawCounts)
	return scan, nil
}

func inspectMCAPCounts(path string) (map[string]int, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer func() { _ = file.Close() }()
	reader, err := mcap.NewReader(file)
	if err != nil {
		return nil, err
	}
	defer reader.Close()
	counts := map[string]int{}
	it, err := reader.Messages()
	if err != nil {
		return nil, err
	}
	for {
		_, channel, _, err := it.Next(nil) //nolint:staticcheck
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return nil, err
		}
		counts[channel.Topic]++
	}
	return counts, nil
}

func projectedLiteCounts(rawCounts map[string]int, profile liteTopicProfile) map[string]int {
	counts := map[string]int{}
	for _, topic := range append(append(append([]string{}, profile.Overlay...), profile.Required...), profile.Optional...) {
		if rawCounts[topic] > 0 {
			counts[topic] = rawCounts[topic]
		}
	}
	return counts
}

func withReplayDefaults(options ReplayOptions) ReplayOptions {
	if strings.TrimSpace(options.RepoRoot) == "" {
		options.RepoRoot = "."
	}
	if absRoot, err := filepath.Abs(options.RepoRoot); err == nil {
		options.RepoRoot = absRoot
	}
	if strings.TrimSpace(options.ArtifactRoot) == "" {
		options.ArtifactRoot = filepath.Join(options.RepoRoot, "artifacts", "sim")
	}
	if strings.TrimSpace(options.MazePath) == "" {
		options.MazePath = filepath.Join(options.RepoRoot, defaultMazeRelativePath)
	}
	if options.ResolutionM == 0 {
		options.ResolutionM = defaultReplayResolutionM
	}
	if options.Stdout == nil {
		options.Stdout = io.Discard
	}
	return options
}

func resolveReplayProfilePath(options ReplayOptions, runDir string, taskID string) (string, error) {
	if strings.TrimSpace(options.ProfilePath) != "" {
		return resolvePath(options.RepoRoot, options.ProfilePath), nil
	}
	if path, ok := liteProfilePath(runDir, taskID); ok {
		return path, nil
	}
	filename := liteProfileFilenameByTask[sanitizeTask(taskID)]
	if filename == "" {
		return "", fmt.Errorf("no Foxglove-lite profile configured for task %q", taskID)
	}
	return filepath.Join(options.RepoRoot, "docker", "profiles", filename), nil
}

func rawMCAPRelative(taskID string) string {
	if path := rawMCAPRelativeByTask[sanitizeTask(taskID)]; path != "" {
		return path
	}
	return "rosbag/rosbag_0.mcap"
}

func resolveRawMCAPPath(runDir string, taskID string) string {
	path := filepath.Join(runDir, rawMCAPRelative(taskID))
	if fileExists(path) {
		return path
	}
	compressed := path + ".zstd"
	if fileExists(compressed) {
		return compressed
	}
	return path
}

func openMCAP(path string) (mcapReadCloser, error) {
	file, err := os.Open(path)
	if err != nil {
		return mcapReadCloser{}, err
	}
	var stream io.Reader = file
	var decoder *zstd.Decoder
	if strings.HasSuffix(path, ".zstd") {
		decoder, err = zstd.NewReader(file)
		if err != nil {
			_ = file.Close()
			return mcapReadCloser{}, err
		}
		stream = decoder
	}
	reader, err := mcap.NewReader(stream)
	if err != nil {
		if decoder != nil {
			decoder.Close()
		}
		_ = file.Close()
		return mcapReadCloser{}, err
	}
	return mcapReadCloser{
		reader: reader,
		close: func() {
			reader.Close()
			if decoder != nil {
				decoder.Close()
			}
			_ = file.Close()
		},
	}, nil
}

func retainIntervals(profile liteTopicProfile) map[string]float64 {
	retain := map[string]float64{}
	for _, topic := range append(append(append([]string{}, profile.Overlay...), profile.Required...), profile.Optional...) {
		retain[topic] = profile.Interval[topic]
	}
	return retain
}

func firstOverlayTopic(profile liteTopicProfile) string {
	if len(profile.Overlay) > 0 {
		return profile.Overlay[0]
	}
	return "/navlab/official_maze/map"
}

func profileDownsampleIntervals(profile liteTopicProfile) map[string]any {
	values := map[string]any{}
	for _, topic := range append(append(append([]string{}, profile.Overlay...), profile.Required...), profile.Optional...) {
		if interval := profile.Interval[topic]; interval > 0 {
			values[topic] = interval
		} else {
			values[topic] = "all"
		}
	}
	return values
}

func profileUsesGazeboDisplayTF(profile liteTopicProfile) bool {
	for _, spec := range profile.DerivedTFs {
		if strings.Contains(spec.Source, "gazebo") {
			return true
		}
	}
	return false
}

func gazeboTruthLayerRole(profile liteTopicProfile) string {
	if profileUsesGazeboDisplayTF(profile) {
		return "visualization_only_replay_display_tf"
	}
	return ""
}

func missingTopics(required []string, counts map[string]int) []string {
	var missing []string
	for _, topic := range required {
		if counts[topic] <= 0 {
			missing = append(missing, topic)
		}
	}
	return missing
}

func copySchema(schema *mcap.Schema, id uint16) *mcap.Schema {
	if schema == nil {
		return nil
	}
	data := append([]byte(nil), schema.Data...)
	return &mcap.Schema{ID: id, Name: schema.Name, Encoding: schema.Encoding, Data: data}
}

func copyChannel(channel *mcap.Channel, id uint16) *mcap.Channel {
	if channel == nil {
		return nil
	}
	metadata := map[string]string{}
	for key, value := range channel.Metadata {
		metadata[key] = value
	}
	return &mcap.Channel{ID: id, SchemaID: channel.SchemaID, Topic: channel.Topic, MessageEncoding: channel.MessageEncoding, Metadata: metadata}
}

func sortedStrings(values []string) []string {
	result := append([]string(nil), values...)
	sort.Strings(result)
	return result
}

func sortedMapKeys(values map[string]int) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

func fileSize(path string) int64 {
	info, err := os.Stat(path)
	if err != nil || info.IsDir() {
		return 0
	}
	return info.Size()
}

func optionalFileSHA256(path string) string {
	digest, _ := fileSHA256(path)
	return digest
}

func fileSHA256(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer func() { _ = file.Close() }()
	digest := sha256.New()
	if _, err := io.Copy(digest, file); err != nil {
		return "", err
	}
	return hex.EncodeToString(digest.Sum(nil)), nil
}

func printReplayResult(writer io.Writer, result ReplayResult) {
	_, _ = fmt.Fprintln(writer, "Foxglove Replay")
	_, _ = fmt.Fprintf(writer, "ok=%t\n", result.OK)
	_, _ = fmt.Fprintf(writer, "run_id=%s\n", result.RunID)
	_, _ = fmt.Fprintf(writer, "task_id=%s\n", result.TaskID)
	_, _ = fmt.Fprintf(writer, "raw_mcap=%s\n", result.RawMCAP)
	_, _ = fmt.Fprintf(writer, "lite_mcap=%s\n", result.ReplayMCAP)
	_, _ = fmt.Fprintf(writer, "summary=%s\n", filepath.Join(result.RunDir, defaultReplaySummary))
	if len(result.Blockers) > 0 {
		_, _ = fmt.Fprintf(writer, "blockers=%s\n", strings.Join(result.Blockers, ", "))
	}
}
