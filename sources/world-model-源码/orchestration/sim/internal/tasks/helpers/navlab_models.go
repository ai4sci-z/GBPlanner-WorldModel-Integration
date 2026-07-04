package helpers

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

const (
	GazeboSensorContainer      = "navlab-official-maze-x2-sensor"
	CartographerContainer      = "navlab-official-maze-x2-cartographer"
	OfficialIris3DBridgeConfig = "/opt/navlab_official_ws/install/ardupilot_gz_bringup/share/ardupilot_gz_bringup/config/iris_3Dlidar_bridge.yaml"
)

func WriteBridgeOverride(path string) error {
	return writeBridgeOverride(path, "imu")
}

func WriteVendorProfile(path string, virtualSerialLink string) error {
	rendered, err := renderHelperTemplate("yaml/vendor_profile.yaml.tmpl", map[string]any{
		"VirtualSerialLink": virtualSerialLink,
	})
	if err != nil {
		return err
	}
	return writeText(path, rendered)
}

func WriteModelOverlayFromSource(path string, source string, spec SensorRuntimeSpec) error {
	if !strings.Contains(source, "</model>") {
		return errors.New("official iris_with_lidar model does not contain a closing </model> tag")
	}
	source = strings.Replace(source, "model://lidar_3d", "model://lidar_2d", 1)
	overlay, err := renderHelperTemplate("sdf/rangefinder_down_overlay.sdf.tmpl", spec)
	if err != nil {
		return err
	}
	rendered := strings.Replace(source, "</model>", overlay+"\n  </model>", 1)
	return writeText(path, rendered)
}

func writeBridgeOverride(path string, imuRosTopic string) error {
	rendered, err := renderHelperTemplate("yaml/bridge_override.yaml.tmpl", map[string]any{
		"IMURosTopic": imuRosTopic,
	})
	if err != nil {
		return err
	}
	return writeText(path, rendered)
}

func WriteParamOverlayFromSource(path string, source string, spec SensorRuntimeSpec) error {
	minCM := int(spec.RangefinderMinDistanceM*100 + 0.5)
	maxCM := int(spec.RangefinderMaxDistanceM*100 + 0.5)
	orientation := 25
	overlay := missingParamLines(source, map[string]string{
		"RNGFND1_TYPE":     "20",
		"RNGFND1_ORIENT":   fmt.Sprintf("%d", orientation),
		"RNGFND1_MIN_CM":   fmt.Sprintf("%d", minCM),
		"RNGFND1_MAX_CM":   fmt.Sprintf("%d", maxCM),
		"RNGFND1_GNDCLEAR": "15",
	})
	if overlay == "" {
		return writeText(path, strings.TrimRight(source, "\n")+"\n")
	}
	return writeText(path, strings.TrimRight(source, "\n")+"\n\n# NavLab hardware-faithful down rangefinder overlay.\n"+overlay)
}

func missingParamLines(source string, defaults map[string]string) string {
	seen := map[string]bool{}
	for _, line := range strings.Split(source, "\n") {
		fields := strings.Fields(line)
		if len(fields) == 0 || strings.HasPrefix(fields[0], "#") {
			continue
		}
		seen[fields[0]] = true
	}
	keys := []string{"RNGFND1_TYPE", "RNGFND1_ORIENT", "RNGFND1_MIN_CM", "RNGFND1_MAX_CM", "RNGFND1_GNDCLEAR"}
	lines := []string{}
	for _, key := range keys {
		if seen[key] {
			continue
		}
		lines = append(lines, key+" "+defaults[key])
	}
	if len(lines) == 0 {
		return ""
	}
	return strings.Join(lines, "\n") + "\n"
}

func writeText(path string, text string) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	return os.WriteFile(path, []byte(text), 0o644)
}

func shellQuote(value string) string {
	if value == "" {
		return "''"
	}
	return "'" + strings.ReplaceAll(value, "'", "'\"'\"'") + "'"
}
