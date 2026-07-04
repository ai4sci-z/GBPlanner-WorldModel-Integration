package helpers

import (
	"fmt"
	"sort"
	"strings"
)

type Definition struct {
	ID              string   `json:"id"`
	Phase           string   `json:"phase"`
	Role            string   `json:"role"`
	ArtifactOutputs []string `json:"artifact_outputs,omitempty"`
	RuntimeAction   bool     `json:"runtime_action"`
	MigrationStatus string   `json:"migration_status"`
}

type Registry struct {
	definitions map[string]Definition
}

func NewRegistry() *Registry {
	return &Registry{definitions: map[string]Definition{}}
}

func DefaultRegistry() *Registry {
	registry := NewRegistry()
	for _, definition := range []Definition{
		{
			ID:              "artifacts",
			Phase:           "artifact",
			Role:            "write JSON/text artifacts and compute sha256",
			ArtifactOutputs: []string{"*.json", "*.txt", "sha256"},
			RuntimeAction:   false,
			MigrationStatus: "ported_basic",
		},
		{
			ID:              "rosbag-profiles",
			Phase:           "artifact",
			Role:            "parse rosbag topic profiles and metadata counts",
			ArtifactOutputs: []string{"rosbag_profile_summary.json"},
			RuntimeAction:   false,
			MigrationStatus: "ported_basic",
		},
		{
			ID:              "navlab-models",
			Phase:           "simulation_setup",
			Role:            "write bridge/vendor profiles, manage gazebo-sensor container, collect topic samples",
			ArtifactOutputs: []string{"bridge_override.yaml", "vendor_profile.yaml", "topic probes", "container logs"},
			RuntimeAction:   true,
			MigrationStatus: "ported_partial",
		},
		{
			ID:              "official-stack",
			Phase:           "doctor_probe",
			Role:            "official baseline dependency checks, ROS graph probes, DDS probe",
			ArtifactOutputs: []string{"ros_graph.txt", "official_dds_probe.txt", "doctor summary"},
			RuntimeAction:   true,
			MigrationStatus: "ported_partial",
		},
		{
			ID:              "sensors",
			Phase:           "simulation_setup",
			Role:            "write lidar/rangefinder model overlays, parameter overlays, sensor runtime config, IMU/range probes",
			ArtifactOutputs: []string{"model_overlay.sdf", "param_overlay.parm", "gazebo_sensor_runtime.toml", "sensor probes"},
			RuntimeAction:   true,
			MigrationStatus: "ported_partial",
		},
		{
			ID:              "slam",
			Phase:           "runtime",
			Role:            "write SLAM runtime config, start SLAM container, collect odometry quality",
			ArtifactOutputs: []string{"slam_runtime.toml", "slam odometry probe", "slam doctor summary"},
			RuntimeAction:   true,
			MigrationStatus: "ported_partial",
		},
		{
			ID:              "fcu-controller",
			Phase:           "runtime",
			Role:            "write FCU controller config/script, start controller container, validate owner/controller summaries",
			ArtifactOutputs: []string{"fcu_controller_runtime.toml", "controller script", "controller summary"},
			RuntimeAction:   true,
			MigrationStatus: "ported_partial",
		},
		{
			ID:              "frame-contract",
			Phase:           "doctor_probe",
			Role:            "write frame contract runtime/probe script and evaluate TF/frame blockers",
			ArtifactOutputs: []string{"frame_contract_runtime.toml", "frame probe", "frame doctor summary"},
			RuntimeAction:   true,
			MigrationStatus: "ported_partial",
		},
		{
			ID:              "slam-hover",
			Phase:           "acceptance_probe",
			Role:            "write hover runtime/probe scripts, rosbag profile, vehicle markers, hover blockers",
			ArtifactOutputs: []string{"slam_hover_runtime.toml", "hover probe", "rosbag profile", "foxglove notes"},
			RuntimeAction:   true,
			MigrationStatus: "ported_partial",
		},
		{
			ID:              "slam-only",
			Phase:           "validation_probe",
			Role:            "write SLAM-only probe and rosbag profile without hover mission or external-nav injection",
			ArtifactOutputs: []string{"slam_only_probe.json", "slam_only_rosbag", "summary.json"},
			RuntimeAction:   true,
			MigrationStatus: "ported_partial",
		},
		{
			ID:              "motion",
			Phase:           "doctor_probe",
			Role:            "build bounded motion doctor summary for exploration dependencies",
			ArtifactOutputs: []string{"motion doctor summary"},
			RuntimeAction:   false,
			MigrationStatus: "ported_basic",
		},
		{
			ID:              "landing",
			Phase:           "acceptance_gate",
			Role:            "apply landing policy and landing acceptance blockers",
			ArtifactOutputs: []string{"landing acceptance summary"},
			RuntimeAction:   false,
			MigrationStatus: "ported_basic",
		},
		{
			ID:              "scan-integrity",
			Phase:           "doctor_probe",
			Role:            "scan integrity blocker summaries and Foxglove notes",
			ArtifactOutputs: []string{"scan integrity notes"},
			RuntimeAction:   false,
			MigrationStatus: "ported_basic",
		},
		{
			ID:              "scan-stabilization",
			Phase:           "runtime",
			Role:            "write scan stabilization sensor/runtime configs, run scan stabilization gate, collect fault profile",
			ArtifactOutputs: []string{"scan stabilization runtime configs", "stabilization status", "summary.json"},
			RuntimeAction:   true,
			MigrationStatus: "ported_partial",
		},
		{
			ID:              "exploration-workflow",
			Phase:           "task_workflow",
			Role:            "exploration model/sensor/runtime configs, exploration probe, rosbag, doctor and acceptance summary",
			ArtifactOutputs: []string{"exploration runtime configs", "exploration probe", "rosbag", "summary.json"},
			RuntimeAction:   true,
			MigrationStatus: "ported_partial",
		},
		{
			ID:              "nav2-navigation-workflow",
			Phase:           "task_workflow",
			Role:            "Nav2 params, navigation adapter config, costmap probes, rosbag, doctor and acceptance summary",
			ArtifactOutputs: []string{"nav2 params", "adapter runtime config", "navigation probes", "rosbag", "summary.json"},
			RuntimeAction:   true,
			MigrationStatus: "ported_partial",
		},
		{
			ID:              "scan-robustness-workflow",
			Phase:           "task_workflow",
			Role:            "scan robustness airframe disturbance runtime configs, profile sweep/live replay, summary gates",
			ArtifactOutputs: []string{"scan robustness runtime configs", "profile sweep summary", "summary.json"},
			RuntimeAction:   true,
			MigrationStatus: "ported_partial",
		},
	} {
		mustRegister(registry, definition)
	}
	return registry
}

func mustRegister(registry *Registry, definition Definition) {
	if err := registry.Register(definition); err != nil {
		panic(err)
	}
}

func (registry *Registry) Register(definition Definition) error {
	id := strings.TrimSpace(definition.ID)
	if id == "" {
		return fmt.Errorf("helper definition id cannot be empty")
	}
	if _, exists := registry.definitions[id]; exists {
		return fmt.Errorf("helper %q is already registered", id)
	}
	definition.ID = id
	registry.definitions[id] = definition
	return nil
}

func (registry *Registry) MustGet(id string) Definition {
	definition, err := registry.Get(id)
	if err != nil {
		panic(err)
	}
	return definition
}

func (registry *Registry) Get(id string) (Definition, error) {
	normalized := strings.TrimSpace(id)
	definition, exists := registry.definitions[normalized]
	if !exists {
		return Definition{}, fmt.Errorf("unknown helper %q", normalized)
	}
	return definition, nil
}

func (registry *Registry) Resolve(ids []string) ([]Definition, error) {
	definitions := make([]Definition, 0, len(ids))
	for _, id := range ids {
		definition, err := registry.Get(id)
		if err != nil {
			return nil, err
		}
		definitions = append(definitions, definition)
	}
	return definitions, nil
}

func (registry *Registry) List() []Definition {
	definitions := make([]Definition, 0, len(registry.definitions))
	for _, definition := range registry.definitions {
		definitions = append(definitions, definition)
	}
	sort.Slice(definitions, func(i, j int) bool {
		return definitions[i].ID < definitions[j].ID
	})
	return definitions
}
