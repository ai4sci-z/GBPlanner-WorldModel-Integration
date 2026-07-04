package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"navlab/orchestration-sim/internal/artifacts"
	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
	hoveraudit "navlab/orchestration-sim/internal/audits/hover"
	"navlab/orchestration-sim/internal/config"
	simfoxglove "navlab/orchestration-sim/internal/foxglove"
	simimages "navlab/orchestration-sim/internal/images"
	simruntime "navlab/orchestration-sim/internal/runtime"
	"navlab/orchestration-sim/internal/tasks"
	"navlab/orchestration-sim/internal/tasks/helpers"
	simtui "navlab/orchestration-sim/internal/tui"
	"navlab/orchestration-sim/internal/ui"
)

const defaultConfigPath = "config.toml"

type appContext struct {
	configPath   string
	artifactRoot string
}

type preparedTaskRun struct {
	Project            config.ProjectConfig
	TaskConfig         config.TaskConfig
	TaskRuntimeConfig  config.TaskRuntimeConfig
	Plan               tasks.Plan
	Result             artifacts.DryRunResult
	GeneratedArtifacts []tasks.GeneratedRuntimeArtifact
	RuntimeSpecs       tasks.RuntimeSpecBundle
	WorkflowBundle     tasks.SimWorkflowBundle
}

func main() {
	if err := newRootCommand().Execute(); err != nil {
		fmt.Fprintln(os.Stderr, ui.Error("error: "+err.Error()))
		os.Exit(1)
	}
}

func newRootCommand() *cobra.Command {
	ctx := &appContext{}
	root := &cobra.Command{
		Use:           "navlab-sim",
		Short:         "NavLab simulation orchestration control plane",
		SilenceUsage:  true,
		SilenceErrors: true,
	}
	root.PersistentFlags().StringVar(
		&ctx.configPath,
		"config",
		defaultConfigPath,
		"sim orchestration TOML config path",
	)
	root.PersistentFlags().StringVar(
		&ctx.artifactRoot,
		"artifact-root",
		"",
		"override sim artifact root",
	)
	root.AddCommand(
		newDoctorCommand(ctx),
		newTaskDoctorCommand(ctx, "hover"),
		newTaskDoctorCommand(ctx, "exploration"),
		newTaskDoctorCommand(ctx, "scan-robustness"),
		newListHelpersCommand(),
		newListTasksCommand(ctx),
		newShowTaskCommand(ctx),
		newRunCommand(ctx),
		newStage1MatrixCommand(ctx),
		newTUICommand(),
		newBuildCommand(ctx),
		newAuditCommand(ctx),
		newFoxgloveCommand(ctx),
	)
	return root
}

func newTaskDoctorCommand(ctx *appContext, taskID string) *cobra.Command {
	return &cobra.Command{
		Use:   taskID + "-doctor",
		Short: "Run static doctor checks for the " + taskID + " simulation task",
		RunE: func(cmd *cobra.Command, args []string) error {
			return doctorTask(ctx.loader(), ctx.registry(), ctx.helperRegistry(), taskID, ctx.artifactRoot)
		},
	}
}

func (ctx *appContext) loader() config.Loader {
	return config.NewLoader(ctx.configPath)
}

func (ctx *appContext) registry() *tasks.Registry {
	return tasks.DefaultRegistry()
}

func (ctx *appContext) helperRegistry() *helpers.Registry {
	return helpers.DefaultRegistry()
}

func newDoctorCommand(ctx *appContext) *cobra.Command {
	return &cobra.Command{
		Use:   "doctor",
		Short: "Validate sim orchestration and task config loading",
		RunE: func(cmd *cobra.Command, args []string) error {
			return doctor(ctx.loader())
		},
	}
}

func newListTasksCommand(ctx *appContext) *cobra.Command {
	return &cobra.Command{
		Use:   "list-tasks",
		Short: "List registered simulation task configs",
		RunE: func(cmd *cobra.Command, args []string) error {
			return listTasks(ctx.loader())
		},
	}
}

func newListHelpersCommand() *cobra.Command {
	return &cobra.Command{
		Use:   "list-helpers",
		Short: "List migrated non-real Python task helpers",
		RunE: func(cmd *cobra.Command, args []string) error {
			return listHelpers(helpers.DefaultRegistry())
		},
	}
}

func newShowTaskCommand(ctx *appContext) *cobra.Command {
	return &cobra.Command{
		Use:   "show-task <task-id>",
		Short: "Show one simulation task config",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			return showTask(ctx.loader(), args[0])
		},
	}
}

func newRunCommand(ctx *appContext) *cobra.Command {
	var dryRun bool
	var tuiMode bool
	var livePreflight bool
	var durationSec float64
	var simulationProfile string
	var hoverSpanTargetM float64
	var hoverSpanHardCapM float64
	cmd := &cobra.Command{
		Use:   "run <task-id>",
		Short: "Plan or run one simulation task",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			return runTask(
				ctx.loader(),
				ctx.registry(),
				ctx.helperRegistry(),
				args[0],
				dryRun,
				tuiMode,
				livePreflight,
				ctx.artifactRoot,
				tasks.PlanOptions{
					DurationSec:       durationSec,
					SimulationProfile: simulationProfile,
					HoverSpanTargetM:  hoverSpanTargetM,
					HoverSpanHardCapM: hoverSpanHardCapM,
				},
			)
		},
	}
	cmd.Flags().BoolVar(&dryRun, "dry-run", false, "print the task plan without starting runtime services")
	cmd.Flags().BoolVar(&tuiMode, "tui", false, "open the replay TUI after dry-run artifact generation")
	cmd.Flags().BoolVar(&livePreflight, "live-preflight", false, "probe Docker daemon, image availability, and networks without starting runtime services")
	cmd.Flags().Float64Var(&durationSec, "duration-sec", 0, "override task duration in seconds")
	cmd.Flags().StringVar(&simulationProfile, "simulation-profile", "", "override simulation profile")
	cmd.Flags().Float64Var(&hoverSpanTargetM, "hover-span-target-m", 0, "override hover XY span SLO target in meters")
	cmd.Flags().Float64Var(&hoverSpanHardCapM, "hover-span-hard-cap-m", 0, "override hover XY span hard cap in meters")
	return cmd
}

func newStage1MatrixCommand(ctx *appContext) *cobra.Command {
	var summaryPaths []string
	var outputPath string
	cmd := &cobra.Command{
		Use:   "stage1-matrix <task-id>",
		Short: "Aggregate Stage 1 simulation profile summaries for one task",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			return stage1Matrix(ctx.loader(), args[0], summaryPaths, outputPath)
		},
	}
	cmd.Flags().StringArrayVar(&summaryPaths, "summary", nil, "summary.json path from one simulation profile run; repeat for multiple profiles")
	cmd.Flags().StringVar(&outputPath, "output", "stage1_profile_matrix.json", "output Stage 1 profile matrix JSON path")
	return cmd
}

func newTUICommand() *cobra.Command {
	return &cobra.Command{
		Use:   "tui <artifact-dir>",
		Short: "Open a replay TUI for one simulation artifact directory",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			return simtui.RunReplay(args[0], simtui.RunOptions{RequireTTY: true})
		},
	}
}

func newBuildCommand(ctx *appContext) *cobra.Command {
	var image string
	var tag string
	var distro string
	var dryRun bool
	cmd := &cobra.Command{
		Use:   "build <base|infra|runtime|all>",
		Short: "Build NavLab simulation Docker images",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			return buildImages(ctx.loader(), args[0], image, tag, distro, dryRun)
		},
	}
	cmd.Flags().StringVar(&image, "image", "", "build one image inside the selected infra or runtime group")
	cmd.Flags().StringVar(&tag, "tag", "", "override configured NavLab image tag")
	cmd.Flags().StringVar(&distro, "distro", "", "override ROS distro; defaults to NAVLAB_SIM_DISTRO or humble")
	cmd.Flags().BoolVar(&dryRun, "dry-run", false, "print Docker SDK image build plans without running them")
	return cmd
}

func newAuditCommand(ctx *appContext) *cobra.Command {
	cmd := &cobra.Command{
		Use:   "audit",
		Short: "Run artifact audits for sim runs",
	}
	cmd.AddCommand(newAuditHoverCommand(ctx))
	return cmd
}

func newAuditHoverCommand(ctx *appContext) *cobra.Command {
	cmd := &cobra.Command{
		Use:   "hover",
		Short: "Run hover artifact audits",
	}
	cmd.AddCommand(
		newAuditHoverSingleCommand(
			"contract",
			"Build Phase 43 hover topic-contract audit JSON",
			"contract_audit.json",
			hoveraudit.BuildHoverContractAudit,
		),
		newAuditHoverHealthCommand(),
		newAuditHoverInitCommand(),
		newAuditHoverSingleCommand(
			"source",
			"Build hover raw-source pairwise audit JSON",
			"raw_source_audit.json",
			hoveraudit.BuildHoverRawSourceAudit,
		),
		newAuditHoverSingleCommand(
			"trajectory",
			"Build hover time-aligned trajectory audit JSON",
			"trajectory_audit.json",
			hoveraudit.BuildHoverTrajectoryAudit,
		),
		newAuditHoverGateReplayCommand(ctx),
	)
	return cmd
}

func newAuditHoverSingleCommand(name string, short string, defaultOutput string, build func(string) (map[string]any, error)) *cobra.Command {
	var output string
	cmd := &cobra.Command{
		Use:   name + " <artifact-dir>",
		Short: short,
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			artifactDir := args[0]
			audit, err := build(artifactDir)
			if err != nil {
				return err
			}
			if output == "" {
				output = artifactlayout.Audit(artifactDir, defaultOutput)
			}
			return writeAuditJSON(output, audit)
		},
	}
	cmd.Flags().StringVar(&output, "output", "", "output JSON path; defaults to <artifact-dir>/"+artifactlayout.AuditRel(defaultOutput))
	return cmd
}

func newAuditHoverHealthCommand() *cobra.Command {
	var output string
	cmd := &cobra.Command{
		Use:   "health <artifact-dir> [<artifact-dir>...]",
		Short: "Build hover health audit JSON for one run or a cohort",
		Args:  cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			var payload any
			if len(args) == 1 {
				artifactDir := args[0]
				audit, err := hoveraudit.BuildHoverHealthAudit(artifactDir)
				if err != nil {
					return err
				}
				payload = audit
				if output == "" {
					output = artifactlayout.Audit(artifactDir, "hover_health_summary.json")
				}
			} else {
				cohort, err := hoveraudit.BuildHoverHealthCohort(args)
				if err != nil {
					return err
				}
				payload = cohort
			}
			return writeAuditJSON(output, payload)
		},
	}
	cmd.Flags().StringVar(&output, "output", "", "output JSON path; defaults to <artifact-dir>/audits/hover_health_summary.json for one run, stdout for cohorts")
	return cmd
}

func newAuditHoverInitCommand() *cobra.Command {
	var output string
	cmd := &cobra.Command{
		Use:   "init <artifact-dir> [<artifact-dir>...]",
		Short: "Build hover initialization audit JSON for one run or a comparison",
		Args:  cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			audits := make([]map[string]any, 0, len(args))
			for _, artifactDir := range args {
				audit, err := hoveraudit.BuildHoverInitializationAudit(artifactDir)
				if err != nil {
					return err
				}
				audit["artifact_dir"] = artifactDir
				audits = append(audits, audit)
				if len(args) == 1 && output == "" {
					output = artifactlayout.Audit(artifactDir, "initialization_audit.json")
				}
			}
			var payload any
			if len(audits) == 1 {
				payload = audits[0]
			} else {
				payload = map[string]any{
					"schema":                    "navlab.hover_initialization_audit.comparison.v1",
					"diagnostic_only":           true,
					"runtime_control_unchanged": true,
					"runs":                      audits,
				}
			}
			return writeAuditJSON(output, payload)
		},
	}
	cmd.Flags().StringVar(&output, "output", "", "output JSON path; defaults to <artifact-dir>/audits/initialization_audit.json for one run, stdout for multiple")
	return cmd
}

func newAuditHoverGateReplayCommand(ctx *appContext) *cobra.Command {
	var output string
	cmd := &cobra.Command{
		Use:   "gate-replay <artifact-dir>",
		Short: "Replay hover result-gate evaluation from saved artifacts",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			artifactDir := args[0]
			payload, err := buildHoverGateReplay(ctx.loader(), artifactDir)
			if err != nil {
				return err
			}
			if output == "" {
				output = artifactlayout.Audit(artifactDir, "gate_replay.json")
			}
			return writeAuditJSON(output, payload)
		},
	}
	cmd.Flags().StringVar(&output, "output", "", "output JSON path; defaults to <artifact-dir>/audits/gate_replay.json")
	return cmd
}

func newFoxgloveCommand(ctx *appContext) *cobra.Command {
	cmd := &cobra.Command{
		Use:   "foxglove",
		Short: "Manage Foxglove replay and upload artifacts for sim runs",
	}
	cmd.AddCommand(newFoxgloveBuildReplayCommand(ctx), newFoxgloveUploadCommand(ctx))
	return cmd
}

func newFoxgloveBuildReplayCommand(ctx *appContext) *cobra.Command {
	var taskID string
	var mazePath string
	var profilePath string
	var resolutionM float64
	var dryRun bool
	cmd := &cobra.Command{
		Use:   "build-replay [run-id-or-artifact-dir]",
		Short: "Build a Foxglove-lite replay MCAP for a sim run",
		Args:  cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			run := ""
			if len(args) > 0 {
				run = args[0]
			}
			return foxgloveBuildReplay(ctx.loader(), ctx.artifactRoot, run, taskID, mazePath, profilePath, resolutionM, dryRun)
		},
	}
	cmd.Flags().StringVar(&taskID, "task", "", "sim task id used to resolve a run id under the sim artifact root")
	cmd.Flags().StringVar(&mazePath, "maze", "", "official maze.sdf path; defaults to ../ardupilot_gz/ardupilot_gz_gazebo/worlds/maze.sdf")
	cmd.Flags().StringVar(&profilePath, "profile", "", "Foxglove-lite topic profile path")
	cmd.Flags().Float64Var(&resolutionM, "resolution", 0, "official maze overlay resolution in meters")
	cmd.Flags().BoolVar(&dryRun, "dry-run", false, "write only the replay summary without generating an MCAP")
	return cmd
}

func newFoxgloveUploadCommand(ctx *appContext) *cobra.Command {
	var taskID string
	var dryRun bool
	var force bool
	var lite bool
	var keyPrefix string
	var apiURL string
	var deviceName string
	cmd := &cobra.Command{
		Use:   "upload [run-id-or-artifact-dir]",
		Short: "Upload a sim run MCAP and summaries to Foxglove",
		Args:  cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			run := ""
			if len(args) > 0 {
				run = args[0]
			}
			return foxgloveUpload(ctx.loader(), ctx.artifactRoot, run, taskID, dryRun, force, lite, keyPrefix, apiURL, deviceName)
		},
	}
	cmd.Flags().StringVar(&taskID, "task", "", "sim task id used to resolve a run id under the sim artifact root")
	cmd.Flags().BoolVar(&dryRun, "dry-run", false, "resolve upload targets without uploading")
	cmd.Flags().BoolVar(&force, "force", false, "perform the upload")
	cmd.Flags().BoolVar(&lite, "lite", false, "upload an existing rosbag_foxglove/rosbag_foxglove_0.mcap instead of the raw task MCAP")
	cmd.Flags().StringVar(&keyPrefix, "key-prefix", "", "Foxglove object key prefix")
	cmd.Flags().StringVar(&apiURL, "api-url", "", "Foxglove API URL")
	cmd.Flags().StringVar(&deviceName, "device-name", "", "Foxglove device name when FOXGLOVE_DEVICE_ID is not set")
	return cmd
}

type taskPlanFile struct {
	Plan tasks.Plan `json:"plan"`
}

type hoverGateReplayOutput struct {
	SchemaVersion  string               `json:"schemaVersion"`
	ArtifactDir    string               `json:"artifact_dir"`
	TaskID         string               `json:"task_id"`
	RunID          string               `json:"run_id"`
	GateEvaluation tasks.GateEvaluation `json:"gate_evaluation"`
}

func buildHoverGateReplay(loader config.Loader, artifactDir string) (hoverGateReplayOutput, error) {
	artifactDir = filepath.Clean(artifactDir)
	summary, err := readAuditJSON[tasks.LiveRunSummary](filepath.Join(artifactDir, "summary.json"))
	if err != nil {
		return hoverGateReplayOutput{}, err
	}
	taskPlan, err := readAuditJSON[taskPlanFile](filepath.Join(artifactDir, "task_plan.json"))
	if err != nil {
		return hoverGateReplayOutput{}, err
	}
	runtimeSpecs, err := readAuditJSON[tasks.RuntimeSpecBundle](filepath.Join(artifactDir, "runtime_plan.json"))
	if err != nil {
		return hoverGateReplayOutput{}, err
	}
	project, err := loader.LoadProject()
	if err != nil {
		return hoverGateReplayOutput{}, fmt.Errorf("load project config: %w", err)
	}
	taskConfig, err := loader.LoadTask(project, taskPlan.Plan.TaskID)
	if err != nil {
		return hoverGateReplayOutput{}, fmt.Errorf("load task config %q: %w", taskPlan.Plan.TaskID, err)
	}
	runtimeConfig, err := config.BuildTaskRuntimeConfig(project, taskConfig)
	if err != nil {
		return hoverGateReplayOutput{}, fmt.Errorf("build runtime config: %w", err)
	}
	runtimeConfig, err = tasks.ApplySimulationProfile(runtimeConfig, taskPlan.Plan)
	if err != nil {
		return hoverGateReplayOutput{}, fmt.Errorf("apply simulation profile: %w", err)
	}
	var executionErr error
	if summary.RuntimeError != "" {
		executionErr = errors.New(summary.RuntimeError)
	}
	return hoverGateReplayOutput{
		SchemaVersion: "navlab.orchestration.gate_replay.v1",
		ArtifactDir:   artifactDir,
		TaskID:        taskPlan.Plan.TaskID,
		RunID:         summary.RunID,
		GateEvaluation: tasks.EvaluateResultGates(
			project,
			runtimeConfig,
			taskPlan.Plan,
			artifactDir,
			runtimeSpecs,
			summary.RuntimeExecution,
			executionErr,
		),
	}, nil
}

func writeAuditJSON(outputPath string, payload any) error {
	data, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	if outputPath == "" {
		_, err = os.Stdout.Write(data)
		return err
	}
	if err := os.MkdirAll(filepath.Dir(outputPath), 0o755); err != nil {
		return err
	}
	if err := os.WriteFile(outputPath, data, 0o644); err != nil {
		return err
	}
	fmt.Println(outputPath)
	return nil
}

func readAuditJSON[T any](path string) (T, error) {
	var value T
	data, err := os.ReadFile(path)
	if err != nil {
		return value, fmt.Errorf("read %s: %w", path, err)
	}
	if err := json.Unmarshal(data, &value); err != nil {
		return value, fmt.Errorf("parse %s: %w", path, err)
	}
	return value, nil
}

func doctor(loader config.Loader) error {
	project, err := loader.LoadProject()
	if err != nil {
		return fmt.Errorf("config doctor failed: %w", err)
	}
	taskConfigs, err := loader.LoadTasks(project)
	if err != nil {
		return fmt.Errorf("task config doctor failed: %w", err)
	}
	configured, err := tasks.DefaultRegistry().Configure(taskConfigs)
	if err != nil {
		return fmt.Errorf("task registry doctor failed: %w", err)
	}
	fmt.Println(ui.Title("NavLab Sim Doctor"))
	fmt.Println(ui.StatusOK("config loaded"))
	fmt.Println(ui.StatusOK("task registry configured"))
	fmt.Println(ui.KeyValue("orchestration_family", project.Orchestration.Family))
	fmt.Println(ui.KeyValue("implementation", project.Orchestration.Implementation))
	fmt.Println(ui.KeyValue("runtime_mode", project.Runtime.Mode))
	fmt.Println(ui.KeyValue("backend", project.Runtime.Backend))
	fmt.Println(ui.KeyValue("task_config_format", "yaml"))
	fmt.Println(ui.KeyValue("task_count", len(configured)))
	return nil
}

func buildImages(loader config.Loader, kind string, image string, tag string, distro string, dryRun bool) error {
	project, err := loader.LoadProject()
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}
	if err := resolveWorkspaceRoot(loader, &project); err != nil {
		return fmt.Errorf("failed to resolve workspace root: %w", err)
	}
	result, err := simimages.Build(context.Background(), project, simimages.BuildOptions{
		Kind:   kind,
		Image:  image,
		Tag:    tag,
		Distro: distro,
		DryRun: dryRun,
		Stdout: os.Stdout,
		Stderr: os.Stderr,
	})
	if err != nil {
		return err
	}
	fmt.Println(ui.Title("NavLab Sim Image Build"))
	fmt.Println(ui.KeyValue("dry_run", result.DryRun))
	fmt.Println(ui.KeyValue("kind", kind))
	if image != "" {
		fmt.Println(ui.KeyValue("image_filter", image))
	}
	if tag != "" {
		fmt.Println(ui.KeyValue("tag_override", tag))
	}
	if distro != "" {
		fmt.Println(ui.KeyValue("distro_override", distro))
	}
	for _, spec := range result.Specs {
		fmt.Println(ui.Subtitle(spec.Kind))
		fmt.Println(ui.KeyValue("group", spec.Group))
		fmt.Println(ui.KeyValue("distro", spec.Distro))
		fmt.Println(ui.KeyValue("tag", spec.Tag))
		fmt.Println(ui.KeyValue("context", spec.Context))
		fmt.Println(ui.KeyValue("dockerfile", spec.Dockerfile))
		fmt.Println(ui.KeyValue("target", spec.Target))
		fmt.Println(ui.KeyValue("image", spec.Image))
		fmt.Println(ui.KeyValue("sdk_plan", spec.Command))
	}
	if !dryRun {
		fmt.Println(ui.StatusOK("NavLab image build completed"))
	}
	return nil
}

func foxgloveUpload(
	loader config.Loader,
	artifactRootOverride string,
	run string,
	taskID string,
	dryRun bool,
	force bool,
	lite bool,
	keyPrefix string,
	apiURL string,
	deviceName string,
) error {
	project, err := loader.LoadProject()
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}
	if err := resolveWorkspaceRoot(loader, &project); err != nil {
		return fmt.Errorf("failed to resolve workspace root: %w", err)
	}
	artifactRootPath := project.Paths.ArtifactRoot
	if artifactRootOverride != "" {
		artifactRootPath = artifactRootOverride
	}
	artifactRoot, err := loader.ResolveProjectPath(artifactRootPath)
	if err != nil {
		return fmt.Errorf("failed to resolve artifact root: %w", err)
	}
	if !filepath.IsAbs(artifactRoot) {
		artifactRoot, err = filepath.Abs(artifactRoot)
		if err != nil {
			return fmt.Errorf("failed to resolve artifact root: %w", err)
		}
	}
	result, err := simfoxglove.Upload(context.Background(), simfoxglove.Options{
		RepoRoot:     project.Paths.WorkspaceRoot,
		ArtifactRoot: artifactRoot,
		Run:          run,
		Task:         taskID,
		DryRun:       dryRun,
		Force:        force,
		Lite:         lite,
		APIURL:       apiURL,
		DeviceName:   deviceName,
		KeyPrefix:    keyPrefix,
		Stdout:       os.Stdout,
		Stderr:       os.Stderr,
	})
	if err != nil {
		return err
	}
	fmt.Println()
	fmt.Println(ui.Title("Foxglove Upload Result"))
	if result.State == "uploaded" {
		fmt.Println(ui.StatusOK("uploaded to Foxglove"))
	} else {
		fmt.Println(ui.KeyValue("state", result.State))
	}
	fmt.Println(ui.KeyValue("run_id", result.RunID))
	fmt.Println(ui.KeyValue("task_id", result.TaskID))
	fmt.Println(ui.KeyValue("mode", uploadModeLabel(result.Lite)))
	if len(result.Uploaded) > 0 {
		fmt.Println(ui.KeyValue("uploaded_files", len(result.Uploaded)))
	} else {
		fmt.Println(ui.KeyValue("target_files", len(result.Files)))
	}
	return nil
}

func uploadModeLabel(lite bool) string {
	if lite {
		return "lite"
	}
	return "raw"
}

func foxgloveBuildReplay(
	loader config.Loader,
	artifactRootOverride string,
	run string,
	taskID string,
	mazePath string,
	profilePath string,
	resolutionM float64,
	dryRun bool,
) error {
	project, err := loader.LoadProject()
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}
	if err := resolveWorkspaceRoot(loader, &project); err != nil {
		return fmt.Errorf("failed to resolve workspace root: %w", err)
	}
	artifactRootPath := project.Paths.ArtifactRoot
	if artifactRootOverride != "" {
		artifactRootPath = artifactRootOverride
	}
	artifactRoot, err := loader.ResolveProjectPath(artifactRootPath)
	if err != nil {
		return fmt.Errorf("failed to resolve artifact root: %w", err)
	}
	if !filepath.IsAbs(artifactRoot) {
		artifactRoot, err = filepath.Abs(artifactRoot)
		if err != nil {
			return fmt.Errorf("failed to resolve artifact root: %w", err)
		}
	}
	result, err := simfoxglove.BuildReplay(simfoxglove.ReplayOptions{
		RepoRoot:     project.Paths.WorkspaceRoot,
		ArtifactRoot: artifactRoot,
		Run:          run,
		Task:         taskID,
		MazePath:     mazePath,
		ProfilePath:  profilePath,
		ResolutionM:  resolutionM,
		DryRun:       dryRun,
		Stdout:       os.Stdout,
	})
	if err != nil {
		return err
	}
	fmt.Println(ui.Title("Foxglove Replay"))
	fmt.Println(ui.KeyValue("status", "ok"))
	fmt.Println(ui.KeyValue("run_id", result.RunID))
	fmt.Println(ui.KeyValue("task_id", result.TaskID))
	fmt.Println(ui.KeyValue("lite_mcap", result.ReplayMCAP))
	fmt.Println(ui.KeyValue("official_maze_topic", result.Overlay.Topic))
	return nil
}

func stage1Matrix(loader config.Loader, taskID string, summaryPaths []string, outputPath string) error {
	if len(summaryPaths) == 0 {
		return fmt.Errorf("at least one --summary path is required")
	}
	project, err := loader.LoadProject()
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}
	if err := resolveWorkspaceRoot(loader, &project); err != nil {
		return fmt.Errorf("failed to resolve workspace root: %w", err)
	}
	taskConfig, err := loader.LoadTask(project, taskID)
	if err != nil {
		return fmt.Errorf("failed to load task %q: %w", taskID, err)
	}
	runtimeConfig, err := config.BuildTaskRuntimeConfig(project, taskConfig)
	if err != nil {
		return fmt.Errorf("failed to build runtime config for %q: %w", taskID, err)
	}
	summaries := make([]tasks.LiveRunSummary, 0, len(summaryPaths))
	for _, path := range summaryPaths {
		resolvedPath, err := resolveProjectPath(loader, path)
		if err != nil {
			return fmt.Errorf("failed to resolve summary path %q: %w", path, err)
		}
		summary, err := tasks.ReadLiveRunSummary(resolvedPath)
		if err != nil {
			return fmt.Errorf("failed to read summary %q: %w", resolvedPath, err)
		}
		summaries = append(summaries, summary)
	}
	matrix := tasks.BuildStage1ProfileMatrix(taskID, tasks.RequiredStage1Profiles(taskID, runtimeConfig), summaries, time.Now())
	resolvedOutputPath, err := resolveProjectPath(loader, outputPath)
	if err != nil {
		return fmt.Errorf("failed to resolve output path %q: %w", outputPath, err)
	}
	if err := artifacts.WriteJSONArtifact(resolvedOutputPath, matrix); err != nil {
		return fmt.Errorf("failed to write Stage 1 profile matrix: %w", err)
	}

	fmt.Println(ui.Title("Stage 1 Profile Matrix"))
	fmt.Println(ui.KeyValue("task_id", taskID))
	fmt.Println(ui.KeyValue("output", resolvedOutputPath))
	fmt.Println(ui.KeyValue("required_profiles", matrix.RequiredProfiles))
	fmt.Println(ui.KeyValue("profiles", len(matrix.Profiles)))
	if matrix.OK {
		fmt.Println(ui.KeyValue("status", "ok"))
		return nil
	}
	fmt.Println(ui.KeyValue("status", "blocked"))
	fmt.Println(ui.KeyValue("blockers", matrix.Blockers))
	return fmt.Errorf("stage 1 profile matrix blocked: %s", strings.Join(matrix.Blockers, ", "))
}

func listTasks(loader config.Loader) error {
	project, err := loader.LoadProject()
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}
	taskConfigs, err := loader.LoadTasks(project)
	if err != nil {
		return fmt.Errorf("failed to load task configs: %w", err)
	}
	configured, err := tasks.DefaultRegistry().Configure(taskConfigs)
	if err != nil {
		return fmt.Errorf("failed to configure task registry: %w", err)
	}
	fmt.Println(ui.Title("Simulation Tasks"))
	for _, task := range configured {
		fmt.Printf("%s\t%s\t%s\n", ui.TaskID(task.Config.ID), task.Config.Family, task.Config.Description)
	}
	return nil
}

func listHelpers(registry *helpers.Registry) error {
	fmt.Println(ui.Title("Simulation Helper Inventory"))
	for _, helper := range registry.List() {
		status := helper.MigrationStatus
		if helper.RuntimeAction {
			status += ",runtime"
		}
		fmt.Printf("%s\t%s\t%s\n", ui.TaskID(helper.ID), helper.Phase, status)
	}
	return nil
}

func showTask(loader config.Loader, taskID string) error {
	project, err := loader.LoadProject()
	if err != nil {
		return fmt.Errorf("failed to load config: %w", err)
	}
	task, err := loader.LoadTask(project, taskID)
	if err != nil {
		return fmt.Errorf("failed to load task %q: %w", taskID, err)
	}
	configured, err := tasks.DefaultRegistry().ConfigureOne(task)
	if err != nil {
		return fmt.Errorf("failed to configure task %q: %w", taskID, err)
	}
	fmt.Println(ui.Title("Simulation Task"))
	fmt.Println(ui.KeyValue("id", configured.Config.ID))
	fmt.Println(ui.KeyValue("family", configured.Config.Family))
	fmt.Println(ui.KeyValue("description", configured.Config.Description))
	fmt.Println(ui.KeyValue("duration_sec", fmt.Sprintf("%.3f", configured.Config.Task.DurationSec)))
	fmt.Println(ui.KeyValue("simulation_profile", configured.Config.Task.SimulationProfile))
	fmt.Println(ui.KeyValue("capabilities", configured.Config.Capabilities))
	helperDefinitions, err := helpers.DefaultRegistry().Resolve(configured.Definition.HelperIDs)
	if err != nil {
		return fmt.Errorf("failed to resolve helpers for task %q: %w", taskID, err)
	}
	fmt.Println(ui.KeyValue("plan_steps", configured.Definition.Steps))
	fmt.Println(ui.Subtitle("Helpers"))
	for _, helper := range helperDefinitions {
		fmt.Printf("%s\t%s\t%s\n", ui.TaskID(helper.ID), helper.Phase, helper.Role)
	}
	return nil
}

func runTask(
	loader config.Loader,
	registry *tasks.Registry,
	helperRegistry *helpers.Registry,
	taskID string,
	dryRun bool,
	tuiMode bool,
	livePreflight bool,
	artifactRootOverride string,
	options tasks.PlanOptions,
) error {
	if tuiMode {
		if err := simtui.EnsureInteractiveTerminal(); err != nil {
			return err
		}
	}
	prepared, err := prepareTaskRun(loader, registry, helperRegistry, taskID, dryRun, artifactRootOverride, options, !dryRun || livePreflight)
	if err != nil {
		return err
	}
	if prepared.WorkflowBundle.DoctorResult.Blocked && !dryRun {
		return fmt.Errorf("sim workflow blocked before runtime-execute: %s", strings.Join(prepared.WorkflowBundle.DoctorResult.Blockers, "; "))
	}
	if !dryRun {
		if tuiMode {
			return simtui.RunLive(prepared.Result.ArtifactDir, func(sink tasks.RuntimeEventSink) error {
				return runLiveTask(prepared.Project, prepared.TaskRuntimeConfig, prepared.Plan, prepared.Result, prepared.GeneratedArtifacts, prepared.RuntimeSpecs, prepared.WorkflowBundle, sink, false)
			}, simtui.RunOptions{RequireTTY: false})
		}
		return runLiveTask(prepared.Project, prepared.TaskRuntimeConfig, prepared.Plan, prepared.Result, prepared.GeneratedArtifacts, prepared.RuntimeSpecs, prepared.WorkflowBundle, nil, true)
	}
	if tuiMode {
		return simtui.RunReplay(prepared.Result.ArtifactDir, simtui.RunOptions{RequireTTY: true})
	}
	fmt.Println(ui.Title("Simulation Task Plan"))
	fmt.Println(ui.KeyValue("dry_run", true))
	fmt.Println(ui.KeyValue("run_id", prepared.Result.RunID))
	fmt.Println(ui.KeyValue("id", prepared.Plan.TaskID))
	fmt.Println(ui.KeyValue("description", prepared.Plan.Description))
	fmt.Println(ui.KeyValue("duration_sec", fmt.Sprintf("%.3f", prepared.Plan.DurationSec)))
	fmt.Println(ui.KeyValue("task_deadline_sec", fmt.Sprintf("%.3f", prepared.Plan.DurationSec)))
	fmt.Println(ui.KeyValue("rosbag_post_task_grace_sec", fmt.Sprintf("%.3f", tasks.DefaultRosbagPostTaskGraceSec)))
	fmt.Println(ui.KeyValue("simulation_profile", prepared.Plan.SimulationProfile))
	if isHoverTaskID(prepared.Plan.TaskID) {
		fmt.Println(ui.KeyValue("hover_span_target_m", fmt.Sprintf("%.3f", prepared.TaskRuntimeConfig.SlamHover.HoverSpanTargetM)))
		fmt.Println(ui.KeyValue("hover_span_hard_cap_m", fmt.Sprintf("%.3f", prepared.TaskRuntimeConfig.SlamHover.HoverSpanHardCapM)))
		policy := prepared.TaskRuntimeConfig.SlamHover.StartupReadinessPolicy
		fmt.Println(ui.KeyValue("startup_readiness_policy", fmt.Sprintf("timeout=%.1fs grace=%.1fs progress_window=%.1fs restart_limit=%d", policy.TimeoutSec, policy.GraceSec, policy.ProgressWindowSec, policy.RestartLimit)))
	}
	fmt.Println(ui.KeyValue("capabilities", prepared.Plan.Capabilities))
	fmt.Println(ui.KeyValue("artifact_dir", prepared.Result.ArtifactDir))
	fmt.Println(ui.KeyValue("task_plan", prepared.Result.PlanPath))
	fmt.Println(ui.KeyValue("manifest", prepared.Result.ManifestPath))
	fmt.Println(ui.KeyValue("generated_runtime_artifacts", len(prepared.GeneratedArtifacts)))
	fmt.Println(ui.KeyValue("runtime_services", len(prepared.RuntimeSpecs.Services)))
	fmt.Println(ui.KeyValue("runtime_probes", len(prepared.RuntimeSpecs.Probes)))
	fmt.Println(ui.KeyValue("runtime_rosbags", len(prepared.RuntimeSpecs.Rosbags)))
	fmt.Println(ui.Subtitle("Workflow Nodes"))
	for _, node := range prepared.WorkflowBundle.Workflow.Nodes {
		fmt.Printf("%s %s\n", ui.TaskID(node.ID), node.Status)
	}
	fmt.Println(ui.Subtitle("Helpers"))
	for _, helper := range prepared.Plan.Helpers {
		status := helper.MigrationStatus
		if helper.RuntimeAction {
			status += ",runtime"
		}
		fmt.Printf("%s %s %s\n", ui.TaskID(helper.ID), ui.Muted(helper.Phase), status)
	}
	fmt.Println(ui.Subtitle("Steps"))
	for index, step := range prepared.Plan.Steps {
		fmt.Printf("%s %s\n", ui.StepNumber(index+1), step)
	}
	return nil
}

func isHoverTaskID(taskID string) bool {
	return taskID == "hover" || taskID == "hover-slam-only"
}

func doctorTask(
	loader config.Loader,
	registry *tasks.Registry,
	helperRegistry *helpers.Registry,
	taskID string,
	artifactRootOverride string,
) error {
	prepared, err := prepareTaskRun(loader, registry, helperRegistry, taskID, true, artifactRootOverride, tasks.PlanOptions{}, false)
	if err != nil {
		return err
	}
	summary := tasks.BuildStaticDoctorSummary(prepared.Project, prepared.Plan, prepared.Result.RunID, prepared.Result.ArtifactDir, prepared.GeneratedArtifacts, prepared.RuntimeSpecs)
	summaryPath := filepath.Join(prepared.Result.ArtifactDir, "doctor_summary.json")
	if err := artifacts.WriteJSONArtifact(summaryPath, summary); err != nil {
		return fmt.Errorf("failed to write %s doctor summary: %w", taskID, err)
	}
	if err := artifacts.AppendManifestArtifacts(prepared.Result.ManifestPath, prepared.Result.ArtifactDir, []artifacts.GeneratedArtifact{
		{Type: "doctor_summary", Path: summaryPath},
	}); err != nil {
		return fmt.Errorf("failed to update %s doctor manifest: %w", taskID, err)
	}
	fmt.Println(ui.Title("Simulation Task Doctor"))
	fmt.Println(ui.KeyValue("id", taskID))
	fmt.Println(ui.KeyValue("status", "ok"))
	fmt.Println(ui.KeyValue("summary", summaryPath))
	fmt.Println(ui.KeyValue("generated_runtime_artifacts", len(prepared.GeneratedArtifacts)))
	fmt.Println(ui.KeyValue("runtime_services", len(prepared.RuntimeSpecs.Services)))
	fmt.Println(ui.KeyValue("runtime_probes", len(prepared.RuntimeSpecs.Probes)))
	fmt.Println(ui.KeyValue("runtime_rosbags", len(prepared.RuntimeSpecs.Rosbags)))
	return nil
}

func prepareTaskRun(
	loader config.Loader,
	registry *tasks.Registry,
	helperRegistry *helpers.Registry,
	taskID string,
	dryRun bool,
	artifactRootOverride string,
	options tasks.PlanOptions,
	liveResourceCheck bool,
) (preparedTaskRun, error) {
	project, err := loader.LoadProject()
	if err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to load config: %w", err)
	}
	if err := resolveWorkspaceRoot(loader, &project); err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to resolve workspace root: %w", err)
	}
	taskConfig, err := loader.LoadTask(project, taskID)
	if err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to load task %q: %w", taskID, err)
	}
	task, err := registry.ConfigureOne(taskConfig)
	if err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to configure task %q: %w", taskID, err)
	}
	plan, err := task.Plan(options, helperRegistry)
	if err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to build task plan for %q: %w", taskID, err)
	}
	taskRuntimeConfig, err := config.BuildTaskRuntimeConfig(project, taskConfig)
	if err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to build runtime config for %q: %w", taskID, err)
	}
	taskRuntimeConfig, err = tasks.ApplySimulationProfile(taskRuntimeConfig, plan)
	if err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to apply simulation profile for %q: %w", taskID, err)
	}
	taskRuntimeConfig, err = tasks.ApplyHoverSLOPolicy(taskRuntimeConfig, plan)
	if err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to apply hover SLO policy for %q: %w", taskID, err)
	}
	plan.Execution.TaskParameters["runtime_config"] = taskRuntimeConfig
	artifactRootPath := project.Paths.ArtifactRoot
	if artifactRootOverride != "" {
		artifactRootPath = artifactRootOverride
	}
	artifactRoot, err := loader.ResolveProjectPath(artifactRootPath)
	if err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to resolve artifact root: %w", err)
	}
	result, err := artifacts.NewWriter(artifactRoot).WriteRunPlan(project, plan, time.Now(), artifacts.RunPlanOptions{DryRun: dryRun})
	if err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to write run artifacts: %w", err)
	}
	generatedArtifacts, err := tasks.GenerateRuntimeArtifacts(project, plan, taskRuntimeConfig, result.ArtifactDir)
	if err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to generate runtime artifacts for %q: %w", taskID, err)
	}
	if err := artifacts.AppendManifestArtifacts(result.ManifestPath, result.ArtifactDir, manifestArtifacts(generatedArtifacts)); err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to update run manifest for %q: %w", taskID, err)
	}
	runtimeSpecs, err := tasks.BuildRuntimeSpecs(project, plan.Execution, result.ArtifactDir)
	if err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to validate runtime specs for %q: %w", taskID, err)
	}
	runtimePlan, err := tasks.BuildRuntimePlanContract(plan, result.RunID, runtimeSpecs)
	if err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to build runtime plan contract for %q: %w", taskID, err)
	}
	runtimePlanPath := filepath.Join(result.ArtifactDir, "runtime_plan.json")
	if err := artifacts.WriteJSONArtifact(runtimePlanPath, runtimePlan); err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to write runtime plan contract for %q: %w", taskID, err)
	}
	if err := artifacts.AppendManifestArtifacts(result.ManifestPath, result.ArtifactDir, []artifacts.GeneratedArtifact{
		{Type: "runtime_plan", Path: runtimePlanPath},
	}); err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to update runtime plan manifest for %q: %w", taskID, err)
	}
	_, plannedTaskFSMArtifact, err := tasks.WritePlannedTaskFSMArtifact(result.ArtifactDir, plan.TaskID, result.RunID)
	if err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to write planned task FSM artifact for %q: %w", taskID, err)
	}
	generatedArtifacts = append(generatedArtifacts, plannedTaskFSMArtifact)
	if err := artifacts.AppendManifestArtifacts(result.ManifestPath, result.ArtifactDir, []artifacts.GeneratedArtifact{
		{Type: plannedTaskFSMArtifact.Type, Path: plannedTaskFSMArtifact.Path},
	}); err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to update planned task FSM manifest for %q: %w", taskID, err)
	}
	workflowBundle := tasks.BuildSimWorkflowBundleWithOptions(
		project,
		taskConfig,
		taskRuntimeConfig,
		plan,
		result.RunID,
		artifactRoot,
		result.ArtifactDir,
		generatedArtifacts,
		runtimeSpecs,
		runtimePlanPath,
		tasks.SimWorkflowOptions{LiveResourceCheck: liveResourceCheck},
	)
	if err := writeSimWorkflowArtifacts(result.ManifestPath, result.ArtifactDir, workflowBundle); err != nil {
		return preparedTaskRun{}, fmt.Errorf("failed to write sim workflow artifacts for %q: %w", taskID, err)
	}
	return preparedTaskRun{
		Project:            project,
		TaskConfig:         taskConfig,
		TaskRuntimeConfig:  taskRuntimeConfig,
		Plan:               plan,
		Result:             result,
		GeneratedArtifacts: generatedArtifacts,
		RuntimeSpecs:       runtimeSpecs,
		WorkflowBundle:     workflowBundle,
	}, nil
}

func writeSimWorkflowArtifacts(manifestPath string, artifactDir string, bundle tasks.SimWorkflowBundle) error {
	entries := []struct {
		artifactType string
		fileName     string
		value        any
	}{
		{artifactType: "preflight_summary", fileName: "preflight_summary.json", value: bundle.Preflight},
		{artifactType: "prepare_summary", fileName: "prepare_summary.json", value: bundle.Prepare},
		{artifactType: "common_doctor_summary", fileName: "common_doctor_summary.json", value: bundle.CommonDoctor},
		{artifactType: "task_doctor_summary", fileName: "task_doctor_summary.json", value: bundle.TaskDoctor},
		{artifactType: "workflow_summary", fileName: "workflow_summary.json", value: bundle.Workflow},
		{artifactType: "doctor_result", fileName: "doctor_result.json", value: bundle.DoctorResult},
	}
	generated := make([]artifacts.GeneratedArtifact, 0, len(entries))
	for _, entry := range entries {
		path := artifactlayout.DAG(artifactDir, entry.fileName)
		if err := artifacts.WriteJSONArtifact(path, entry.value); err != nil {
			return err
		}
		generated = append(generated, artifacts.GeneratedArtifact{Type: entry.artifactType, Path: path})
	}
	return artifacts.AppendManifestArtifacts(manifestPath, artifactDir, generated)
}

func writeSimWorkflowResultArtifacts(artifactDir string, workflow tasks.SimWorkflowSummary, doctorResult tasks.SimDoctorResult) error {
	if err := artifacts.WriteJSONArtifact(artifactlayout.DAG(artifactDir, "workflow_summary.json"), workflow); err != nil {
		return err
	}
	if err := artifacts.WriteJSONArtifact(artifactlayout.DAG(artifactDir, "doctor_result.json"), doctorResult); err != nil {
		return err
	}
	return nil
}

func runLiveTask(
	project config.ProjectConfig,
	taskRuntimeConfig config.TaskRuntimeConfig,
	plan tasks.Plan,
	result artifacts.DryRunResult,
	generatedArtifacts []tasks.GeneratedRuntimeArtifact,
	runtimeSpecs tasks.RuntimeSpecBundle,
	workflowBundle tasks.SimWorkflowBundle,
	eventSink tasks.RuntimeEventSink,
	printSummary bool,
) error {
	execution, executionErr := tasks.ExecuteRuntimeSpecs(
		simruntime.NewDockerBackend(nil),
		runtimeSpecs,
		tasks.RuntimeExecutionOptions{
			WaitForRosbags:         true,
			RosbagPostTaskGraceSec: tasks.DefaultRosbagPostTaskGraceSec,
			TaskDeadlineSec:        plan.DurationSec,
			TaskID:                 plan.TaskID,
			RunID:                  result.RunID,
			ArtifactDir:            result.ArtifactDir,
			StartupReadinessPolicy: taskRuntimeConfig.SlamHover.StartupReadinessPolicy,
			EventSink:              eventSink,
		},
	)
	summary := tasks.BuildLiveRunSummary(project, taskRuntimeConfig, plan, result.RunID, result.ArtifactDir, generatedArtifacts, runtimeSpecs, execution, executionErr)
	runtimeFSMRefs, runtimeFSMArtifacts, err := tasks.WriteRosbagRecorderFSMArtifacts(result.ArtifactDir, plan.TaskID, result.RunID, execution, summary.GateEvaluation)
	if err != nil {
		return fmt.Errorf("failed to write runtime FSM artifacts for %q: %w", plan.TaskID, err)
	}
	taskFSMRef, taskFSMArtifact, err := tasks.WriteTaskFSMArtifact(result.ArtifactDir, plan.TaskID, result.RunID, summary.GateEvaluation, executionErr, runtimeFSMRefs)
	if err != nil {
		return fmt.Errorf("failed to write task FSM artifact for %q: %w", plan.TaskID, err)
	}
	summary.FSMArtifacts = append([]tasks.FSMArtifactRef{taskFSMRef}, runtimeFSMRefs...)
	summary.GateEvaluation.FSMArtifacts = append([]tasks.FSMArtifactRef(nil), summary.FSMArtifacts...)
	tasks.AttachRuntimeHoverHealthFromMissionSummary(&summary)
	summaryPath := filepath.Join(result.ArtifactDir, "summary.json")
	summary.SummaryPath = summaryPath
	summary.Stage1ProfileResult = tasks.Stage1ProfileResultFromSummary(summary)
	if err := artifacts.WriteJSONArtifact(summaryPath, summary); err != nil {
		return fmt.Errorf("failed to write live summary for %q: %w", plan.TaskID, err)
	}
	manifestEntries := []artifacts.GeneratedArtifact{
		{Type: "summary", Path: summaryPath},
	}
	for _, artifact := range runtimeFSMArtifacts {
		manifestEntries = append(manifestEntries, artifacts.GeneratedArtifact{Type: artifact.Type, Path: artifact.Path})
	}
	manifestEntries = append(manifestEntries, artifacts.GeneratedArtifact{Type: taskFSMArtifact.Type, Path: taskFSMArtifact.Path})
	liveCommonDoctor := tasks.BuildSimLiveCommonDoctorSummary(project, plan, result.RunID, runtimeSpecs, execution, executionErr, runtimeFSMRefs...)
	liveCommonDoctorPath := artifactlayout.DAG(result.ArtifactDir, "common_doctor_live_summary.json")
	if err := artifacts.WriteJSONArtifact(liveCommonDoctorPath, liveCommonDoctor); err != nil {
		return fmt.Errorf("failed to write live common doctor summary for %q: %w", plan.TaskID, err)
	}
	manifestEntries = append(manifestEntries, artifacts.GeneratedArtifact{Type: "common_doctor_live_summary", Path: liveCommonDoctorPath})
	if plan.TaskID == "hover" {
		if health, healthPath, err := tasks.BuildAndWriteHoverHealthSummaryArtifact(result.ArtifactDir); err != nil {
			summary.Warnings = append(summary.Warnings, "hover_health_audit_failed:"+err.Error())
			if rewriteErr := artifacts.WriteJSONArtifact(summaryPath, summary); rewriteErr != nil {
				return fmt.Errorf("failed to rewrite live summary after hover health warning for %q: %w", plan.TaskID, rewriteErr)
			}
		} else {
			tasks.AttachHoverHealthToLiveRunSummary(&summary, health)
			summary.Stage1ProfileResult = tasks.Stage1ProfileResultFromSummary(summary)
			if err := artifacts.WriteJSONArtifact(summaryPath, summary); err != nil {
				return fmt.Errorf("failed to rewrite live summary with hover health for %q: %w", plan.TaskID, err)
			}
			manifestEntries = append(manifestEntries, artifacts.GeneratedArtifact{Type: "hover_health_summary", Path: healthPath})
		}
	}
	liveWorkflow := tasks.BuildSimLiveWorkflowSummary(workflowBundle.Workflow, summary)
	liveDoctorResult := tasks.BuildSimDoctorResult(plan.TaskID, result.RunID, liveWorkflow.Nodes)
	if err := writeSimWorkflowResultArtifacts(result.ArtifactDir, liveWorkflow, liveDoctorResult); err != nil {
		return fmt.Errorf("failed to rewrite live workflow artifacts for %q: %w", plan.TaskID, err)
	}
	emitTaskEvent(eventSink, plan.TaskID, result.RunID, tasks.RuntimeEvent{
		Phase:    "summary.written",
		Level:    "info",
		Message:  "summary written",
		Artifact: summaryPath,
	})
	finalArtifacts, err := artifacts.FinalizeRunArtifacts(project, plan, result, stageLabel(plan.TaskID), controlMode(plan.TaskID, plan.SimulationProfile))
	if err != nil {
		return fmt.Errorf("failed to finalize live artifacts for %q: %w", plan.TaskID, err)
	}
	manifestEntries = append(manifestEntries, finalArtifacts...)
	if err := artifacts.AppendManifestArtifacts(result.ManifestPath, result.ArtifactDir, manifestEntries); err != nil {
		return fmt.Errorf("failed to update live manifest for %q: %w", plan.TaskID, err)
	}
	if summary.OK {
		emitTaskEvent(eventSink, plan.TaskID, result.RunID, tasks.RuntimeEvent{Phase: "run.completed", Level: "info", Message: "task completed"})
	} else {
		emitTaskEvent(eventSink, plan.TaskID, result.RunID, tasks.RuntimeEvent{Phase: "run.blocked", Level: "error", Message: "task blocked"})
	}
	if !printSummary {
		if !summary.OK {
			if executionErr != nil {
				return fmt.Errorf("task %q live run failed; summary: %s: %w", plan.TaskID, summaryPath, executionErr)
			}
			return fmt.Errorf("task %q live run blocked; summary: %s", plan.TaskID, summaryPath)
		}
		return nil
	}
	fmt.Println(ui.Title("Simulation Task Run"))
	fmt.Println(ui.KeyValue("dry_run", false))
	fmt.Println(ui.KeyValue("run_id", result.RunID))
	fmt.Println(ui.KeyValue("id", plan.TaskID))
	fmt.Println(ui.KeyValue("summary", summaryPath))
	fmt.Println(ui.KeyValue("artifact_dir", result.ArtifactDir))
	fmt.Println(ui.KeyValue("runtime_services", len(runtimeSpecs.Services)))
	fmt.Println(ui.KeyValue("runtime_probes", len(runtimeSpecs.Probes)))
	fmt.Println(ui.KeyValue("runtime_rosbags", len(runtimeSpecs.Rosbags)))
	if !summary.OK {
		fmt.Println(ui.KeyValue("status", "blocked"))
		if executionErr != nil {
			return fmt.Errorf("task %q live run failed; summary: %s: %w", plan.TaskID, summaryPath, executionErr)
		}
		return fmt.Errorf("task %q live run blocked; summary: %s", plan.TaskID, summaryPath)
	}
	fmt.Println(ui.KeyValue("status", "ok"))
	return nil
}

func emitTaskEvent(sink tasks.RuntimeEventSink, taskID string, runID string, event tasks.RuntimeEvent) {
	if sink == nil {
		return
	}
	event.Time = time.Now().UTC()
	event.TaskID = taskID
	event.RunID = runID
	sink.EmitRuntimeEvent(event)
}

func stageLabel(taskID string) string {
	switch taskID {
	case "hover":
		return "Go sim FCU/SLAM hover + landing acceptance"
	case "exploration":
		return "Go sim official-maze exploration acceptance"
	case "scan-robustness":
		return "Go sim scan robustness acceptance"
	default:
		return "Go sim task acceptance"
	}
}

func controlMode(taskID string, profile string) string {
	if profile == "" {
		profile = "default"
	}
	return taskID + "_" + profile
}

func resolveWorkspaceRoot(loader config.Loader, project *config.ProjectConfig) error {
	if project.Paths.WorkspaceRoot == "" {
		return nil
	}
	resolved, err := loader.ResolveProjectPath(project.Paths.WorkspaceRoot)
	if err != nil {
		return err
	}
	project.Paths.WorkspaceRoot = resolved
	return nil
}

func resolveProjectPath(loader config.Loader, path string) (string, error) {
	if filepath.IsAbs(path) {
		return path, nil
	}
	return loader.ResolveProjectPath(path)
}

func manifestArtifacts(generated []tasks.GeneratedRuntimeArtifact) []artifacts.GeneratedArtifact {
	converted := make([]artifacts.GeneratedArtifact, 0, len(generated))
	for _, artifact := range generated {
		converted = append(converted, artifacts.GeneratedArtifact{
			Type: artifact.Type,
			Path: artifact.Path,
		})
	}
	return converted
}
