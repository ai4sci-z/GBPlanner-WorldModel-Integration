package config

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"github.com/spf13/viper"
)

type Loader struct {
	configPath string
}

func NewLoader(configPath string) Loader {
	return Loader{configPath: configPath}
}

func (l Loader) LoadProject() (ProjectConfig, error) {
	var cfg ProjectConfig
	configPath, err := l.ConfigPath()
	if err != nil {
		return cfg, err
	}
	v := viper.New()
	v.SetConfigFile(configPath)
	v.SetConfigType("toml")
	if err := v.ReadInConfig(); err != nil {
		return cfg, err
	}
	if err := v.Unmarshal(&cfg); err != nil {
		return cfg, err
	}
	cfg.Sections = projectConfigSections(configPath)
	normalizeProject(&cfg)
	if err := validateProject(cfg); err != nil {
		return cfg, err
	}
	return cfg, nil
}

func (l Loader) ConfigPath() (string, error) {
	return resolveConfigPath(l.configPath)
}

func (l Loader) ResolveProjectPath(path string) (string, error) {
	if strings.TrimSpace(path) == "" {
		return "", errors.New("path cannot be empty")
	}
	if filepath.IsAbs(path) {
		return filepath.Clean(path), nil
	}
	configPath, err := l.ConfigPath()
	if err != nil {
		return "", err
	}
	return filepath.Clean(filepath.Join(filepath.Dir(configPath), path)), nil
}

func (l Loader) LoadTasks(project ProjectConfig) ([]TaskConfig, error) {
	taskDir, err := l.taskDir(project)
	if err != nil {
		return nil, err
	}
	entries, err := os.ReadDir(taskDir)
	if err != nil {
		return nil, err
	}
	var tasks []TaskConfig
	for _, entry := range entries {
		if entry.IsDir() || !isYAML(entry.Name()) {
			continue
		}
		task, err := loadTaskFile(filepath.Join(taskDir, entry.Name()))
		if err != nil {
			return nil, err
		}
		tasks = append(tasks, task)
	}
	sort.Slice(tasks, func(i, j int) bool {
		return tasks[i].ID < tasks[j].ID
	})
	return tasks, nil
}

func (l Loader) LoadTask(project ProjectConfig, taskID string) (TaskConfig, error) {
	normalized := strings.TrimSpace(taskID)
	if normalized == "" {
		return TaskConfig{}, errors.New("task id cannot be empty")
	}
	tasks, err := l.LoadTasks(project)
	if err != nil {
		return TaskConfig{}, err
	}
	for _, task := range tasks {
		if task.ID == normalized {
			return task, nil
		}
	}
	return TaskConfig{}, fmt.Errorf("unknown task id %q", normalized)
}

func (l Loader) taskDir(project ProjectConfig) (string, error) {
	if strings.TrimSpace(project.Paths.TaskConfigDir) == "" {
		return "", errors.New("paths.task_config_dir is required")
	}
	if filepath.IsAbs(project.Paths.TaskConfigDir) {
		return project.Paths.TaskConfigDir, nil
	}
	configPath, err := l.ConfigPath()
	if err != nil {
		return "", err
	}
	base := filepath.Dir(configPath)
	return filepath.Clean(filepath.Join(base, project.Paths.TaskConfigDir)), nil
}

func resolveConfigPath(configPath string) (string, error) {
	if _, err := os.Stat(configPath); err == nil {
		return configPath, nil
	}
	for _, candidate := range []string{
		"config.toml",
		filepath.Join("orchestration", "sim", "config.toml"),
		filepath.Join("..", "..", "config.toml"),
	} {
		if _, err := os.Stat(candidate); err == nil {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("config file not found: %s", configPath)
}

func loadTaskFile(path string) (TaskConfig, error) {
	var task TaskConfig
	v := viper.New()
	v.SetConfigFile(path)
	v.SetConfigType("yaml")
	if err := v.ReadInConfig(); err != nil {
		return task, err
	}
	if err := v.Unmarshal(&task); err != nil {
		return task, err
	}
	if err := validateTask(task); err != nil {
		return task, fmt.Errorf("%s: %w", path, err)
	}
	return task, nil
}

func validateProject(cfg ProjectConfig) error {
	if cfg.Orchestration.Family != "sim" {
		return fmt.Errorf("orchestration.family must be sim, got %q", cfg.Orchestration.Family)
	}
	if cfg.Orchestration.Implementation != "go" {
		return fmt.Errorf("orchestration.implementation must be go, got %q", cfg.Orchestration.Implementation)
	}
	if cfg.Runtime.Mode != "simulation" {
		return fmt.Errorf("runtime.mode must be simulation, got %q", cfg.Runtime.Mode)
	}
	if cfg.Runtime.Backend == "" {
		return errors.New("runtime.backend is required")
	}
	if cfg.Orchestration.Runtime.Docker.WorkspaceContainerPath == "" {
		return errors.New("orchestration.runtime.docker.workspace_container_path is required")
	}
	if len(cfg.Images) == 0 {
		return errors.New("navlab.images must define at least one image")
	}
	if !cfg.Sections.Nav2 {
		return errors.New("nav2 section is required")
	}
	if !cfg.Sections.Nav2Costmap {
		return errors.New("nav2.costmap section is required")
	}
	if !cfg.Sections.NavigationAdapter {
		return errors.New("navigation_adapter section is required")
	}
	if !cfg.Sections.NavigationMission {
		return errors.New("navigation_mission section is required")
	}
	return nil
}

func projectConfigSections(path string) ProjectConfigSections {
	data, err := os.ReadFile(path)
	if err != nil {
		return ProjectConfigSections{}
	}
	lines := strings.Split(string(data), "\n")
	sections := ProjectConfigSections{}
	for _, line := range lines {
		section := strings.TrimSpace(line)
		switch section {
		case "[nav2]":
			sections.Nav2 = true
		case "[nav2.costmap]":
			sections.Nav2Costmap = true
		case "[navigation_adapter]":
			sections.NavigationAdapter = true
		case "[navigation_mission]":
			sections.NavigationMission = true
		}
	}
	return ProjectConfigSections{
		Nav2:              sections.Nav2,
		Nav2Costmap:       sections.Nav2Costmap,
		NavigationAdapter: sections.NavigationAdapter,
		NavigationMission: sections.NavigationMission,
	}
}

func normalizeProject(cfg *ProjectConfig) {
	if cfg.Runtime.Mode == "" {
		cfg.Runtime.Mode = cfg.Orchestration.Runtime.Mode
	}
	if cfg.Runtime.Backend == "" {
		cfg.Runtime.Backend = cfg.Orchestration.Runtime.Backend
	}
	if cfg.Orchestration.Runtime.Mode == "" {
		cfg.Orchestration.Runtime.Mode = cfg.Runtime.Mode
	}
	if cfg.Orchestration.Runtime.Backend == "" {
		cfg.Orchestration.Runtime.Backend = cfg.Runtime.Backend
	}
	if len(cfg.Images) == 0 && len(cfg.Navlab.Images.Catalog) > 0 {
		cfg.Images = cfg.Navlab.Images.Catalog
	}
	if cfg.Navlab.Images.TagPolicy == "" {
		if cfg.Navlab.Images.TagStrategy != "" {
			cfg.Navlab.Images.TagPolicy = cfg.Navlab.Images.TagStrategy
		} else {
			cfg.Navlab.Images.TagPolicy = "distro-git-commit"
		}
	}
	if cfg.Navlab.Images.TagStrategy == "" {
		cfg.Navlab.Images.TagStrategy = cfg.Navlab.Images.TagPolicy
	}
	if cfg.Navlab.Images.Distro == "" {
		cfg.Navlab.Images.Distro = "humble"
	}
	applySimulationDefaults(cfg)
}

func validateTask(task TaskConfig) error {
	if strings.TrimSpace(task.ID) == "" {
		return errors.New("id is required")
	}
	if task.Family != "sim" {
		return fmt.Errorf("family must be sim, got %q", task.Family)
	}
	if task.Task.DurationSec < 0 {
		return errors.New("task.duration_sec cannot be negative")
	}
	if task.Task.TimeoutSec < 0 {
		return errors.New("task.timeout_sec cannot be negative")
	}
	return nil
}

func isYAML(name string) bool {
	ext := strings.ToLower(filepath.Ext(name))
	return ext == ".yaml" || ext == ".yml"
}
