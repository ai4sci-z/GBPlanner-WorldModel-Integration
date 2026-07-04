package tasks

import (
	"fmt"
	"sort"
	"strings"

	"navlab/orchestration-sim/internal/config"
)

type Registry struct {
	definitions map[string]Definition
}

func NewRegistry() *Registry {
	return &Registry{definitions: map[string]Definition{}}
}

func DefaultRegistry() *Registry {
	registry := NewRegistry()
	mustRegister(registry, Definition{
		ID:          "hover",
		Description: "SITL hover gate over Gazebo with SLAM and landing checks.",
		Steps: []string{
			"load task YAML config",
			"validate simulation source claims",
			"generate model, sensor, SLAM, frame, hover mission, rosbag, and landing artifacts",
			"start Gazebo/SITL stack",
			"start companion and SLAM runtime",
			"record rosbag and collect task result artifacts",
		},
		HelperIDs: []string{
			"artifacts",
			"navlab-models",
			"official-stack",
			"sensors",
			"slam",
			"frame-contract",
			"slam-hover",
			"landing",
			"rosbag-profiles",
		},
	})
	mustRegister(registry, Definition{
		ID:          "hover-slam-only",
		Description: "SLAM-only hover preflight over Gazebo without FCU takeoff or external-nav injection.",
		Steps: []string{
			"load task YAML config",
			"generate model, sensor, SLAM, frame, and SLAM-only rosbag artifacts",
			"start Gazebo/SITL stack without hover mission or FCU controller",
			"start sensor bridge and Cartographer SLAM runtime",
			"record SLAM-only rosbag and collect SLAM health probe",
		},
		HelperIDs: []string{
			"artifacts",
			"navlab-models",
			"sensors",
			"slam",
			"slam-only",
			"rosbag-profiles",
		},
	})
	mustRegister(registry, Definition{
		ID:          "exploration",
		Description: "Official-maze exploration gate over Gazebo/SITL.",
		Steps: []string{
			"load task YAML config",
			"validate simulation source claims",
			"generate model, sensor, SLAM, controller, frame, exploration, rosbag, and landing artifacts",
			"start official maze Gazebo/SITL stack",
			"start exploration controller runtime",
			"record rosbag and collect task result artifacts",
		},
		HelperIDs: []string{
			"artifacts",
			"navlab-models",
			"official-stack",
			"sensors",
			"slam",
			"fcu-controller",
			"frame-contract",
			"motion",
			"landing",
			"rosbag-profiles",
			"exploration-workflow",
		},
	})
	mustRegister(registry, Definition{
		ID:          "navigation",
		Description: "Nav2 indoor navigation gate over Gazebo/SITL.",
		Steps: []string{
			"load task YAML config",
			"validate simulation source claims",
			"generate model, sensor, SLAM, controller, frame, Nav2, adapter, rosbag, and landing artifacts",
			"start official maze Gazebo/SITL stack",
			"start SLAM, Nav2, and navigation adapter runtime",
			"record rosbag and collect task result artifacts",
		},
		HelperIDs: []string{
			"artifacts",
			"navlab-models",
			"official-stack",
			"sensors",
			"slam",
			"fcu-controller",
			"frame-contract",
			"slam-hover",
			"motion",
			"scan-integrity",
			"scan-stabilization",
			"landing",
			"rosbag-profiles",
			"nav2-navigation-workflow",
		},
	})
	mustRegister(registry, Definition{
		ID:          "scan-robustness",
		Description: "Airframe disturbance and scan robustness simulation gate.",
		Steps: []string{
			"load task YAML config",
			"validate simulation source claims",
			"generate sensor, stabilization, disturbance, rosbag, and landing artifacts",
			"start Gazebo/SITL and gazebo-sensor runtime",
			"apply configured disturbance profiles",
			"record rosbag and collect task result artifacts",
		},
		HelperIDs: []string{
			"artifacts",
			"navlab-models",
			"official-stack",
			"sensors",
			"slam",
			"fcu-controller",
			"frame-contract",
			"slam-hover",
			"landing",
			"rosbag-profiles",
			"scan-integrity",
			"scan-stabilization",
			"scan-robustness-workflow",
		},
	})
	return registry
}

func mustRegister(registry *Registry, definition Definition) {
	if err := registry.Register(definition); err != nil {
		panic(err)
	}
}

func (registry *Registry) Register(definition Definition) error {
	id := normalizeID(definition.ID)
	if id == "" {
		return fmt.Errorf("task definition id cannot be empty")
	}
	if _, exists := registry.definitions[id]; exists {
		return fmt.Errorf("task %q is already registered", id)
	}
	definition.ID = id
	registry.definitions[id] = definition
	return nil
}

func (registry *Registry) Configure(taskConfigs []config.TaskConfig) ([]ConfiguredTask, error) {
	configured := make([]ConfiguredTask, 0, len(taskConfigs))
	for _, taskConfig := range taskConfigs {
		task, err := registry.ConfigureOne(taskConfig)
		if err != nil {
			return nil, err
		}
		configured = append(configured, task)
	}
	sort.Slice(configured, func(i, j int) bool {
		return configured[i].Config.ID < configured[j].Config.ID
	})
	return configured, nil
}

func (registry *Registry) ConfigureOne(taskConfig config.TaskConfig) (ConfiguredTask, error) {
	id := normalizeID(taskConfig.ID)
	definition, exists := registry.definitions[id]
	if !exists {
		return ConfiguredTask{}, fmt.Errorf("task %q has config but is not registered", id)
	}
	taskConfig.ID = id
	if strings.TrimSpace(taskConfig.Description) == "" {
		taskConfig.Description = definition.Description
	}
	return ConfiguredTask{Definition: definition, Config: taskConfig}, nil
}

func normalizeID(id string) string {
	return strings.TrimSpace(id)
}
