package helpers

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestWriteBridgeOverrideAndVendorProfile(t *testing.T) {
	dir := t.TempDir()
	bridge := filepath.Join(dir, "bridge.yaml")
	vendor := filepath.Join(dir, "vendor.yaml")
	if err := WriteBridgeOverride(bridge); err != nil {
		t.Fatalf("WriteBridgeOverride() error = %v", err)
	}
	if err := WriteVendorProfile(vendor, "/tmp/x2"); err != nil {
		t.Fatalf("WriteVendorProfile() error = %v", err)
	}
	bridgeData, _ := os.ReadFile(bridge)
	vendorData, _ := os.ReadFile(vendor)
	if !strings.Contains(string(bridgeData), "ros_topic_name: \"imu\"") {
		t.Fatalf("bridge override missing imu topic:\n%s", bridgeData)
	}
	if strings.Contains(string(bridgeData), "ros_topic_name: \"odometry\"") {
		t.Fatalf("bridge override must not publish Gazebo model odometry to bare /odometry:\n%s", bridgeData)
	}
	if !strings.Contains(string(bridgeData), "ros_topic_name: \"gazebo/model/odometry\"") {
		t.Fatalf("bridge override missing isolated Gazebo model odometry topic:\n%s", bridgeData)
	}
	if !strings.Contains(string(bridgeData), "ros_topic_name: \"rangefinder/down/scan_ideal\"") ||
		!strings.Contains(string(bridgeData), "gz_topic_name: \"/rangefinder/down/scan_ideal\"") ||
		!strings.Contains(string(bridgeData), "ros_type_name: \"sensor_msgs/msg/LaserScan\"") ||
		!strings.Contains(string(bridgeData), "gz_type_name: \"gz.msgs.LaserScan\"") {
		t.Fatalf("bridge override missing down rangefinder LaserScan bridge:\n%s", bridgeData)
	}
	if strings.Contains(string(bridgeData), "ros_topic_name: \"gz/tf\"") {
		t.Fatalf("bridge override must not publish Gazebo truth TF into legacy gz/tf namespace:\n%s", bridgeData)
	}
	if !strings.Contains(string(bridgeData), "ros_topic_name: \"gazebo/tf\"") {
		t.Fatalf("bridge override missing isolated Gazebo truth TF topic:\n%s", bridgeData)
	}
	if !strings.Contains(string(vendorData), "port: /tmp/x2") {
		t.Fatalf("vendor profile missing serial link:\n%s", vendorData)
	}
}
