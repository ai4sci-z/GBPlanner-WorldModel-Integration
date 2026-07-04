package hover

import (
	"encoding/binary"
	"math"
)

func gateTestStringCDR(value string) []byte {
	builder := gateTestCDRBuilder{data: []byte{0, 1, 0, 0}}
	builder.string(value)
	return builder.data
}

type gateTestCDRBuilder struct{ data []byte }

func (builder *gateTestCDRBuilder) align(size int) {
	if size <= 1 {
		return
	}
	remainder := (len(builder.data) - 4) % size
	if remainder != 0 {
		for range size - remainder {
			builder.data = append(builder.data, 0)
		}
	}
}

func (builder *gateTestCDRBuilder) uint32(value uint32) {
	builder.align(4)
	builder.data = binary.LittleEndian.AppendUint32(builder.data, value)
}

func (builder *gateTestCDRBuilder) int32(value int32) {
	builder.uint32(uint32(value))
}

func (builder *gateTestCDRBuilder) float64(value float64) {
	builder.align(8)
	builder.data = binary.LittleEndian.AppendUint64(builder.data, math.Float64bits(value))
}

func (builder *gateTestCDRBuilder) float32(value float64) {
	builder.align(4)
	builder.data = binary.LittleEndian.AppendUint32(builder.data, math.Float32bits(float32(value)))
}

func (builder *gateTestCDRBuilder) string(value string) {
	encoded := append([]byte(value), 0)
	builder.uint32(uint32(len(encoded)))
	builder.data = append(builder.data, encoded...)
	builder.align(4)
}

func gateTestOdometryCDR(x float64, y float64, z float64) []byte {
	builder := gateTestCDRBuilder{data: []byte{0, 1, 0, 0}}
	builder.int32(1)
	builder.uint32(2)
	builder.string("odom")
	builder.string("base_link")
	builder.float64(x)
	builder.float64(y)
	builder.float64(z)
	return builder.data
}

func gateTestLaserScanCDR(referenceRange float64, tx float64, ty float64) []byte {
	builder := gateTestCDRBuilder{data: []byte{0, 1, 0, 0}}
	builder.int32(1)
	builder.uint32(2)
	builder.string("base_scan")
	angleMin := 0.0
	angleIncrement := math.Pi / 2.0
	builder.float32(angleMin)
	builder.float32(math.Pi * 1.5)
	builder.float32(angleIncrement)
	builder.float32(0)
	builder.float32(0)
	builder.float32(0.05)
	builder.float32(10.0)
	builder.uint32(4)
	for idx := 0; idx < 4; idx++ {
		theta := angleMin + float64(idx)*angleIncrement
		rangeM := referenceRange - (math.Cos(theta)*tx + math.Sin(theta)*ty)
		builder.float32(rangeM)
	}
	builder.uint32(0)
	return builder.data
}
