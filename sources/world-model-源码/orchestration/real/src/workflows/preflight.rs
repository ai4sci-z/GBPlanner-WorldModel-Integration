use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::{Context, Result};
use serde::Serialize;
use time::{OffsetDateTime, format_description::well_known::Rfc3339};
use tracing::{info, instrument};

use crate::config::{PreflightDependencyConfig, ProjectConfig, SerialMavlinkConfig};
use crate::contracts;

#[derive(Debug, Clone, Serialize)]
pub struct PreflightSummary {
    pub ok: bool,
    pub blocked: bool,
    pub blockers: Vec<String>,
    pub warnings: Vec<String>,
    pub runtime_backend: String,
    pub runtime_mode: String,
    pub preflight_claim: String,
    pub flight_claim: String,
    pub landing_claim: String,
    pub checked_at: String,
    pub valid_for_sec: f64,
    pub ros_distro: String,
    pub fcu_bridge_mode: String,
    pub real_preflight: RealPreflightEvidence,
}

#[derive(Debug, Clone, Serialize)]
pub struct RealPreflightEvidence {
    pub serial_mavlink: SerialMavlinkEvidence,
    pub dependencies: DependencyEvidence,
}

#[derive(Debug, Clone, Serialize)]
pub struct SerialMavlinkEvidence {
    pub enabled: bool,
    pub port: String,
    pub baud: u32,
    pub heartbeat_timeout_sec: f64,
    pub required_messages: Vec<String>,
    pub optional_messages: Vec<String>,
    pub serial_open_ok: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct DependencyEvidence {
    pub ros_distro: String,
    pub required_command_groups: Vec<CommandGroupEvidence>,
    pub required_python_modules: BTreeMap<String, bool>,
    pub required_ros_packages: BTreeMap<String, RosPackageEvidence>,
    pub required_process_services: BTreeMap<String, bool>,
    pub configured_process_services: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct CommandGroupEvidence {
    pub candidates: Vec<String>,
    pub found: bool,
    pub selected: String,
    pub path: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct RosPackageEvidence {
    pub present: bool,
    pub prefix: String,
    pub error: String,
}

#[cfg_attr(test, mockall::automock)]
pub trait EnvironmentProbe {
    fn command_path(&self, command: &str, ros_distro: &str) -> Option<String>;
    fn python_module_present(&self, module: &str) -> bool;
    fn ros_package_prefix(&self, package: &str, ros_distro: &str) -> RosPackageEvidence;
    fn process_services(&self) -> Vec<String>;
}

#[derive(Debug, Default)]
pub struct HostEnvironmentProbe;

impl EnvironmentProbe for HostEnvironmentProbe {
    fn command_path(&self, command: &str, ros_distro: &str) -> Option<String> {
        if command == "ros2" {
            let ros2 = PathBuf::from("/opt/ros").join(ros_distro).join("bin/ros2");
            if ros2.exists() {
                return Some(ros2.display().to_string());
            }
            return find_in_path(command);
        }
        find_in_path(command)
    }

    fn python_module_present(&self, module: &str) -> bool {
        Command::new("python3")
            .args([
                "-c",
                &format!(
                    "import importlib.util, sys\ntry:\n    found = importlib.util.find_spec({module:?}) is not None\nexcept ModuleNotFoundError:\n    found = False\nsys.exit(0 if found else 1)"
                ),
            ])
            .output()
            .map(|output| output.status.success())
            .unwrap_or(false)
    }

    fn ros_package_prefix(&self, package: &str, ros_distro: &str) -> RosPackageEvidence {
        let Some(ros2) = self.command_path("ros2", ros_distro) else {
            return RosPackageEvidence {
                present: false,
                prefix: String::new(),
                error: format!("ros2_distro_not_found:{ros_distro}"),
            };
        };
        let output = Command::new(ros2).args(["pkg", "prefix", package]).output();
        match output {
            Ok(output) if output.status.success() => RosPackageEvidence {
                present: true,
                prefix: String::from_utf8_lossy(&output.stdout).trim().to_string(),
                error: String::new(),
            },
            Ok(output) => RosPackageEvidence {
                present: false,
                prefix: String::new(),
                error: String::from_utf8_lossy(&output.stderr).trim().to_string(),
            },
            Err(error) => RosPackageEvidence {
                present: false,
                prefix: String::new(),
                error: error.to_string(),
            },
        }
    }

    fn process_services(&self) -> Vec<String> {
        Vec::new()
    }
}

#[instrument(skip(project, environment))]
pub fn run_preflight(
    project: &ProjectConfig,
    environment: &dyn EnvironmentProbe,
    summary_path: Option<&Path>,
) -> Result<PreflightSummary> {
    let summary = build_preflight_summary(project, environment);
    let path = match summary_path {
        Some(path) => path.to_path_buf(),
        None => default_summary_path(project),
    };
    write_summary(&path, &summary)?;
    write_doctor_result(&path, "preflight", summary.ok, &summary.blockers)?;
    info!(
        ok = summary.ok,
        blocked = summary.blocked,
        path = %path.display(),
        "wrote real preflight summary"
    );
    Ok(summary)
}

fn write_doctor_result(
    summary_path: &Path,
    task_id: &str,
    ok: bool,
    blockers: &[String],
) -> Result<()> {
    let result = contracts::doctor_result(
        task_id,
        ok,
        blockers,
        vec![
            ("runtime_backend_process", ok),
            ("runtime_mode_real", ok),
            ("dependencies_available", ok),
        ],
    );
    contracts::write_json(
        &summary_path.with_file_name("doctor_result.json"),
        &result,
        "real preflight doctor result",
    )
}

pub fn build_preflight_summary(
    project: &ProjectConfig,
    environment: &dyn EnvironmentProbe,
) -> PreflightSummary {
    let mut blockers = Vec::new();
    if project.runtime.backend != "process" {
        blockers.push(format!(
            "runtime_backend_must_be_process:{}",
            project.runtime.backend
        ));
    }
    if project.runtime.mode != "real" {
        blockers.push(format!(
            "runtime_mode_must_be_real:{}",
            project.runtime.mode
        ));
    }

    let (serial_mavlink, serial_blockers) = probe_serial_mavlink(&project.preflight.serial_mavlink);
    let (dependencies, dependency_blockers) = probe_dependencies(
        &project.preflight.dependencies,
        &project.preflight.ros_distro,
        environment,
    );
    blockers.extend(serial_blockers);
    blockers.extend(dependency_blockers);
    blockers = dedupe(blockers);

    PreflightSummary {
        ok: blockers.is_empty(),
        blocked: !blockers.is_empty(),
        blockers,
        warnings: Vec::new(),
        runtime_backend: project.runtime.backend.clone(),
        runtime_mode: project.runtime.mode.clone(),
        preflight_claim: "evaluated".to_string(),
        flight_claim: "not_evaluated".to_string(),
        landing_claim: "not_evaluated".to_string(),
        checked_at: utc_now(),
        valid_for_sec: project.preflight.valid_for_sec,
        ros_distro: project.preflight.ros_distro.clone(),
        fcu_bridge_mode: project.prepare.fcu_bridge_mode.clone(),
        real_preflight: RealPreflightEvidence {
            serial_mavlink,
            dependencies,
        },
    }
}

pub fn probe_serial_mavlink(
    settings: &SerialMavlinkConfig,
) -> (SerialMavlinkEvidence, Vec<String>) {
    let mut blockers = Vec::new();
    let mut serial_open_ok = false;
    if settings.enabled {
        if is_network_endpoint(&settings.port) {
            blockers.push(format!(
                "serial_mavlink_endpoint_not_serial:{}",
                settings.port
            ));
        } else if !Path::new(&settings.port).exists() {
            blockers.push(format!("serial_port_missing:{}", settings.port));
        } else {
            serial_open_ok = true;
        }
    }

    (
        SerialMavlinkEvidence {
            enabled: settings.enabled,
            port: settings.port.clone(),
            baud: settings.baud,
            heartbeat_timeout_sec: settings.heartbeat_timeout_sec,
            required_messages: settings.required_messages.clone(),
            optional_messages: settings.optional_messages.clone(),
            serial_open_ok,
        },
        blockers,
    )
}

pub fn probe_dependencies(
    settings: &PreflightDependencyConfig,
    ros_distro: &str,
    environment: &dyn EnvironmentProbe,
) -> (DependencyEvidence, Vec<String>) {
    let mut blockers = Vec::new();
    let mut command_groups = Vec::new();
    for group in &settings.required_command_groups {
        let mut selected = String::new();
        let mut selected_path = String::new();
        for command in group {
            if let Some(path) = environment.command_path(command, ros_distro) {
                selected = command.clone();
                selected_path = path;
                break;
            }
        }
        if selected.is_empty() {
            blockers.push(format!("required_command_missing:{}", group.join("|")));
        }
        command_groups.push(CommandGroupEvidence {
            candidates: group.clone(),
            found: !selected.is_empty(),
            selected,
            path: selected_path,
        });
    }

    let mut python_modules = BTreeMap::new();
    for module in &settings.required_python_modules {
        let present = environment.python_module_present(module);
        python_modules.insert(module.clone(), present);
        if !present {
            blockers.push(format!("required_python_module_missing:{module}"));
        }
    }

    let mut ros_packages = BTreeMap::new();
    for package in &settings.required_ros_packages {
        let result = environment.ros_package_prefix(package, ros_distro);
        if !result.present {
            blockers.push(format!("required_ros_package_missing:{package}"));
        }
        ros_packages.insert(package.clone(), result);
    }

    let configured_process_services = environment.process_services();
    let service_set: BTreeSet<_> = configured_process_services.iter().cloned().collect();
    let mut required_process_services = BTreeMap::new();
    for service in &settings.required_process_services {
        let present = service_set.contains(service);
        required_process_services.insert(service.clone(), present);
        if !present {
            blockers.push(format!("required_process_service_missing:{service}"));
        }
    }

    (
        DependencyEvidence {
            ros_distro: ros_distro.to_string(),
            required_command_groups: command_groups,
            required_python_modules: python_modules,
            required_ros_packages: ros_packages,
            required_process_services,
            configured_process_services,
        },
        dedupe(blockers),
    )
}

fn write_summary(path: &Path, summary: &PreflightSummary) -> Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("create preflight artifact dir {}", parent.display()))?;
    }
    let data = serde_json::to_string_pretty(summary)?;
    fs::write(path, data)
        .with_context(|| format!("write real preflight summary {}", path.display()))
}

fn default_summary_path(project: &ProjectConfig) -> PathBuf {
    project
        .paths
        .artifact_root
        .join("preflight")
        .join(run_id())
        .join("summary.json")
}

fn run_id() -> String {
    let now = OffsetDateTime::now_utc();
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

fn utc_now() -> String {
    OffsetDateTime::now_utc()
        .format(&Rfc3339)
        .unwrap_or_else(|_| "unknown".to_string())
}

fn is_network_endpoint(value: &str) -> bool {
    let lower = value.to_ascii_lowercase();
    lower.starts_with("udp:")
        || lower.starts_with("tcp:")
        || lower.starts_with("udpin:")
        || lower.starts_with("udpout:")
}

fn find_in_path(command: &str) -> Option<String> {
    let paths = env::var_os("PATH")?;
    for dir in env::split_paths(&paths) {
        let candidate = dir.join(command);
        if candidate.is_file() {
            return Some(candidate.display().to_string());
        }
    }
    None
}

fn dedupe(values: Vec<String>) -> Vec<String> {
    let mut seen = BTreeSet::new();
    let mut result = Vec::new();
    for value in values {
        if seen.insert(value.clone()) {
            result.push(value);
        }
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::{
        CommonDoctorConfig, OrchestrationConfig, PathConfig, PrepareConfig, RuntimeConfig,
        SourceConfig, TaskDoctorConfig,
    };
    use rstest::rstest;

    fn project() -> ProjectConfig {
        ProjectConfig {
            orchestration: OrchestrationConfig {
                family: "real".to_string(),
                implementation: "rust".to_string(),
                contract_version: "navlab.orchestration.v1".to_string(),
            },
            runtime: RuntimeConfig {
                mode: "real".to_string(),
                backend: "process".to_string(),
            },
            paths: PathConfig {
                workspace_root: "../..".into(),
                artifact_root: "artifacts/real".into(),
                task_config_dir: "configs/tasks".into(),
            },
            sources: SourceConfig {
                scan_source_claim: "real_lidar_driver".to_string(),
                scan_source_topic: "/scan".to_string(),
                fcu_source_claim: "real_serial_mavlink_or_ardupilot_dds_bridge".to_string(),
                imu_source_claim: "real_fcu_or_sensor".to_string(),
                rangefinder_source_claim: "real_or_not_required".to_string(),
                slam_source_claim: "real_slam".to_string(),
                required_real_topics: vec![],
                forbidden_simulation_input_topics: vec![],
            },
            preflight: crate::config::PreflightConfig {
                serial_mavlink: SerialMavlinkConfig {
                    enabled: true,
                    ..SerialMavlinkConfig::default()
                },
                dependencies: PreflightDependencyConfig {
                    required_command_groups: vec![
                        vec!["mavlink-routerd".to_string(), "mavlink-router".to_string()],
                        vec!["ros2".to_string()],
                    ],
                    required_python_modules: vec![
                        "navlab.real.companion.nodes.mavlink_bridge".to_string(),
                    ],
                    required_ros_packages: vec!["navlab_slam_bringup".to_string()],
                    required_process_services: vec!["companion".to_string()],
                },
                ..crate::config::PreflightConfig::default()
            },
            prepare: PrepareConfig::default(),
            common_doctor: CommonDoctorConfig::default(),
            task_doctor: TaskDoctorConfig::default(),
        }
    }

    fn healthy_mock() -> MockEnvironmentProbe {
        let mut probe = MockEnvironmentProbe::new();
        probe
            .expect_command_path()
            .returning(|command, _| Some(format!("/usr/bin/{command}")));
        probe.expect_python_module_present().returning(|_| true);
        probe
            .expect_ros_package_prefix()
            .returning(|package, _| RosPackageEvidence {
                present: true,
                prefix: format!("/opt/ros/humble/share/{package}"),
                error: String::new(),
            });
        probe
            .expect_process_services()
            .returning(|| vec!["companion".to_string()]);
        probe
    }

    #[test]
    fn preflight_summary_json_contract_is_stable() {
        let summary = build_preflight_summary(&project(), &healthy_mock());

        insta::assert_json_snapshot!(summary, {
            ".checked_at" => "[checked_at]"
        }, @r###"
        {
          "ok": false,
          "blocked": true,
          "blockers": [
            "serial_port_missing:/dev/ttyACM0"
          ],
          "warnings": [],
          "runtime_backend": "process",
          "runtime_mode": "real",
          "preflight_claim": "evaluated",
          "flight_claim": "not_evaluated",
          "landing_claim": "not_evaluated",
          "checked_at": "[checked_at]",
          "valid_for_sec": 300.0,
          "ros_distro": "humble",
          "fcu_bridge_mode": "navlab_mavlink",
          "real_preflight": {
            "serial_mavlink": {
              "enabled": true,
              "port": "/dev/ttyACM0",
              "baud": 115200,
              "heartbeat_timeout_sec": 5.0,
              "required_messages": [
                "HEARTBEAT",
                "SYS_STATUS",
                "ATTITUDE"
              ],
              "optional_messages": [
                "LOCAL_POSITION_NED",
                "GLOBAL_POSITION_INT",
                "RANGEFINDER",
                "DISTANCE_SENSOR",
                "HIGHRES_IMU",
                "RAW_IMU",
                "SCALED_IMU"
              ],
              "serial_open_ok": false
            },
            "dependencies": {
              "ros_distro": "humble",
              "required_command_groups": [
                {
                  "candidates": [
                    "mavlink-routerd",
                    "mavlink-router"
                  ],
                  "found": true,
                  "selected": "mavlink-routerd",
                  "path": "/usr/bin/mavlink-routerd"
                },
                {
                  "candidates": [
                    "ros2"
                  ],
                  "found": true,
                  "selected": "ros2",
                  "path": "/usr/bin/ros2"
                }
              ],
              "required_python_modules": {
                "navlab.real.companion.nodes.mavlink_bridge": true
              },
              "required_ros_packages": {
                "navlab_slam_bringup": {
                  "present": true,
                  "prefix": "/opt/ros/humble/share/navlab_slam_bringup",
                  "error": ""
                }
              },
              "required_process_services": {
                "companion": true
              },
              "configured_process_services": [
                "companion"
              ]
            }
          }
        }
        "###);
    }

    #[rstest]
    #[case(
        "udp:127.0.0.1:14550",
        "serial_mavlink_endpoint_not_serial:udp:127.0.0.1:14550"
    )]
    #[case(
        "/tmp/navlab_missing_fcu_serial",
        "serial_port_missing:/tmp/navlab_missing_fcu_serial"
    )]
    fn serial_probe_blocks_invalid_ports(#[case] port: &str, #[case] blocker: &str) {
        let settings = SerialMavlinkConfig {
            enabled: true,
            port: port.to_string(),
            ..SerialMavlinkConfig::default()
        };

        let (_summary, blockers) = probe_serial_mavlink(&settings);

        assert_eq!(blockers, vec![blocker.to_string()]);
    }
}
