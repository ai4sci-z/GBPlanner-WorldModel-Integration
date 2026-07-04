package layout

import (
	"os"
	"path/filepath"
)

const (
	AuditsDir         = "audits"
	DAGDir            = "dag"
	ProbesDir         = "probes"
	RuntimeDir        = "runtime"
	RuntimeScriptsDir = "runtime/scripts"
	RuntimeConfigDir  = "runtime/config"
	RuntimeLogsDir    = "runtime/logs"
	ProfilesDir       = "profiles"
	RosbagDir         = "rosbag"
	SITLDir           = "sitl"
)

var RootEntries = map[string]bool{
	"manifest.json":        true,
	"summary.json":         true,
	"summary.md":           true,
	"mission_summary.json": true,
	"task_plan.json":       true,
	"task_request.json":    true,
	"runtime_plan.json":    true,
	"run_config.toml":      true,
}

func Ensure(root string) error {
	for _, dir := range []string{AuditsDir, DAGDir, ProbesDir, RuntimeScriptsDir, RuntimeConfigDir, RuntimeLogsDir, ProfilesDir, RosbagDir, SITLDir} {
		if err := os.MkdirAll(filepath.Join(root, dir), 0o755); err != nil {
			return err
		}
	}
	return nil
}

func Audit(root, name string) string { return filepath.Join(root, AuditsDir, filepath.Base(name)) }
func DAG(root, name string) string   { return filepath.Join(root, DAGDir, filepath.Base(name)) }
func Probe(root, name string) string { return filepath.Join(root, ProbesDir, filepath.Base(name)) }
func Runtime(root, name string) string {
	return filepath.Join(root, RuntimeDir, filepath.Base(name))
}
func RuntimeScript(root, name string) string {
	return filepath.Join(root, RuntimeScriptsDir, filepath.Base(name))
}
func RuntimeConfig(root, name string) string {
	return filepath.Join(root, RuntimeConfigDir, filepath.Base(name))
}
func RuntimeLog(root, name string) string {
	return filepath.Join(root, RuntimeLogsDir, filepath.Base(name))
}
func Profile(root, name string) string { return filepath.Join(root, ProfilesDir, filepath.Base(name)) }
func RosbagOutputDir(root, name string) string {
	return filepath.Join(root, RosbagDir, filepath.Base(name))
}
func SITL(root string, elems ...string) string {
	parts := append([]string{root, SITLDir}, elems...)
	return filepath.Join(parts...)
}

func AuditRel(name string) string {
	return filepath.ToSlash(filepath.Join(AuditsDir, filepath.Base(name)))
}
func DAGRel(name string) string {
	return filepath.ToSlash(filepath.Join(DAGDir, filepath.Base(name)))
}
func ProbeRel(name string) string {
	return filepath.ToSlash(filepath.Join(ProbesDir, filepath.Base(name)))
}
func RuntimeRel(name string) string {
	return filepath.ToSlash(filepath.Join(RuntimeDir, filepath.Base(name)))
}
func RuntimeScriptRel(name string) string {
	return filepath.ToSlash(filepath.Join(RuntimeScriptsDir, filepath.Base(name)))
}
func RuntimeConfigRel(name string) string {
	return filepath.ToSlash(filepath.Join(RuntimeConfigDir, filepath.Base(name)))
}
func RuntimeLogRel(name string) string {
	return filepath.ToSlash(filepath.Join(RuntimeLogsDir, filepath.Base(name)))
}
func ProfileRel(name string) string {
	return filepath.ToSlash(filepath.Join(ProfilesDir, filepath.Base(name)))
}
func RosbagOutputDirRel(name string) string {
	return filepath.ToSlash(filepath.Join(RosbagDir, filepath.Base(name)))
}
func SITLRel(elems ...string) string {
	parts := append([]string{SITLDir}, elems...)
	return filepath.ToSlash(filepath.Join(parts...))
}
