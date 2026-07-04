use std::path::PathBuf;

use anyhow::{Result, bail};
use clap::{Args, Parser, Subcommand};
use tracing::{info, instrument};

use crate::config::Loader;
use crate::errors::RealOrchestrationError;
use crate::logging::{LogFormat, LogRotation, LoggingConfig, init_logging};
use crate::tasks::{MotorDebugOverrides, OperatorConfirmations, Registry};
use crate::ui::{print_key_value, print_status, print_title};
use crate::workflows::{
    CommonDoctorInput, DoctorChainInput, HostEnvironmentProbe, HostTopicProbe, PrepareInput,
    TaskDoctorInput, run_common_doctor, run_doctor_chain, run_preflight, run_prepare,
    run_task_doctor,
};

const DEFAULT_CONFIG_PATH: &str = "config.toml";

#[derive(Debug, Parser)]
#[command(name = "navlab-real")]
#[command(about = "NavLab real-machine orchestration control plane")]
pub struct Cli {
    #[arg(long, default_value = DEFAULT_CONFIG_PATH)]
    pub config: PathBuf,

    #[arg(long, default_value = "info")]
    pub log_level: String,

    #[arg(long, value_enum, default_value_t = LogFormat::Human)]
    pub log_format: LogFormat,

    #[arg(long)]
    pub log_file: bool,

    #[arg(long, default_value = "logs/real")]
    pub log_dir: PathBuf,

    #[arg(long, value_enum, default_value_t = LogRotation::Daily)]
    pub log_rotation: LogRotation,

    #[command(subcommand)]
    pub command: Command,
}

#[derive(Debug, Subcommand)]
pub enum Command {
    Doctor,
    Preflight(PreflightCommand),
    Prepare(PrepareCommand),
    CommonDoctor(CommonDoctorCommand),
    TaskDoctor(TaskDoctorCommand),
    DoctorChain(DoctorChainCommand),
    ListTasks,
    ShowTask { task_id: String },
    Run(RunCommand),
}

#[derive(Debug, Args)]
pub struct PreflightCommand {
    #[arg(long)]
    pub summary_path: Option<PathBuf>,
}

#[derive(Debug, Args)]
pub struct PrepareCommand {
    pub task_id: String,

    #[arg(long)]
    pub dry_run: bool,

    #[arg(long)]
    pub allow_live: bool,

    #[arg(long)]
    pub summary_path: Option<PathBuf>,
}

#[derive(Debug, Args)]
pub struct CommonDoctorCommand {
    pub task_id: String,

    #[arg(long)]
    pub upstream_json: Option<PathBuf>,

    #[arg(long)]
    pub summary_path: Option<PathBuf>,

    #[arg(long)]
    pub upstream_output: Option<PathBuf>,
}

#[derive(Debug, Args)]
pub struct TaskDoctorCommand {
    pub task_id: String,

    #[arg(long)]
    pub upstream_json: Option<PathBuf>,

    #[arg(long)]
    pub summary_path: Option<PathBuf>,
}

#[derive(Debug, Args)]
pub struct DoctorChainCommand {
    pub task_id: String,

    #[arg(long)]
    pub prepare_dry_run: bool,

    #[arg(long)]
    pub allow_live_prepare: bool,

    #[arg(long)]
    pub upstream_json: Option<PathBuf>,

    #[arg(long)]
    pub artifact_dir: Option<PathBuf>,

    #[arg(long)]
    pub summary_path: Option<PathBuf>,
}

#[derive(Debug, Args)]
pub struct RunCommand {
    pub task_id: String,

    #[arg(long)]
    pub dry_run: bool,

    #[arg(long)]
    pub with_doctor_chain: bool,

    #[arg(long)]
    pub allow_live_prepare: bool,

    #[arg(long)]
    pub upstream_json: Option<PathBuf>,

    #[arg(long)]
    pub doctor_artifact_dir: Option<PathBuf>,

    #[arg(long)]
    pub artifact_dir: Option<PathBuf>,

    #[arg(long)]
    pub summary_path: Option<PathBuf>,

    #[arg(long)]
    pub confirm_manual_takeover: bool,

    #[arg(long)]
    pub confirm_kill_switch: bool,

    #[arg(long)]
    pub confirm_safe_area: bool,

    #[arg(long)]
    pub confirm_no_props: bool,

    #[arg(long)]
    pub confirm_props_installed: bool,

    #[arg(long)]
    pub task_config: Option<PathBuf>,

    #[arg(long)]
    pub motor_percent: Option<f64>,

    #[arg(long)]
    pub motor_sec: Option<f64>,

    #[arg(long)]
    pub motor_count: Option<u32>,
}

pub async fn run(cli: Cli) -> Result<()> {
    init_logging(LoggingConfig {
        level: cli.log_level.clone(),
        format: cli.log_format,
        file_enabled: cli.log_file,
        directory: cli.log_dir.clone(),
        rotation: cli.log_rotation,
        file_prefix: "navlab-real.log".to_string(),
    })?;
    info!(
        config = %cli.config.display(),
        command = ?cli.command,
        "starting real orchestration command"
    );
    dispatch(cli).await
}

#[instrument(skip(cli))]
async fn dispatch(cli: Cli) -> Result<()> {
    let loader = Loader::new(cli.config);
    let registry = Registry::default();
    match cli.command {
        Command::Doctor => doctor(&loader, &registry),
        Command::Preflight(command) => preflight(&loader, command),
        Command::Prepare(command) => prepare(&loader, &registry, command),
        Command::CommonDoctor(command) => common_doctor(&loader, &registry, command),
        Command::TaskDoctor(command) => task_doctor(&loader, &registry, command),
        Command::DoctorChain(command) => doctor_chain(&loader, &registry, command),
        Command::ListTasks => list_tasks(&loader, &registry),
        Command::ShowTask { task_id } => show_task(&loader, &registry, &task_id),
        Command::Run(command) => run_task(&loader, &registry, command).await,
    }
}

fn doctor(loader: &Loader, registry: &Registry) -> Result<()> {
    let project = loader.load_project()?;
    let task_configs = loader.load_tasks(&project)?;
    let configured = registry.configure(&task_configs)?;
    let mut blockers = Vec::new();
    if project.orchestration.family != "real" {
        blockers.push(format!(
            "orchestration_family_must_be_real:{}",
            project.orchestration.family
        ));
    }
    if project.orchestration.implementation != "rust" {
        blockers.push(format!(
            "orchestration_implementation_must_be_rust:{}",
            project.orchestration.implementation
        ));
    }
    if project.runtime.mode != "real" {
        blockers.push(format!(
            "runtime_mode_must_be_real:{}",
            project.runtime.mode
        ));
    }
    if project.runtime.backend != "process" {
        blockers.push(format!(
            "runtime_backend_must_be_process:{}",
            project.runtime.backend
        ));
    }

    print_title("NavLab Real Doctor");
    print_status("config loaded", blockers.is_empty());
    print_key_value("orchestration_family", &project.orchestration.family);
    print_key_value("implementation", &project.orchestration.implementation);
    print_key_value("runtime_mode", &project.runtime.mode);
    print_key_value("backend", &project.runtime.backend);
    print_key_value("task_count", &configured.len().to_string());
    if blockers.is_empty() {
        Ok(())
    } else {
        bail!("real doctor blocked: {}", blockers.join(", "))
    }
}

fn preflight(loader: &Loader, command: PreflightCommand) -> Result<()> {
    let project = loader.load_project()?;
    let environment = HostEnvironmentProbe;
    let summary = run_preflight(&project, &environment, command.summary_path.as_deref())?;
    print_title("NavLab Real Preflight");
    print_status("preflight", summary.ok);
    print_key_value("runtime_mode", &summary.runtime_mode);
    print_key_value("backend", &summary.runtime_backend);
    print_key_value("ros_distro", &summary.ros_distro);
    print_key_value("blockers", &summary.blockers.len().to_string());
    if summary.ok {
        Ok(())
    } else {
        bail!("real preflight blocked: {}", summary.blockers.join(", "))
    }
}

fn prepare(loader: &Loader, registry: &Registry, command: PrepareCommand) -> Result<()> {
    let project = loader.load_project()?;
    let task_config = loader.load_task(&project, &command.task_id, None)?;
    if registry.create(&command.task_id).is_none() {
        return Err(RealOrchestrationError::UnknownTask(command.task_id).into());
    }
    let summary = run_prepare(
        &project,
        &task_config,
        PrepareInput {
            dry_run: if command.dry_run { Some(true) } else { None },
            allow_live: command.allow_live,
            summary_path: command.summary_path,
        },
    )?;
    print_title("NavLab Real Prepare");
    print_status("prepare", summary.ok);
    print_key_value("task", &summary.task_name);
    print_key_value("claim", &summary.prepare_claim);
    print_key_value("dry_run", &summary.dry_run.to_string());
    print_key_value("fcu_bridge_mode", &summary.fcu_bridge_mode.name);
    print_key_value("service_count", &summary.service_count.to_string());
    print_key_value("blockers", &summary.blockers.len().to_string());
    if summary.ok {
        Ok(())
    } else {
        bail!("real prepare blocked: {}", summary.blockers.join(", "))
    }
}

fn common_doctor(loader: &Loader, registry: &Registry, command: CommonDoctorCommand) -> Result<()> {
    let project = loader.load_project()?;
    let task_config = loader.load_task(&project, &command.task_id, None)?;
    if registry.create(&command.task_id).is_none() {
        return Err(RealOrchestrationError::UnknownTask(command.task_id).into());
    }
    let input = CommonDoctorInput {
        upstream_json: command.upstream_json,
        summary_path: command.summary_path,
        upstream_output: command.upstream_output,
    };
    let probe = HostTopicProbe;
    let summary = run_common_doctor(&project, &task_config, input, &probe)?;
    print_title("NavLab Real Common Doctor");
    print_status("common_doctor", summary.ok);
    print_key_value("task", &summary.task_name);
    print_key_value("fcu_bridge_mode", &summary.fcu_bridge_mode);
    print_key_value("mode", &summary.common_state.mode);
    print_key_value(
        "external_nav_source",
        &summary.common_state.configured_external_nav_source_set,
    );
    print_key_value("blockers", &summary.blockers.len().to_string());
    if summary.ok {
        Ok(())
    } else {
        bail!(
            "real common doctor blocked: {}",
            summary.blockers.join(", ")
        )
    }
}

fn doctor_chain(loader: &Loader, registry: &Registry, command: DoctorChainCommand) -> Result<()> {
    let project = loader.load_project()?;
    let task_config = loader.load_task(&project, &command.task_id, None)?;
    if registry.create(&command.task_id).is_none() {
        return Err(RealOrchestrationError::UnknownTask(command.task_id).into());
    }
    let environment = HostEnvironmentProbe;
    let topic_probe = HostTopicProbe;
    let summary = run_doctor_chain(
        &project,
        &task_config,
        &environment,
        &topic_probe,
        DoctorChainInput {
            prepare_dry_run: command.prepare_dry_run || !command.allow_live_prepare,
            allow_live_prepare: command.allow_live_prepare,
            upstream_json: command.upstream_json,
            artifact_dir: command.artifact_dir,
            summary_path: command.summary_path,
        },
    )?;
    print_title("NavLab Real Doctor Chain");
    print_status("doctor_chain", summary.ok);
    print_key_value("task", &summary.task_name);
    print_key_value("artifact_dir", &summary.artifact_dir);
    print_key_value("prepare_stopped", &summary.prepare_stopped.to_string());
    print_key_value("blockers", &summary.blockers.len().to_string());
    if summary.ok {
        Ok(())
    } else {
        bail!("real doctor chain blocked: {}", summary.blockers.join(", "))
    }
}

fn task_doctor(loader: &Loader, registry: &Registry, command: TaskDoctorCommand) -> Result<()> {
    let project = loader.load_project()?;
    let task_config = loader.load_task(&project, &command.task_id, None)?;
    if registry.create(&command.task_id).is_none() {
        return Err(RealOrchestrationError::UnknownTask(command.task_id).into());
    }
    let input = TaskDoctorInput {
        upstream_json: command.upstream_json,
        summary_path: command.summary_path,
    };
    let summary = run_task_doctor(&project, &task_config, input)?;
    print_title("NavLab Real Task Doctor");
    print_status("task_doctor", summary.ok);
    print_key_value("task", &summary.task_name);
    print_key_value("fcu_bridge_mode", &summary.fcu_bridge_mode);
    print_key_value("blockers", &summary.blockers.len().to_string());
    if summary.ok {
        Ok(())
    } else {
        bail!("real task doctor blocked: {}", summary.blockers.join(", "))
    }
}

fn list_tasks(loader: &Loader, registry: &Registry) -> Result<()> {
    let project = loader.load_project()?;
    let task_configs = loader.load_tasks(&project)?;
    let configured = registry.configure(&task_configs)?;
    print_title("NavLab Real Tasks");
    for task in configured {
        print_key_value(&task.id, &task.description);
    }
    Ok(())
}

fn show_task(loader: &Loader, registry: &Registry, task_id: &str) -> Result<()> {
    let project = loader.load_project()?;
    let task_configs = loader.load_tasks(&project)?;
    let configured = registry.configure(&task_configs)?;
    let task = configured
        .into_iter()
        .find(|task| task.id == task_id)
        .ok_or_else(|| RealOrchestrationError::UnknownTask(task_id.to_string()))?;
    println!("{}", serde_json::to_string_pretty(&task)?);
    Ok(())
}

async fn run_task(loader: &Loader, registry: &Registry, command: RunCommand) -> Result<()> {
    let project = loader.load_project()?;
    let task_config =
        loader.load_task(&project, &command.task_id, command.task_config.as_deref())?;
    let task = registry
        .create(&command.task_id)
        .ok_or_else(|| RealOrchestrationError::UnknownTask(command.task_id.clone()))?;
    let mut run_artifact_dir = command.artifact_dir.clone();
    if command.with_doctor_chain && run_artifact_dir.is_none() && command.summary_path.is_none() {
        run_artifact_dir = Some(default_run_artifact_dir(&project, &command.task_id));
    }
    let mut doctor_chain_summary = None;
    if command.with_doctor_chain {
        let environment = HostEnvironmentProbe;
        let topic_probe = HostTopicProbe;
        let summary = run_doctor_chain(
            &project,
            &task_config,
            &environment,
            &topic_probe,
            doctor_chain_input_from_run_command(&command, run_artifact_dir.clone()),
        )?;
        print_title("NavLab Real Run Doctor Chain");
        print_status("doctor_chain", summary.ok);
        print_key_value("artifact_dir", &summary.artifact_dir);
        print_key_value("prepare_stopped", &summary.prepare_stopped.to_string());
        print_key_value("blockers", &summary.blockers.len().to_string());
        doctor_chain_summary = Some(summary);
    }
    task.run(
        &project,
        &task_config,
        crate::tasks::RunOptions {
            dry_run: command.dry_run,
            motor_debug: MotorDebugOverrides {
                motor_percent: command.motor_percent,
                motor_sec: command.motor_sec,
                motor_count: command.motor_count,
            },
            operator_confirmations: operator_confirmations_from_run_command(&command),
            artifact_dir: run_artifact_dir,
            summary_path: command.summary_path,
            doctor_chain: doctor_chain_summary,
        },
    )
    .await
}

fn doctor_chain_input_from_run_command(
    command: &RunCommand,
    run_artifact_dir: Option<PathBuf>,
) -> DoctorChainInput {
    DoctorChainInput {
        prepare_dry_run: !command.allow_live_prepare,
        allow_live_prepare: command.allow_live_prepare,
        upstream_json: command.upstream_json.clone(),
        artifact_dir: command.doctor_artifact_dir.clone().or(run_artifact_dir),
        summary_path: None,
    }
}

fn default_run_artifact_dir(project: &crate::config::ProjectConfig, task_id: &str) -> PathBuf {
    project.paths.artifact_root.join(task_id).join(run_id())
}

fn run_id() -> String {
    let now = time::OffsetDateTime::now_utc();
    format!(
        "{:04}{:02}{:02}T{:02}{:02}{:02}Z",
        now.year(),
        u8::from(now.month()),
        now.day(),
        now.hour(),
        now.minute(),
        now.second()
    )
}

fn operator_confirmations_from_run_command(command: &RunCommand) -> OperatorConfirmations {
    OperatorConfirmations {
        manual_takeover: confirmation_value(
            "NAVLAB_CONFIRM_MANUAL_TAKEOVER",
            command.confirm_manual_takeover,
        ),
        kill_switch: confirmation_value("NAVLAB_CONFIRM_KILL_SWITCH", command.confirm_kill_switch),
        safe_area: confirmation_value("NAVLAB_CONFIRM_SAFE_AREA", command.confirm_safe_area),
        no_props: confirmation_value("NAVLAB_CONFIRM_NO_PROPS", command.confirm_no_props),
        props_installed: confirmation_value(
            "NAVLAB_CONFIRM_PROPS_INSTALLED",
            command.confirm_props_installed,
        ),
    }
}

fn confirmation_value(env_name: &str, cli_value: bool) -> bool {
    let Ok(raw) = std::env::var(env_name) else {
        return cli_value;
    };
    let raw = raw.trim();
    if raw.is_empty() {
        cli_value
    } else {
        matches!(
            raw.to_ascii_lowercase().as_str(),
            "true" | "1" | "yes" | "on"
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn run_doctor_chain_input_defaults_prepare_to_dry_run() {
        let command = RunCommand {
            task_id: "motor-debug".to_string(),
            dry_run: true,
            with_doctor_chain: true,
            allow_live_prepare: false,
            upstream_json: Some("upstream.json".into()),
            doctor_artifact_dir: Some("chain".into()),
            artifact_dir: None,
            summary_path: None,
            confirm_manual_takeover: false,
            confirm_kill_switch: false,
            confirm_safe_area: false,
            confirm_no_props: false,
            confirm_props_installed: false,
            task_config: None,
            motor_percent: None,
            motor_sec: None,
            motor_count: None,
        };

        let input = doctor_chain_input_from_run_command(&command, None);

        assert!(input.prepare_dry_run);
        assert!(!input.allow_live_prepare);
        assert_eq!(
            input.upstream_json.as_deref(),
            Some(std::path::Path::new("upstream.json"))
        );
        assert_eq!(
            input.artifact_dir.as_deref(),
            Some(std::path::Path::new("chain"))
        );
    }

    #[test]
    fn run_doctor_chain_input_uses_run_artifact_dir_when_no_doctor_dir() {
        let command = RunCommand {
            task_id: "motor-debug".to_string(),
            dry_run: false,
            with_doctor_chain: true,
            allow_live_prepare: false,
            upstream_json: None,
            doctor_artifact_dir: None,
            artifact_dir: None,
            summary_path: None,
            confirm_manual_takeover: false,
            confirm_kill_switch: false,
            confirm_safe_area: false,
            confirm_no_props: false,
            confirm_props_installed: false,
            task_config: None,
            motor_percent: None,
            motor_sec: None,
            motor_count: None,
        };

        let input = doctor_chain_input_from_run_command(&command, Some("run-artifacts".into()));

        assert_eq!(
            input.artifact_dir.as_deref(),
            Some(std::path::Path::new("run-artifacts"))
        );
    }

    #[test]
    fn run_doctor_chain_input_prefers_explicit_doctor_artifact_dir() {
        let command = RunCommand {
            task_id: "motor-debug".to_string(),
            dry_run: false,
            with_doctor_chain: true,
            allow_live_prepare: false,
            upstream_json: None,
            doctor_artifact_dir: Some("doctor-artifacts".into()),
            artifact_dir: None,
            summary_path: None,
            confirm_manual_takeover: false,
            confirm_kill_switch: false,
            confirm_safe_area: false,
            confirm_no_props: false,
            confirm_props_installed: false,
            task_config: None,
            motor_percent: None,
            motor_sec: None,
            motor_count: None,
        };

        let input = doctor_chain_input_from_run_command(&command, Some("run-artifacts".into()));

        assert_eq!(
            input.artifact_dir.as_deref(),
            Some(std::path::Path::new("doctor-artifacts"))
        );
    }

    #[test]
    fn run_doctor_chain_input_allows_explicit_live_prepare() {
        let command = RunCommand {
            task_id: "motor-debug".to_string(),
            dry_run: false,
            with_doctor_chain: true,
            allow_live_prepare: true,
            upstream_json: None,
            doctor_artifact_dir: None,
            artifact_dir: None,
            summary_path: None,
            confirm_manual_takeover: false,
            confirm_kill_switch: false,
            confirm_safe_area: false,
            confirm_no_props: false,
            confirm_props_installed: false,
            task_config: None,
            motor_percent: None,
            motor_sec: None,
            motor_count: None,
        };

        let input = doctor_chain_input_from_run_command(&command, None);

        assert!(!input.prepare_dry_run);
        assert!(input.allow_live_prepare);
    }

    #[test]
    fn operator_confirmations_use_cli_flags() {
        let command = RunCommand {
            task_id: "motor-debug".to_string(),
            dry_run: false,
            with_doctor_chain: false,
            allow_live_prepare: false,
            upstream_json: None,
            doctor_artifact_dir: None,
            artifact_dir: None,
            summary_path: None,
            confirm_manual_takeover: true,
            confirm_kill_switch: true,
            confirm_safe_area: true,
            confirm_no_props: true,
            confirm_props_installed: true,
            task_config: None,
            motor_percent: None,
            motor_sec: None,
            motor_count: None,
        };

        let confirmations = operator_confirmations_from_run_command(&command);

        assert!(confirmations.manual_takeover);
        assert!(confirmations.kill_switch);
        assert!(confirmations.safe_area);
        assert!(confirmations.no_props);
        assert!(confirmations.props_installed);
    }

    #[test]
    fn confirmation_value_accepts_env_truthy_values() {
        unsafe {
            std::env::set_var("NAVLAB_TEST_CONFIRMATION", "yes");
        }

        assert!(confirmation_value("NAVLAB_TEST_CONFIRMATION", false));

        unsafe {
            std::env::remove_var("NAVLAB_TEST_CONFIRMATION");
        }
    }
}
