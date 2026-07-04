package foxglove

import (
	"bytes"
	"encoding/binary"
	"errors"
	"io"
	"math"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/foxglove/mcap/go/mcap"
	"github.com/klauspost/compress/zstd"
)

func TestBuildReplayRejectsRawMissingOfficialMazeOverlay(t *testing.T) {
	runDir := makeRun(t, "hover", "20260615T010000Z")
	mustWriteJSON(t, filepath.Join(runDir, "summary.json"), validTaskSummary("hover"))
	writeTestMCAP(t, filepath.Join(runDir, rawMCAPRelative("hover")), []string{"/tf", "/tf_static", "/map", "/scan", "/slam/odom"})
	mustWriteLiteProfile(t, runDir, "hover", `
overlay /navlab/official_maze/map
required /tf interval=all
required /tf_static interval=all
required /map interval=all
required /scan interval=all
required /slam/odom interval=all
`)

	_, err := BuildReplay(ReplayOptions{
		RepoRoot:     repoRootFromRunDir(runDir),
		ArtifactRoot: "artifacts/sim",
		Task:         "hover",
		Run:          filepath.Base(runDir),
	})
	if err == nil || !strings.Contains(err.Error(), "/navlab/official_maze/map") {
		t.Fatalf("err = %v", err)
	}
}

func TestBuildReplayCopiesProfileTopicsWithMCAPLibrary(t *testing.T) {
	runDir := makeRun(t, "hover", "20260615T020000Z")
	mustWriteJSON(t, filepath.Join(runDir, "summary.json"), validTaskSummary("hover"))
	writeTestMCAP(t, filepath.Join(runDir, rawMCAPRelative("hover")), []string{
		"/navlab/official_maze/map",
		"/tf",
		"/tf_static",
		"/map",
		"/scan",
		"/slam/odom",
		"/clock",
	})
	mustWriteLiteProfile(t, runDir, "hover", `
overlay /navlab/official_maze/map
required /tf interval=all
required /tf_static interval=all
required /map interval=all
required /scan interval=all
required /slam/odom interval=all
drop /clock
`)

	result, err := BuildReplay(ReplayOptions{
		RepoRoot:     repoRootFromRunDir(runDir),
		ArtifactRoot: "artifacts/sim",
		Task:         "hover",
		Run:          filepath.Base(runDir),
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.ReplayMCAPInfo.MessageCounts["/navlab/official_maze/map"] != 1 {
		t.Fatalf("message counts = %#v", result.ReplayMCAPInfo.MessageCounts)
	}
	if result.TaskSummary.Path == "" || !result.TaskSummary.OK {
		t.Fatalf("task summary gate = %#v", result.TaskSummary)
	}
	if result.ReplayMCAPInfo.MessageCounts["/clock"] != 0 {
		t.Fatalf("drop topic leaked into lite: %#v", result.ReplayMCAPInfo.MessageCounts)
	}
	targets, err := BuildTargets(runDir, "hover", true, "navlab/sim")
	if err != nil {
		t.Fatal(err)
	}
	if len(targets) == 0 || !strings.Contains(targets[0].Filename, "_lite_") {
		t.Fatalf("targets = %#v", targets)
	}
}

func TestBuildReplayReadsCompressedRawMCAPWithoutPlainCopy(t *testing.T) {
	runDir := makeRun(t, "hover", "20260615T030000Z")
	mustWriteJSON(t, filepath.Join(runDir, "summary.json"), validTaskSummary("hover"))
	rawPath := filepath.Join(runDir, rawMCAPRelative("hover"))
	writeTestCompressedMCAP(t, rawPath+".zstd", []string{
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

	result, err := BuildReplay(ReplayOptions{
		RepoRoot:     repoRootFromRunDir(runDir),
		ArtifactRoot: "artifacts/sim",
		Task:         "hover",
		Run:          filepath.Base(runDir),
	})
	if err != nil {
		t.Fatal(err)
	}
	if result.RawMCAP != rawPath+".zstd" {
		t.Fatalf("raw path = %q, want compressed path", result.RawMCAP)
	}
	if _, err := os.Stat(rawPath); !os.IsNotExist(err) {
		t.Fatalf("plain raw MCAP should not be created, stat err = %v", err)
	}
	if result.ReplayMCAPInfo.MessageCounts["/navlab/official_maze/map"] != 1 {
		t.Fatalf("message counts = %#v", result.ReplayMCAPInfo.MessageCounts)
	}
}

func TestBuildReplayRejectsBlockedTaskSummary(t *testing.T) {
	runDir := makeRun(t, "hover", "20260615T040000Z")
	mustWriteJSON(t, filepath.Join(runDir, "summary.json"), map[string]any{
		"task_id":      "hover",
		"ok":           false,
		"blocked":      true,
		"blockerCodes": []string{"hover_takeoff_target_altitude_not_reached"},
	})
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

	_, err := BuildReplay(ReplayOptions{
		RepoRoot:     repoRootFromRunDir(runDir),
		ArtifactRoot: "artifacts/sim",
		Task:         "hover",
		Run:          filepath.Base(runDir),
	})
	if err == nil || !strings.Contains(err.Error(), "task summary is not ok") {
		t.Fatalf("err = %v", err)
	}
}

func TestLiteProfileParsesReplayOnlyAlignedScan(t *testing.T) {
	runDir := makeRun(t, "hover", "20260615T050000Z")
	mustWriteLiteProfile(t, runDir, "hover", `
overlay /navlab/official_maze/map
required /tf interval=all
required /tf_static interval=all
required /map interval=all
required /scan interval=all
required /slam/odom interval=all
optional /scan_map_aligned interval=0.10
optional /scan_map_aligned_points interval=0.10
derive_scan /scan_map_aligned source=/scan frame=base_scan_map_aligned fixed_frame=map points_topic=/scan_map_aligned_points role=visualization_only
`)

	profile, err := readLiteTopicProfile(liteProfileFilename(t, runDir, "hover"))
	if err != nil {
		t.Fatal(err)
	}
	if len(profile.DerivedScans) != 1 {
		t.Fatalf("derived scans = %#v", profile.DerivedScans)
	}
	derived := profile.DerivedScans[0]
	if derived.Topic != "/scan_map_aligned" ||
		derived.Source != "/scan" ||
		derived.FrameID != "base_scan_map_aligned" ||
		derived.FixedFrame != "map" ||
		derived.PointsTopic != "/scan_map_aligned_points" ||
		derived.Role != "visualization_only" {
		t.Fatalf("derived scan = %#v", derived)
	}
	if stringSliceContains(profile.Required, "/scan_map_aligned") {
		t.Fatalf("aligned scan must stay replay-only optional, required=%#v", profile.Required)
	}
}

func TestLiteProfileParsesReplayOnlyDisplayTF(t *testing.T) {
	runDir := makeRun(t, "hover", "20260615T055000Z")
	mustWriteLiteProfile(t, runDir, "hover", `
overlay /navlab/official_maze/map
required /tf interval=all
required /tf_static interval=all
required /map interval=all
required /scan interval=all
required /slam/odom interval=all
optional /gazebo/model/odometry interval=0.05
derive_display_tf /tf source=/gazebo/model/odometry parent=map child=base_link mode=replace coordinate_mode=gazebo_xyz_to_ned role=visualization_only
`)

	profile, err := readLiteTopicProfile(liteProfileFilename(t, runDir, "hover"))
	if err != nil {
		t.Fatal(err)
	}
	if len(profile.DerivedTFs) != 1 {
		t.Fatalf("derived TFs = %#v", profile.DerivedTFs)
	}
	derived := profile.DerivedTFs[0]
	if derived.Topic != "/tf" ||
		derived.Source != "/gazebo/model/odometry" ||
		derived.Parent != "map" ||
		derived.Child != "base_link" ||
		derived.Mode != "replace" ||
		derived.CoordinateMode != "gazebo_xyz_to_ned" ||
		derived.Role != "visualization_only" {
		t.Fatalf("derived display TF = %#v", derived)
	}
}

func TestLiteProfileParsesMapFrameSeparation(t *testing.T) {
	runDir := makeRun(t, "hover", "20260615T056000Z")
	mustWriteLiteProfile(t, runDir, "hover", `
overlay /navlab/official_maze/map
required /tf interval=all
required /map interval=all
required /slam/odom interval=all
rewrite_frame /map frame=cartographer_map flip_y=true scan_free_space=true scan_crop=true crop_to_known=true crop_margin_m=0.25 role=visualization_only
rewrite_frame /slam/odom frame=cartographer_map role=visualization_only
derive_map_tf /tf display_source=/gazebo/model/odometry slam_source=/navlab/slam/tf parent=map child=cartographer_map display_parent=map display_child=base_link slam_parent=map slam_child=base_link coordinate_mode=gazebo_xyz_to_ned role=visualization_only
`)

	profile, err := readLiteTopicProfile(liteProfileFilename(t, runDir, "hover"))
	if err != nil {
		t.Fatal(err)
	}
	if len(profile.FrameRewrites) != 2 {
		t.Fatalf("frame rewrites = %#v", profile.FrameRewrites)
	}
	if profile.FrameRewrites[0].Topic != "/map" ||
		profile.FrameRewrites[0].FrameID != "cartographer_map" ||
		!profile.FrameRewrites[0].FlipY ||
		!profile.FrameRewrites[0].ScanFreeSpace ||
		!profile.FrameRewrites[0].ScanCrop ||
		!profile.FrameRewrites[0].CropToKnown ||
		profile.FrameRewrites[0].CropMarginM != 0.25 {
		t.Fatalf("map rewrite = %#v", profile.FrameRewrites[0])
	}
	if len(profile.DerivedMapTFs) != 1 {
		t.Fatalf("derived map TFs = %#v", profile.DerivedMapTFs)
	}
	derived := profile.DerivedMapTFs[0]
	if derived.Topic != "/tf" ||
		derived.DisplaySource != "/gazebo/model/odometry" ||
		derived.SlamSource != "/navlab/slam/tf" ||
		derived.Parent != "map" ||
		derived.Child != "cartographer_map" ||
		derived.CoordinateMode != "gazebo_xyz_to_ned" ||
		derived.Role != "visualization_only" {
		t.Fatalf("derived map TF = %#v", derived)
	}
}

func TestWriteLiteMCAPGeneratesReplayOnlyAlignedScanFrame(t *testing.T) {
	dir := t.TempDir()
	rawPath := filepath.Join(dir, "raw.mcap")
	outputPath := filepath.Join(dir, "lite.mcap")
	writeScanReplaySourceMCAP(t, rawPath)

	derived, derivedTFs, derivedMapTFs, err := writeLiteMCAP(rawPath, outputPath, liteTopicProfile{
		Required: []string{"/scan", "/tf"},
		Interval: map[string]float64{
			"/scan": 0,
			"/tf":   0,
		},
		DerivedScans: []derivedScanProfile{{
			Topic:       "/scan_map_aligned",
			Source:      "/scan",
			FrameID:     "base_scan_map_aligned",
			FixedFrame:  "map",
			PointsTopic: "/scan_map_aligned_points",
			Role:        "visualization_only",
		}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(derived) != 1 || derived[0].Topic != "/scan_map_aligned" || derived[0].Role != "visualization_only" {
		t.Fatalf("derived = %#v", derived)
	}
	if len(derivedTFs) != 0 {
		t.Fatalf("derived TFs = %#v", derivedTFs)
	}
	if len(derivedMapTFs) != 0 {
		t.Fatalf("derived map TFs = %#v", derivedMapTFs)
	}

	evidence := inspectReplayAlignedEvidence(t, outputPath)
	if evidence.scanFrame != "base_scan" {
		t.Fatalf("/scan frame = %q", evidence.scanFrame)
	}
	if evidence.alignedFrame != "base_scan_map_aligned" || evidence.alignedCount != evidence.scanCount {
		t.Fatalf("aligned evidence = %#v", evidence)
	}
	if evidence.alignedPointsFrame != "map" || evidence.alignedPointsCount != evidence.scanCount {
		t.Fatalf("aligned point cloud evidence = %#v", evidence)
	}
	if !evidence.alignedDynamicTFEdge {
		t.Fatalf("missing replay-only dynamic map -> base_scan_map_aligned edge: %#v", evidence)
	}
}

func TestWriteLiteMCAPReplacesOnlyMapBaseLinkAndKeepsVehicleChildTF(t *testing.T) {
	dir := t.TempDir()
	rawPath := filepath.Join(dir, "raw.mcap")
	outputPath := filepath.Join(dir, "lite.mcap")
	writeDisplayTFReplaySourceMCAP(t, rawPath)

	derivedScans, derivedTFs, derivedMapTFs, err := writeLiteMCAP(rawPath, outputPath, liteTopicProfile{
		Required: []string{"/tf", "/scan"},
		Optional: []string{"/gazebo/model/odometry"},
		Interval: map[string]float64{
			"/tf":                    0,
			"/scan":                  0,
			"/gazebo/model/odometry": 0,
		},
		DerivedTFs: []derivedTFProfile{{
			Topic:          "/tf",
			Source:         "/gazebo/model/odometry",
			Parent:         "map",
			Child:          "base_link",
			Mode:           "replace",
			CoordinateMode: "gazebo_xyz_to_ned",
			Role:           "visualization_only",
		}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(derivedScans) != 0 {
		t.Fatalf("derived scans = %#v", derivedScans)
	}
	if len(derivedTFs) != 1 || derivedTFs[0].Source != "/gazebo/model/odometry" {
		t.Fatalf("derived TFs = %#v", derivedTFs)
	}
	if len(derivedMapTFs) != 0 {
		t.Fatalf("derived map TFs = %#v", derivedMapTFs)
	}

	pairs := inspectTFPairsByTopic(t, outputPath)
	if !containsTFPair(pairs["/tf"], [2]string{"raw_parent", "raw_child"}) {
		t.Fatalf("vehicle child /tf should be preserved in display replay: %#v", pairs["/tf"])
	}
	if !containsTFPair(pairs["/tf"], [2]string{"map", "base_link"}) {
		t.Fatalf("missing Gazebo display map -> base_link TF: %#v", pairs["/tf"])
	}
	var mapped *decodedTransform
	for _, transform := range inspectTransformsByTopic(t, outputPath)["/tf"] {
		if transform.Parent == "map" && transform.Child == "base_link" && transform.X == 99 {
			t.Fatalf("raw map -> base_link TF was not replaced: %#v", transform)
		}
		if transform.Parent == "map" && transform.Child == "base_link" {
			current := transform
			mapped = &current
		}
	}
	if mapped == nil {
		t.Fatal("missing mapped Gazebo display map -> base_link TF")
	}
	if math.Abs(mapped.X-(-0.5)) > 1e-9 || math.Abs(mapped.Y-(-1.25)) > 1e-9 || math.Abs(mapped.Z-0.2) > 1e-9 {
		t.Fatalf("display TF did not apply Gazebo XYZ to NED projection: %#v", mapped)
	}
	if math.Abs(yawFromQuaternion(mapped.QX, mapped.QY, mapped.QZ, mapped.QW)-math.Pi/4) > 1e-9 {
		t.Fatalf("display TF yaw should preserve source body yaw so /scan is not over-rotated: %#v", mapped)
	}
}

func TestWriteLiteMCAPSeparatesCartographerMapFrame(t *testing.T) {
	dir := t.TempDir()
	rawPath := filepath.Join(dir, "raw.mcap")
	outputPath := filepath.Join(dir, "lite.mcap")
	writeMapFrameSeparationReplaySourceMCAP(t, rawPath)

	derivedScans, derivedTFs, derivedMapTFs, err := writeLiteMCAP(rawPath, outputPath, liteTopicProfile{
		Required: []string{"/tf", "/map", "/slam/odom"},
		Optional: []string{"/gazebo/model/odometry"},
		Interval: map[string]float64{
			"/tf":                    0,
			"/map":                   0,
			"/slam/odom":             0,
			"/gazebo/model/odometry": 0,
		},
		FrameRewrites: []frameRewriteProfile{
			{Topic: "/map", FrameID: "cartographer_map", FlipY: true, Role: "visualization_only"},
			{Topic: "/slam/odom", FrameID: "cartographer_map", Role: "visualization_only"},
		},
		DerivedMapTFs: []derivedMapTFProfile{{
			Topic:          "/tf",
			DisplaySource:  "/gazebo/model/odometry",
			SlamSource:     "/navlab/slam/tf",
			Parent:         "map",
			Child:          "cartographer_map",
			DisplayParent:  "map",
			DisplayChild:   "base_link",
			SlamParent:     "map",
			SlamChild:      "base_link",
			CoordinateMode: "gazebo_xyz_to_ned",
			Role:           "visualization_only",
		}},
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(derivedScans) != 0 || len(derivedTFs) != 0 || len(derivedMapTFs) != 1 {
		t.Fatalf("derived scans=%#v TFs=%#v mapTFs=%#v", derivedScans, derivedTFs, derivedMapTFs)
	}

	grids := inspectOccupancyGridsByTopic(t, outputPath)
	if len(grids["/map"]) != 1 || grids["/map"][0].FrameID != "cartographer_map" {
		t.Fatalf("/map frame rewrite failed: %#v", grids["/map"])
	}
	if math.Abs(grids["/map"][0].OriginY-0.9) > 1e-6 {
		t.Fatalf("/map flip_y origin_y = %.6f, want 0.9", grids["/map"][0].OriginY)
	}
	if got := inspectTopicHeaderFrame(t, outputPath, "/slam/odom"); got != "cartographer_map" {
		t.Fatalf("/slam/odom frame = %q, want cartographer_map", got)
	}
	var mapped *decodedTransform
	for _, transform := range inspectTransformsByTopic(t, outputPath)["/tf"] {
		if transform.Parent == "map" && transform.Child == "cartographer_map" {
			current := transform
			mapped = &current
		}
	}
	if mapped == nil {
		t.Fatal("missing derived map -> cartographer_map TF")
	}
	if math.Abs(mapped.X-(-2.0)) > 1e-9 || math.Abs(mapped.Y-0.0) > 1e-9 {
		t.Fatalf("derived map frame translation = %#v, want x=-2 y=0", mapped)
	}
	if math.Abs(yawFromQuaternion(mapped.QX, mapped.QY, mapped.QZ, mapped.QW)) > 1e-9 {
		t.Fatalf("derived map frame yaw = %#v, want 0", mapped)
	}
}

func TestRewriteOccupancyGridCropsKnownCanvas(t *testing.T) {
	cells := bytes.Repeat([]byte{0xff}, 8*6)
	cells[1*8+2] = 100
	cells[2*8+3] = 0
	cells[3*8+4] = 100
	grid := testOccupancyGridCellsCDR("map", 8, 6, 0.10, -1.2, -1.2, cells)

	rewritten, err := rewriteOccupancyGridFrameAndData(grid, frameRewriteProfile{
		FrameID:     "cartographer_map",
		CropToKnown: true,
		Role:        "visualization_only",
	}, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	info, err := parseOccupancyGridInfoCDR(rewritten)
	if err != nil {
		t.Fatal(err)
	}
	if info.FrameID != "cartographer_map" {
		t.Fatalf("frame = %q, want cartographer_map", info.FrameID)
	}
	if info.Width != 3 || info.Height != 3 {
		t.Fatalf("cropped size = %dx%d, want 3x3", info.Width, info.Height)
	}
	if math.Abs(info.OriginX-(-1.0)) > 1e-6 || math.Abs(info.OriginY-(-1.1)) > 1e-6 {
		t.Fatalf("cropped origin = %.3f %.3f, want -1.000 -1.100", info.OriginX, info.OriginY)
	}
	if info.Occupied != 2 {
		t.Fatalf("occupied = %d, want 2", info.Occupied)
	}
}

func TestWriteLiteMCAPDropsOfficialMazeMapAlias(t *testing.T) {
	dir := t.TempDir()
	rawPath := filepath.Join(dir, "raw.mcap")
	outputPath := filepath.Join(dir, "lite.mcap")
	writeMapAliasReplaySourceMCAP(t, rawPath)

	derivedScans, derivedTFs, derivedMapTFs, err := writeLiteMCAP(rawPath, outputPath, liteTopicProfile{
		Overlay:  []string{"/navlab/official_maze/map"},
		Required: []string{"/map"},
		Interval: map[string]float64{
			"/navlab/official_maze/map": 0,
			"/map":                      0,
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	if len(derivedScans) != 0 || len(derivedTFs) != 0 || len(derivedMapTFs) != 0 {
		t.Fatalf("derived scans=%#v derived TFs=%#v derived map TFs=%#v", derivedScans, derivedTFs, derivedMapTFs)
	}

	grids := inspectOccupancyGridsByTopic(t, outputPath)
	if len(grids["/navlab/official_maze/map"]) != 1 {
		t.Fatalf("official overlay count = %d, want 1", len(grids["/navlab/official_maze/map"]))
	}
	mapGrids := grids["/map"]
	if len(mapGrids) != 1 {
		t.Fatalf("/map should keep only Cartographer grid, got %#v", mapGrids)
	}
	if mapGrids[0].Resolution != 0.05 || mapGrids[0].Width != 80 || mapGrids[0].Height != 60 {
		t.Fatalf("/map retained wrong grid: %#v", mapGrids[0])
	}
}

func writeTestMCAP(t *testing.T, path string, topics []string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	writer, err := mcap.NewWriter(file, &mcap.WriterOptions{Chunked: true})
	if err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteHeader(&mcap.Header{Profile: "ros2", Library: "test"}); err != nil {
		t.Fatal(err)
	}
	schema := &mcap.Schema{ID: 1, Name: "std_msgs/msg/String", Encoding: "ros2msg", Data: []byte("string data\n")}
	if err := writer.WriteSchema(schema); err != nil {
		t.Fatal(err)
	}
	for index, topic := range topics {
		channelID := uint16(index + 1)
		if err := writer.WriteChannel(&mcap.Channel{
			ID:              channelID,
			SchemaID:        schema.ID,
			Topic:           topic,
			MessageEncoding: "cdr",
		}); err != nil {
			t.Fatal(err)
		}
		if err := writer.WriteMessage(&mcap.Message{
			ChannelID:   channelID,
			LogTime:     uint64(index+1) * 1_000_000,
			PublishTime: uint64(index+1) * 1_000_000,
			Data:        []byte{0, 1, byte(index)},
		}); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
}

func writeScanReplaySourceMCAP(t *testing.T, path string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	writer, err := mcap.NewWriter(file, &mcap.WriterOptions{Chunked: true})
	if err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteHeader(&mcap.Header{Profile: "ros2", Library: "test"}); err != nil {
		t.Fatal(err)
	}
	scanSchema := laserScanSchema(1)
	if err := writer.WriteSchema(scanSchema); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 1, SchemaID: scanSchema.ID, Topic: "/scan", MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteMessage(&mcap.Message{
		ChannelID:   1,
		LogTime:     1_000_000,
		PublishTime: 1_000_000,
		Data:        testLaserScanCDR("base_scan"),
	}); err != nil {
		t.Fatal(err)
	}
	tfSchema := tfMessageSchema(2)
	if err := writer.WriteSchema(tfSchema); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 2, SchemaID: tfSchema.ID, Topic: "/tf", MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteMessage(&mcap.Message{
		ChannelID:   2,
		LogTime:     2_000_000,
		PublishTime: 2_000_000,
		Data:        encodeTransformTFMessage("map", "base_link", 0, 0, 0, 0),
	}); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
}

func writeDisplayTFReplaySourceMCAP(t *testing.T, path string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	writer, err := mcap.NewWriter(file, &mcap.WriterOptions{Chunked: true})
	if err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteHeader(&mcap.Header{Profile: "ros2", Library: "test"}); err != nil {
		t.Fatal(err)
	}
	scanSchema := laserScanSchema(1)
	if err := writer.WriteSchema(scanSchema); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 1, SchemaID: scanSchema.ID, Topic: "/scan", MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteMessage(&mcap.Message{ChannelID: 1, LogTime: 1_000_000, PublishTime: 1_000_000, Data: testLaserScanCDR("base_scan")}); err != nil {
		t.Fatal(err)
	}
	tfSchema := tfMessageSchema(2)
	if err := writer.WriteSchema(tfSchema); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 2, SchemaID: tfSchema.ID, Topic: "/tf", MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteMessage(&mcap.Message{ChannelID: 2, LogTime: 2_000_000, PublishTime: 2_000_000, Data: encodeTransformTFMessage("raw_parent", "raw_child", 0, 0, 0, 0)}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteMessage(&mcap.Message{ChannelID: 2, LogTime: 2_500_000, PublishTime: 2_500_000, Data: encodeTransformTFMessage("map", "base_link", 99, 0, 0, 0)}); err != nil {
		t.Fatal(err)
	}
	odomSchema := odometrySchema(3)
	if err := writer.WriteSchema(odomSchema); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 3, SchemaID: odomSchema.ID, Topic: "/gazebo/model/odometry", MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteMessage(&mcap.Message{ChannelID: 3, LogTime: 3_000_000, PublishTime: 3_000_000, Data: testOdometryCDR("odom", "base_link", 1.25, -0.5, 0.2, math.Pi/4)}); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
}

func writeMapFrameSeparationReplaySourceMCAP(t *testing.T, path string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	writer, err := mcap.NewWriter(file, &mcap.WriterOptions{Chunked: true})
	if err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteHeader(&mcap.Header{Profile: "ros2", Library: "test"}); err != nil {
		t.Fatal(err)
	}
	tfSchema := tfMessageSchema(1)
	gridSchema := occupancyGridSchema(2)
	odomSchema := odometrySchema(3)
	for _, schema := range []*mcap.Schema{tfSchema, gridSchema, odomSchema} {
		if err := writer.WriteSchema(schema); err != nil {
			t.Fatal(err)
		}
	}
	channels := []*mcap.Channel{
		{ID: 1, SchemaID: tfSchema.ID, Topic: "/tf", MessageEncoding: "cdr"},
		{ID: 2, SchemaID: tfSchema.ID, Topic: "/navlab/slam/tf", MessageEncoding: "cdr"},
		{ID: 3, SchemaID: gridSchema.ID, Topic: "/map", MessageEncoding: "cdr"},
		{ID: 4, SchemaID: odomSchema.ID, Topic: "/slam/odom", MessageEncoding: "cdr"},
		{ID: 5, SchemaID: odomSchema.ID, Topic: "/gazebo/model/odometry", MessageEncoding: "cdr"},
	}
	for _, channel := range channels {
		if err := writer.WriteChannel(channel); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.WriteMessage(&mcap.Message{ChannelID: 1, LogTime: 1_000_000, PublishTime: 1_000_000, Data: encodeTransformTFMessage("raw_parent", "raw_child", 0, 0, 0, 0)}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteMessage(&mcap.Message{ChannelID: 2, LogTime: 2_000_000, PublishTime: 2_000_000, Data: encodeTransformTFMessage("map", "base_link", 2, 0, 0, 0)}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteMessage(&mcap.Message{ChannelID: 3, LogTime: 3_000_000, PublishTime: 3_000_000, Data: testOccupancyGridCDR("map", 8, 6, 0.05, -1.2, -1.2, 6)}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteMessage(&mcap.Message{ChannelID: 4, LogTime: 4_000_000, PublishTime: 4_000_000, Data: testOdometryCDR("map", "base_link", 2, 0, 0, 0)}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteMessage(&mcap.Message{ChannelID: 5, LogTime: 5_000_000, PublishTime: 5_000_000, Data: testOdometryCDR("odom", "base_link", 0, 0, 0, 0)}); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
}

func writeMapAliasReplaySourceMCAP(t *testing.T, path string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	writer, err := mcap.NewWriter(file, &mcap.WriterOptions{Chunked: true})
	if err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteHeader(&mcap.Header{Profile: "ros2", Library: "test"}); err != nil {
		t.Fatal(err)
	}
	gridSchema := occupancyGridSchema(1)
	if err := writer.WriteSchema(gridSchema); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 1, SchemaID: gridSchema.ID, Topic: "/navlab/official_maze/map", MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteChannel(&mcap.Channel{ID: 2, SchemaID: gridSchema.ID, Topic: "/map", MessageEncoding: "cdr"}); err != nil {
		t.Fatal(err)
	}
	official := testOccupancyGridCDR("map", 206, 206, 0.10, -10.3, -10.3, 3321)
	if err := writer.WriteMessage(&mcap.Message{ChannelID: 1, LogTime: 1_000_000, PublishTime: 1_000_000, Data: official}); err != nil {
		t.Fatal(err)
	}
	if err := writer.WriteMessage(&mcap.Message{ChannelID: 2, LogTime: 2_000_000, PublishTime: 2_000_000, Data: official}); err != nil {
		t.Fatal(err)
	}
	slam := testOccupancyGridCDR("map", 80, 60, 0.05, -1.2, -1.2, 258)
	if err := writer.WriteMessage(&mcap.Message{ChannelID: 2, LogTime: 3_000_000, PublishTime: 3_000_000, Data: slam}); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
}

func testLaserScanCDR(frameID string) []byte {
	builder := testCDRBuilder{data: []byte{0, 1, 0, 0}}
	builder.int32(0)
	builder.uint32(0)
	builder.string(frameID)
	builder.float32(-math.Pi)
	builder.float32(math.Pi)
	builder.float32((2 * math.Pi) / 63.0)
	builder.float32(0)
	builder.float32(0.1)
	builder.float32(0.05)
	builder.float32(10)
	builder.uint32(64)
	for i := 0; i < 64; i++ {
		builder.float32(1.0)
	}
	builder.uint32(0)
	return builder.data
}

func testOccupancyGridCDR(frameID string, width uint32, height uint32, resolution float64, originX float64, originY float64, occupied int) []byte {
	cellCount := int(width * height)
	cells := make([]byte, cellCount)
	for index := 0; index < cellCount; index++ {
		if index < occupied {
			cells[index] = 100
		}
	}
	return testOccupancyGridCellsCDR(frameID, width, height, resolution, originX, originY, cells)
}

func testOccupancyGridCellsCDR(frameID string, width uint32, height uint32, resolution float64, originX float64, originY float64, cells []byte) []byte {
	builder := testCDRBuilder{data: []byte{0, 1, 0, 0}}
	builder.int32(0)
	builder.uint32(0)
	builder.string(frameID)
	builder.int32(0)
	builder.uint32(0)
	builder.float32(resolution)
	builder.uint32(width)
	builder.uint32(height)
	builder.float64(originX)
	builder.float64(originY)
	builder.float64(0)
	builder.float64(0)
	builder.float64(0)
	builder.float64(0)
	builder.float64(1)
	builder.uint32(uint32(len(cells)))
	builder.data = append(builder.data, cells...)
	return builder.data
}

func testOdometryCDR(frameID string, childFrameID string, x float64, y float64, z float64, yaw float64) []byte {
	qz, qw := yawQuaternion(yaw)
	builder := testCDRBuilder{data: []byte{0, 1, 0, 0}}
	builder.int32(1)
	builder.uint32(2)
	builder.string(frameID)
	builder.string(childFrameID)
	builder.float64(x)
	builder.float64(y)
	builder.float64(z)
	builder.float64(0)
	builder.float64(0)
	builder.float64(qz)
	builder.float64(qw)
	for i := 0; i < 36; i++ {
		builder.float64(0)
	}
	for i := 0; i < 6; i++ {
		builder.float64(0)
	}
	for i := 0; i < 36; i++ {
		builder.float64(0)
	}
	return builder.data
}

func odometrySchema(id uint16) *mcap.Schema {
	return &mcap.Schema{ID: id, Name: "nav_msgs/msg/Odometry", Encoding: "ros2msg", Data: []byte("std_msgs/Header header\nstring child_frame_id\n")}
}

func occupancyGridSchema(id uint16) *mcap.Schema {
	return &mcap.Schema{ID: id, Name: "nav_msgs/msg/OccupancyGrid", Encoding: "ros2msg", Data: []byte("std_msgs/Header header\nnav_msgs/MapMetaData info\nint8[] data\n")}
}

type testCDRBuilder struct{ data []byte }

func (builder *testCDRBuilder) align(size int) {
	if size <= 1 {
		return
	}
	base := 4
	remainder := (len(builder.data) - base) % size
	if remainder < 0 {
		remainder += size
	}
	if remainder != 0 {
		for i := 0; i < size-remainder; i++ {
			builder.data = append(builder.data, 0)
		}
	}
}

func (builder *testCDRBuilder) uint32(value uint32) {
	builder.align(4)
	builder.data = binary.LittleEndian.AppendUint32(builder.data, value)
}

func (builder *testCDRBuilder) int32(value int32) {
	builder.uint32(uint32(value))
}

func (builder *testCDRBuilder) float32(value float64) {
	builder.align(4)
	builder.data = binary.LittleEndian.AppendUint32(builder.data, math.Float32bits(float32(value)))
}

func (builder *testCDRBuilder) float64(value float64) {
	builder.align(8)
	builder.data = binary.LittleEndian.AppendUint64(builder.data, math.Float64bits(value))
}

func (builder *testCDRBuilder) string(value string) {
	encoded := append([]byte(value), 0)
	builder.uint32(uint32(len(encoded)))
	builder.data = append(builder.data, encoded...)
	builder.align(4)
}

type replayAlignedEvidence struct {
	scanCount            int
	alignedCount         int
	alignedPointsCount   int
	scanFrame            string
	alignedFrame         string
	alignedPointsFrame   string
	alignedStaticMapEdge bool
	alignedDynamicTFEdge bool
}

func inspectReplayAlignedEvidence(t *testing.T, path string) replayAlignedEvidence {
	t.Helper()
	file, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	reader, err := mcap.NewReader(file)
	if err != nil {
		t.Fatal(err)
	}
	defer reader.Close()
	it, err := reader.Messages(mcap.UsingIndex(false))
	if err != nil {
		t.Fatal(err)
	}
	var evidence replayAlignedEvidence
	for {
		_, channel, message, err := it.Next(nil) //nolint:staticcheck
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		switch channel.Topic {
		case "/scan":
			evidence.scanCount++
			if evidence.scanFrame == "" {
				evidence.scanFrame = testHeaderFrameID(t, message.Data)
			}
		case "/scan_map_aligned":
			evidence.alignedCount++
			if evidence.alignedFrame == "" {
				evidence.alignedFrame = testHeaderFrameID(t, message.Data)
			}
		case "/scan_map_aligned_points":
			evidence.alignedPointsCount++
			if evidence.alignedPointsFrame == "" {
				evidence.alignedPointsFrame = testHeaderFrameID(t, message.Data)
			}
		case "/tf", "/tf_static":
			for _, pair := range testTFPairs(t, message.Data) {
				if pair[0] == "map" && pair[1] == "base_scan_map_aligned" {
					if channel.Topic == "/tf" {
						evidence.alignedDynamicTFEdge = true
					} else {
						evidence.alignedStaticMapEdge = true
					}
				}
			}
		}
	}
	return evidence
}

func inspectTFPairsByTopic(t *testing.T, path string) map[string][][2]string {
	t.Helper()
	file, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	reader, err := mcap.NewReader(file)
	if err != nil {
		t.Fatal(err)
	}
	defer reader.Close()
	it, err := reader.Messages(mcap.UsingIndex(false))
	if err != nil {
		t.Fatal(err)
	}
	pairs := map[string][][2]string{}
	for {
		_, channel, message, err := it.Next(nil) //nolint:staticcheck
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		if channel.Topic == "/tf" || channel.Topic == "/tf_static" {
			pairs[channel.Topic] = append(pairs[channel.Topic], testTFPairs(t, message.Data)...)
		}
	}
	return pairs
}

func inspectTransformsByTopic(t *testing.T, path string) map[string][]decodedTransform {
	t.Helper()
	file, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	reader, err := mcap.NewReader(file)
	if err != nil {
		t.Fatal(err)
	}
	defer reader.Close()
	it, err := reader.Messages(mcap.UsingIndex(false))
	if err != nil {
		t.Fatal(err)
	}
	transforms := map[string][]decodedTransform{}
	for {
		_, channel, message, err := it.Next(nil) //nolint:staticcheck
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		if channel.Topic == "/tf" || channel.Topic == "/tf_static" {
			decoded, err := decodeTFMessageCDR(message.Data)
			if err != nil {
				t.Fatal(err)
			}
			transforms[channel.Topic] = append(transforms[channel.Topic], decoded...)
		}
	}
	return transforms
}

func inspectOccupancyGridsByTopic(t *testing.T, path string) map[string][]occupancyGridInfo {
	t.Helper()
	file, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	reader, err := mcap.NewReader(file)
	if err != nil {
		t.Fatal(err)
	}
	defer reader.Close()
	it, err := reader.Messages(mcap.UsingIndex(false))
	if err != nil {
		t.Fatal(err)
	}
	grids := map[string][]occupancyGridInfo{}
	for {
		_, channel, message, err := it.Next(nil) //nolint:staticcheck
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		if channel.Topic != "/map" && channel.Topic != "/navlab/official_maze/map" {
			continue
		}
		grid, err := parseOccupancyGridInfoCDR(message.Data)
		if err != nil {
			t.Fatal(err)
		}
		grids[channel.Topic] = append(grids[channel.Topic], grid)
	}
	return grids
}

func inspectTopicHeaderFrame(t *testing.T, path string, topic string) string {
	t.Helper()
	file, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	reader, err := mcap.NewReader(file)
	if err != nil {
		t.Fatal(err)
	}
	defer reader.Close()
	it, err := reader.Messages(mcap.UsingIndex(false))
	if err != nil {
		t.Fatal(err)
	}
	for {
		_, channel, message, err := it.Next(nil) //nolint:staticcheck
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		if channel.Topic == topic {
			return testHeaderFrameID(t, message.Data)
		}
	}
	t.Fatalf("topic not found: %s", topic)
	return ""
}

func containsTFPair(values [][2]string, want [2]string) bool {
	for _, value := range values {
		if value == want {
			return true
		}
	}
	return false
}

func testHeaderFrameID(t *testing.T, data []byte) string {
	t.Helper()
	cursor := testCDRCursor{data: data, off: 4}
	if _, err := cursor.int32(); err != nil {
		t.Fatal(err)
	}
	if _, err := cursor.uint32(); err != nil {
		t.Fatal(err)
	}
	frame, err := cursor.string()
	if err != nil {
		t.Fatal(err)
	}
	return frame
}

func testTFPairs(t *testing.T, data []byte) [][2]string {
	t.Helper()
	cursor := testCDRCursor{data: data, off: 4}
	count, err := cursor.uint32()
	if err != nil {
		t.Fatal(err)
	}
	pairs := make([][2]string, 0, count)
	for i := uint32(0); i < count; i++ {
		if _, err := cursor.int32(); err != nil {
			t.Fatal(err)
		}
		if _, err := cursor.uint32(); err != nil {
			t.Fatal(err)
		}
		parent, err := cursor.string()
		if err != nil {
			t.Fatal(err)
		}
		child, err := cursor.string()
		if err != nil {
			t.Fatal(err)
		}
		for j := 0; j < 7; j++ {
			if err := cursor.float64(); err != nil {
				t.Fatal(err)
			}
		}
		pairs = append(pairs, [2]string{parent, child})
	}
	return pairs
}

type testCDRCursor struct {
	data []byte
	off  int
}

func (cursor *testCDRCursor) align(size int) {
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

func (cursor *testCDRCursor) uint32() (uint32, error) {
	cursor.align(4)
	if cursor.off+4 > len(cursor.data) {
		return 0, io.ErrUnexpectedEOF
	}
	value := binary.LittleEndian.Uint32(cursor.data[cursor.off : cursor.off+4])
	cursor.off += 4
	return value, nil
}

func (cursor *testCDRCursor) int32() (int32, error) {
	value, err := cursor.uint32()
	return int32(value), err
}

func (cursor *testCDRCursor) float64() error {
	cursor.align(8)
	if cursor.off+8 > len(cursor.data) {
		return io.ErrUnexpectedEOF
	}
	cursor.off += 8
	return nil
}

func (cursor *testCDRCursor) string() (string, error) {
	length, err := cursor.uint32()
	if err != nil {
		return "", err
	}
	if int(length) > len(cursor.data)-cursor.off {
		return "", io.ErrUnexpectedEOF
	}
	raw := cursor.data[cursor.off : cursor.off+int(length)]
	cursor.off += int(length)
	cursor.align(4)
	if len(raw) > 0 && raw[len(raw)-1] == 0 {
		raw = raw[:len(raw)-1]
	}
	return string(raw), nil
}

func liteProfileFilename(t *testing.T, runDir string, task string) string {
	t.Helper()
	filename := liteProfileFilenameByTask[task]
	if filename == "" {
		t.Fatalf("missing lite profile filename for task %s", task)
	}
	return filepath.Join(repoRootFromRunDir(runDir), "docker", "profiles", filename)
}

func stringSliceContains(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

func writeTestCompressedMCAP(t *testing.T, path string, topics []string) {
	t.Helper()
	var plain bytes.Buffer
	writeTestMCAPTo(t, &plain, topics)
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	file, err := os.Create(path)
	if err != nil {
		t.Fatal(err)
	}
	defer file.Close()
	encoder, err := zstd.NewWriter(file)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := encoder.Write(plain.Bytes()); err != nil {
		t.Fatal(err)
	}
	if err := encoder.Close(); err != nil {
		t.Fatal(err)
	}
}

func writeTestMCAPTo(t *testing.T, output *bytes.Buffer, topics []string) {
	t.Helper()
	writer, err := mcap.NewWriter(output, &mcap.WriterOptions{Chunked: true})
	if err != nil {
		t.Fatal(err)
	}
	writeTestMCAPContents(t, writer, topics)
}

func writeTestMCAPContents(t *testing.T, writer *mcap.Writer, topics []string) {
	t.Helper()
	if err := writer.WriteHeader(&mcap.Header{Profile: "ros2", Library: "test"}); err != nil {
		t.Fatal(err)
	}
	schema := &mcap.Schema{ID: 1, Name: "std_msgs/msg/String", Encoding: "ros2msg", Data: []byte("string data\n")}
	if err := writer.WriteSchema(schema); err != nil {
		t.Fatal(err)
	}
	for index, topic := range topics {
		channelID := uint16(index + 1)
		if err := writer.WriteChannel(&mcap.Channel{
			ID:              channelID,
			SchemaID:        schema.ID,
			Topic:           topic,
			MessageEncoding: "cdr",
		}); err != nil {
			t.Fatal(err)
		}
		if err := writer.WriteMessage(&mcap.Message{
			ChannelID:   channelID,
			LogTime:     uint64(index+1) * 1_000_000,
			PublishTime: uint64(index+1) * 1_000_000,
			Data:        []byte{0, 1, byte(index)},
		}); err != nil {
			t.Fatal(err)
		}
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
}
