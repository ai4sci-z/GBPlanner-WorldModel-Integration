package foxglove

import (
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"math"
	"sort"

	"github.com/foxglove/mcap/go/mcap"
)

const (
	alignedScanDefaultSourceTopic = "/scan"
	alignedScanDefaultFrameID     = "base_scan_map_aligned"
	alignedScanDefaultFixedFrame  = "map"
	alignedScanDefaultPointsTopic = "/scan_map_aligned_points"
)

type derivedScanProfile struct {
	Topic       string `json:"topic"`
	Source      string `json:"source"`
	FrameID     string `json:"frame_id"`
	FixedFrame  string `json:"fixed_frame"`
	PointsTopic string `json:"points_topic,omitempty"`
	Role        string `json:"role"`
}

type derivedScanState struct {
	Spec           derivedScanProfile
	Schema         *mcap.Schema
	Messages       []derivedScanMessage
	Transform      *alignedTransform
	SourceCount    int
	GeneratedCount int
}

type derivedScanMessage struct {
	LogTime     uint64
	PublishTime uint64
	Sequence    uint32
	StampSec    int32
	StampNsec   uint32
	Transform   alignedTransform
	Data        []byte
	PointsData  []byte
}

type alignedTransform struct {
	X float64
	Y float64
}

type laserScanCDR struct {
	StampSec       int32
	StampNsec      uint32
	AngleMin       float32
	AngleIncrement float32
	RangeMin       float32
	RangeMax       float32
	Ranges         []float32
}

type replayWall struct {
	X         float64
	Y         float64
	Yaw       float64
	Length    float64
	Thickness float64
}

var officialMazeReplayWalls = []replayWall{
	{X: -10.0, Y: 0.0, Yaw: math.Pi / 2.0, Length: 20.0, Thickness: 0.2},
	{X: 0.0, Y: -10.0, Yaw: 0.0, Length: 20.0, Thickness: 0.2},
	{X: 10.0, Y: -1.5, Yaw: math.Pi / 2.0, Length: 17.0, Thickness: 0.2},
	{X: 0.0, Y: 10.0, Yaw: 0.0, Length: 20.0, Thickness: 0.2},
	{X: 1.5, Y: -7.0, Yaw: 0.0, Length: 17.0, Thickness: 0.2},
	{X: -7.0, Y: 0.0, Yaw: math.Pi / 2.0, Length: 14.0, Thickness: 0.2},
	{X: 3.0, Y: -4.0, Yaw: 0.0, Length: 14.0, Thickness: 0.2},
	{X: -4.0, Y: 0.0, Yaw: math.Pi / 2.0, Length: 8.0, Thickness: 0.2},
	{X: 4.5, Y: -1.0, Yaw: 0.0, Length: 11.0, Thickness: 0.2},
	{X: -1.0, Y: 3.0, Yaw: math.Pi / 2.0, Length: 8.0, Thickness: 0.2},
	{X: -4.0, Y: 8.5, Yaw: math.Pi / 2.0, Length: 3.0, Thickness: 0.2},
	{X: 0.0, Y: 4.0, Yaw: 0.0, Length: 2.0, Thickness: 0.2},
	{X: 6.0, Y: 7.0, Yaw: 0.0, Length: 8.0, Thickness: 0.2},
	{X: 5.0, Y: 4.5, Yaw: math.Pi / 2.0, Length: 5.0, Thickness: 0.2},
}

func normalizeDerivedScanProfile(spec derivedScanProfile) derivedScanProfile {
	if spec.Source == "" {
		spec.Source = alignedScanDefaultSourceTopic
	}
	if spec.FrameID == "" {
		spec.FrameID = alignedScanDefaultFrameID
	}
	if spec.FixedFrame == "" {
		spec.FixedFrame = alignedScanDefaultFixedFrame
	}
	if spec.PointsTopic == "" {
		spec.PointsTopic = alignedScanDefaultPointsTopic
	}
	if spec.Role == "" {
		spec.Role = "visualization_only"
	}
	return spec
}

func newDerivedScanStates(profile liteTopicProfile) []*derivedScanState {
	states := make([]*derivedScanState, 0, len(profile.DerivedScans))
	for _, spec := range profile.DerivedScans {
		states = append(states, &derivedScanState{Spec: normalizeDerivedScanProfile(spec)})
	}
	return states
}

func (state *derivedScanState) maybeCollect(schema *mcap.Schema, channel *mcap.Channel, message *mcap.Message) error {
	if state == nil || channel == nil || message == nil || channel.Topic != state.Spec.Source {
		return nil
	}
	state.SourceCount++
	if schema != nil && state.Schema == nil {
		state.Schema = schema
	}
	scan, err := parseLaserScanCDR(message.Data)
	if err != nil {
		return fmt.Errorf("parse aligned scan source %s: %w", state.Spec.Source, err)
	}
	if state.Transform == nil {
		transform, err := estimateAlignedScanTransform(scan, nil)
		if err != nil {
			return err
		}
		state.Transform = transform
	} else {
		transform, err := estimateAlignedScanTransform(scan, state.Transform)
		if err != nil {
			return err
		}
		state.Transform = transform
	}
	data, err := replaceROS2HeaderFrameID(message.Data, state.Spec.FrameID)
	if err != nil {
		return fmt.Errorf("rewrite aligned scan frame: %w", err)
	}
	pointsData := encodeAlignedPointCloud2(scan, state.Spec.FixedFrame, *state.Transform)
	state.Messages = append(state.Messages, derivedScanMessage{
		LogTime:     message.LogTime,
		PublishTime: message.PublishTime,
		Sequence:    message.Sequence,
		StampSec:    scan.StampSec,
		StampNsec:   scan.StampNsec,
		Transform:   *state.Transform,
		Data:        data,
		PointsData:  pointsData,
	})
	return nil
}

func writeDerivedScanOutputs(writer *mcap.Writer, states []*derivedScanState, nextSchemaID uint16, nextChannelID uint16) ([]derivedScanProfile, uint16, uint16, error) {
	var summaries []derivedScanProfile
	for _, state := range states {
		if state.SourceCount == 0 {
			return nil, nextSchemaID, nextChannelID, fmt.Errorf("derived scan source topic missing: %s", state.Spec.Source)
		}
		if state.Transform == nil || len(state.Messages) == 0 {
			return nil, nextSchemaID, nextChannelID, fmt.Errorf("derived scan alignment unavailable for %s", state.Spec.Topic)
		}
		schema := copySchema(state.Schema, nextSchemaID)
		if schema == nil {
			schema = laserScanSchema(nextSchemaID)
		}
		if err := writer.WriteSchema(schema); err != nil {
			return nil, nextSchemaID, nextChannelID, err
		}
		scanChannelID := nextChannelID
		if err := writer.WriteChannel(&mcap.Channel{ID: scanChannelID, SchemaID: schema.ID, Topic: state.Spec.Topic, MessageEncoding: "cdr"}); err != nil {
			return nil, nextSchemaID, nextChannelID, err
		}
		nextSchemaID++
		nextChannelID++

		pointsSchemaID := nextSchemaID
		pointsChannelID := nextChannelID
		if err := writer.WriteSchema(pointCloud2Schema(pointsSchemaID)); err != nil {
			return nil, nextSchemaID, nextChannelID, err
		}
		if err := writer.WriteChannel(&mcap.Channel{ID: pointsChannelID, SchemaID: pointsSchemaID, Topic: state.Spec.PointsTopic, MessageEncoding: "cdr"}); err != nil {
			return nil, nextSchemaID, nextChannelID, err
		}
		nextSchemaID++
		nextChannelID++

		tfSchemaID := nextSchemaID
		tfChannelID := nextChannelID
		if err := writer.WriteSchema(tfMessageSchema(tfSchemaID)); err != nil {
			return nil, nextSchemaID, nextChannelID, err
		}
		if err := writer.WriteChannel(&mcap.Channel{ID: tfChannelID, SchemaID: tfSchemaID, Topic: "/tf", MessageEncoding: "cdr"}); err != nil {
			return nil, nextSchemaID, nextChannelID, err
		}
		for _, message := range state.Messages {
			if err := writer.WriteMessage(&mcap.Message{
				ChannelID:   tfChannelID,
				LogTime:     message.LogTime,
				PublishTime: message.PublishTime,
				Data:        encodeTransformTFMessage(state.Spec.FixedFrame, state.Spec.FrameID, message.Transform.X, message.Transform.Y, message.StampSec, message.StampNsec),
			}); err != nil {
				return nil, nextSchemaID, nextChannelID, err
			}
			if err := writer.WriteMessage(&mcap.Message{ChannelID: scanChannelID, Sequence: message.Sequence, LogTime: message.LogTime, PublishTime: message.PublishTime, Data: message.Data}); err != nil {
				return nil, nextSchemaID, nextChannelID, err
			}
			if err := writer.WriteMessage(&mcap.Message{ChannelID: pointsChannelID, Sequence: message.Sequence, LogTime: message.LogTime, PublishTime: message.PublishTime, Data: message.PointsData}); err != nil {
				return nil, nextSchemaID, nextChannelID, err
			}
			state.GeneratedCount++
		}
		nextSchemaID++
		nextChannelID++
		summaries = append(summaries, state.Spec)
	}
	return summaries, nextSchemaID, nextChannelID, nil
}

func parseLaserScanCDR(data []byte) (laserScanCDR, error) {
	cursor := cdrCursor{data: data}
	if err := cursor.skip(4); err != nil {
		return laserScanCDR{}, err
	}
	stampSec, err := cursor.int32()
	if err != nil {
		return laserScanCDR{}, err
	}
	stampNsec, err := cursor.uint32()
	if err != nil {
		return laserScanCDR{}, err
	}
	if err := cursor.string(); err != nil {
		return laserScanCDR{}, err
	}
	angleMin, err := cursor.float32()
	if err != nil {
		return laserScanCDR{}, err
	}
	if _, err := cursor.float32(); err != nil { // angle_max
		return laserScanCDR{}, err
	}
	angleIncrement, err := cursor.float32()
	if err != nil {
		return laserScanCDR{}, err
	}
	if _, err := cursor.float32(); err != nil { // time_increment
		return laserScanCDR{}, err
	}
	if _, err := cursor.float32(); err != nil { // scan_time
		return laserScanCDR{}, err
	}
	rangeMin, err := cursor.float32()
	if err != nil {
		return laserScanCDR{}, err
	}
	rangeMax, err := cursor.float32()
	if err != nil {
		return laserScanCDR{}, err
	}
	ranges, err := cursor.float32Sequence()
	if err != nil {
		return laserScanCDR{}, err
	}
	return laserScanCDR{StampSec: stampSec, StampNsec: stampNsec, AngleMin: angleMin, AngleIncrement: angleIncrement, RangeMin: rangeMin, RangeMax: rangeMax, Ranges: ranges}, nil
}

func (cursor *cdrCursor) float32() (float32, error) {
	cursor.align(4)
	if cursor.off+4 > len(cursor.data) {
		return 0, ioErrUnexpectedEOF()
	}
	value := math.Float32frombits(binary.LittleEndian.Uint32(cursor.data[cursor.off : cursor.off+4]))
	cursor.off += 4
	return value, nil
}

func (cursor *cdrCursor) float32Sequence() ([]float32, error) {
	length, err := cursor.uint32()
	if err != nil {
		return nil, err
	}
	values := make([]float32, int(length))
	for index := range values {
		value, err := cursor.float32()
		if err != nil {
			return nil, err
		}
		values[index] = value
	}
	return values, nil
}

func ioErrUnexpectedEOF() error {
	return io.ErrUnexpectedEOF
}

func estimateAlignedScanTransform(scan laserScanCDR, seed *alignedTransform) (*alignedTransform, error) {
	points := scanLocalPoints(scan, 4, 140)
	if len(points) < 12 {
		return nil, errors.New("not enough valid scan points for replay alignment")
	}
	seedX, seedY := 0.0, 0.0
	passes := []scanSearchPass{{Radius: 9.0, Step: 0.5}, {Radius: 0.6, Step: 0.10}, {Radius: 0.12, Step: 0.02}}
	if seed != nil {
		seedX, seedY = seed.X, seed.Y
		passes = []scanSearchPass{{Radius: 0.8, Step: 0.10}, {Radius: 0.12, Step: 0.02}}
	}
	bestX, bestY, _, _ := scanMatch(points, seedX, seedY, passes)
	return &alignedTransform{X: bestX, Y: bestY}, nil
}

type xyPoint struct{ X, Y float64 }
type scanSearchPass struct{ Radius, Step float64 }

func scanLocalPoints(scan laserScanCDR, stride int, limit int) []xyPoint {
	if stride < 1 {
		stride = 1
	}
	points := []xyPoint{}
	rangeMin := math.Max(float64(scan.RangeMin), 0.05)
	rangeMax := float64(scan.RangeMax) - 0.05
	for index, raw := range scan.Ranges {
		if index%stride != 0 {
			continue
		}
		distance := float64(raw)
		if (math.IsNaN(distance) || math.IsInf(distance, 0)) || distance < rangeMin || distance >= rangeMax {
			continue
		}
		angle := float64(scan.AngleMin) + float64(index)*float64(scan.AngleIncrement)
		points = append(points, xyPoint{X: distance * math.Cos(angle), Y: distance * math.Sin(angle)})
		if limit > 0 && len(points) >= limit {
			break
		}
	}
	return points
}

func alignedScanPoints(scan laserScanCDR, transform alignedTransform) []xyPoint {
	points := scanLocalPoints(scan, 1, 0)
	for index := range points {
		points[index].X += transform.X
		points[index].Y += transform.Y
	}
	return points
}

func scanMatch(points []xyPoint, seedX float64, seedY float64, passes []scanSearchPass) (float64, float64, float64, float64) {
	bestX, bestY := seedX, seedY
	bestMean, bestP90 := candidateWallScore(points, bestX, bestY)
	for _, pass := range passes {
		centerX, centerY := bestX, bestY
		steps := int(math.Round((2.0 * pass.Radius) / pass.Step))
		if steps < 1 {
			steps = 1
		}
		for ix := 0; ix <= steps; ix++ {
			x := centerX - pass.Radius + float64(ix)*pass.Step
			for iy := 0; iy <= steps; iy++ {
				y := centerY - pass.Radius + float64(iy)*pass.Step
				mean, p90 := candidateWallScore(points, x, y)
				if p90 < bestP90 || (p90 == bestP90 && mean < bestMean) {
					bestX, bestY, bestMean, bestP90 = x, y, mean, p90
				}
			}
		}
	}
	return bestX, bestY, bestMean, bestP90
}

func candidateWallScore(points []xyPoint, x float64, y float64) (float64, float64) {
	if len(points) == 0 {
		return math.Inf(1), math.Inf(1)
	}
	distances := make([]float64, 0, len(points))
	sum := 0.0
	for _, point := range points {
		distance := nearestReplayWallDistance(point.X+x, point.Y+y)
		distances = append(distances, distance)
		sum += distance
	}
	sort.Float64s(distances)
	p90Index := int(math.Round(0.90 * float64(len(distances)-1)))
	return sum / float64(len(distances)), distances[p90Index]
}

func nearestReplayWallDistance(x float64, y float64) float64 {
	best := math.Inf(1)
	for _, wall := range officialMazeReplayWalls {
		if distance := pointToReplayWallDistance(x, y, wall); distance < best {
			best = distance
		}
	}
	return best
}

func pointToReplayWallDistance(x float64, y float64, wall replayWall) float64 {
	dx, dy := x-wall.X, y-wall.Y
	c, s := math.Cos(wall.Yaw), math.Sin(wall.Yaw)
	localX := c*dx + s*dy
	localY := -s*dx + c*dy
	outsideX := math.Abs(localX) - wall.Length*0.5
	outsideY := math.Abs(localY) - wall.Thickness*0.5
	if outsideX <= 0 && outsideY <= 0 {
		return 0
	}
	return math.Hypot(math.Max(outsideX, 0), math.Max(outsideY, 0))
}

func replaceROS2HeaderFrameID(data []byte, frameID string) ([]byte, error) {
	if len(data) < 16 {
		return nil, errors.New("message too short for ROS2 header")
	}
	lengthOffset := 12
	oldLength := int(binary.LittleEndian.Uint32(data[lengthOffset : lengthOffset+4]))
	if oldLength <= 0 || lengthOffset+4+oldLength > len(data) {
		return nil, errors.New("invalid header frame_id string length")
	}
	oldEnd := alignCDROffset(lengthOffset+4+oldLength, 4)
	newString := append([]byte(frameID), 0)
	newEnd := alignCDROffset(lengthOffset+4+len(newString), 4)
	out := make([]byte, 0, len(data)-oldEnd+newEnd)
	out = append(out, data[:lengthOffset]...)
	lengthBytes := make([]byte, 4)
	binary.LittleEndian.PutUint32(lengthBytes, uint32(len(newString)))
	out = append(out, lengthBytes...)
	out = append(out, newString...)
	for len(out) < newEnd {
		out = append(out, 0)
	}
	out = append(out, data[oldEnd:]...)
	return out, nil
}

func encodeTransformTFMessage(parent string, child string, x float64, y float64, stampSec int32, stampNsec uint32) []byte {
	builder := newCDRBuilder()
	builder.uint32(1) // transforms length
	builder.int32(stampSec)
	builder.uint32(stampNsec)
	builder.string(parent)
	builder.string(child)
	builder.float64(x)
	builder.float64(y)
	builder.float64(0)
	builder.float64(0)
	builder.float64(0)
	builder.float64(0)
	builder.float64(1)
	return builder.bytes()
}

func encodeAlignedPointCloud2(scan laserScanCDR, frameID string, transform alignedTransform) []byte {
	points := alignedScanPoints(scan, transform)
	builder := newCDRBuilder()
	builder.int32(scan.StampSec)
	builder.uint32(scan.StampNsec)
	builder.string(frameID)
	builder.uint32(1) // height
	builder.uint32(uint32(len(points)))
	builder.uint32(3) // fields length
	builder.string("x")
	builder.uint32(0)
	builder.uint8(7) // FLOAT32
	builder.uint32(1)
	builder.string("y")
	builder.uint32(4)
	builder.uint8(7)
	builder.uint32(1)
	builder.string("z")
	builder.uint32(8)
	builder.uint8(7)
	builder.uint32(1)
	builder.uint8(0) // is_bigendian
	builder.uint32(12)
	builder.uint32(uint32(len(points) * 12))
	builder.uint32(uint32(len(points) * 12))
	for _, point := range points {
		builder.float32(float32(point.X))
		builder.float32(float32(point.Y))
		builder.float32(0)
	}
	builder.uint8(1) // is_dense
	return builder.bytes()
}

func laserScanSchema(id uint16) *mcap.Schema {
	return &mcap.Schema{ID: id, Name: "sensor_msgs/msg/LaserScan", Encoding: "ros2msg", Data: []byte(laserScanSchemaText)}
}

func tfMessageSchema(id uint16) *mcap.Schema {
	return &mcap.Schema{ID: id, Name: "tf2_msgs/msg/TFMessage", Encoding: "ros2msg", Data: []byte(tfMessageSchemaText)}
}

func pointCloud2Schema(id uint16) *mcap.Schema {
	return &mcap.Schema{ID: id, Name: "sensor_msgs/msg/PointCloud2", Encoding: "ros2msg", Data: []byte(pointCloud2SchemaText)}
}

const laserScanSchemaText = `std_msgs/Header header
float32 angle_min
float32 angle_max
float32 angle_increment
float32 time_increment
float32 scan_time
float32 range_min
float32 range_max
float32[] ranges
float32[] intensities
================================================================================
MSG: std_msgs/Header
builtin_interfaces/Time stamp
string frame_id
================================================================================
MSG: builtin_interfaces/Time
int32 sec
uint32 nanosec
`

const tfMessageSchemaText = `geometry_msgs/TransformStamped[] transforms
================================================================================
MSG: geometry_msgs/TransformStamped
std_msgs/Header header
string child_frame_id
geometry_msgs/Transform transform
================================================================================
MSG: std_msgs/Header
builtin_interfaces/Time stamp
string frame_id
================================================================================
MSG: builtin_interfaces/Time
int32 sec
uint32 nanosec
================================================================================
MSG: geometry_msgs/Transform
geometry_msgs/Vector3 translation
geometry_msgs/Quaternion rotation
================================================================================
MSG: geometry_msgs/Vector3
float64 x
float64 y
float64 z
================================================================================
MSG: geometry_msgs/Quaternion
float64 x
float64 y
float64 z
float64 w
`

const pointCloud2SchemaText = `std_msgs/Header header
uint32 height
uint32 width
sensor_msgs/PointField[] fields
bool is_bigendian
uint32 point_step
uint32 row_step
uint8[] data
bool is_dense
================================================================================
MSG: std_msgs/Header
builtin_interfaces/Time stamp
string frame_id
================================================================================
MSG: builtin_interfaces/Time
int32 sec
uint32 nanosec
================================================================================
MSG: sensor_msgs/PointField
string name
uint32 offset
uint8 datatype
uint32 count
uint8 INT8=1
uint8 UINT8=2
uint8 INT16=3
uint8 UINT16=4
uint8 INT32=5
uint8 UINT32=6
uint8 FLOAT32=7
uint8 FLOAT64=8
`

type cdrBuilder struct{ data []byte }

func newCDRBuilder() *cdrBuilder { return &cdrBuilder{data: []byte{0, 1, 0, 0}} }

func (builder *cdrBuilder) align(size int) {
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

func (builder *cdrBuilder) uint32(value uint32) {
	builder.align(4)
	builder.data = binary.LittleEndian.AppendUint32(builder.data, value)
}

func (builder *cdrBuilder) int32(value int32) { builder.uint32(uint32(value)) }

func (builder *cdrBuilder) uint8(value uint8) {
	builder.data = append(builder.data, value)
}

func (builder *cdrBuilder) float32(value float32) {
	builder.align(4)
	builder.data = binary.LittleEndian.AppendUint32(builder.data, math.Float32bits(value))
}

func (builder *cdrBuilder) float64(value float64) {
	builder.align(8)
	builder.data = binary.LittleEndian.AppendUint64(builder.data, math.Float64bits(value))
}

func (builder *cdrBuilder) string(value string) {
	encoded := append([]byte(value), 0)
	builder.uint32(uint32(len(encoded)))
	builder.data = append(builder.data, encoded...)
	builder.align(4)
}

func (builder *cdrBuilder) bytes() []byte { return append([]byte(nil), builder.data...) }
