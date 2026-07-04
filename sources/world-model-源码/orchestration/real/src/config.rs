use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail};
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone)]
pub struct Loader {
    config_path: PathBuf,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ProjectConfig {
    pub orchestration: OrchestrationConfig,
    pub runtime: RuntimeConfig,
    pub paths: PathConfig,
    pub sources: SourceConfig,
    #[serde(default)]
    pub preflight: PreflightConfig,
    #[serde(default)]
    pub prepare: PrepareConfig,
    #[serde(default)]
    pub common_doctor: CommonDoctorConfig,
    #[serde(default)]
    pub task_doctor: TaskDoctorConfig,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct OrchestrationConfig {
    pub family: String,
    pub implementation: String,
    pub contract_version: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RuntimeConfig {
    pub mode: String,
    pub backend: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct PathConfig {
    pub workspace_root: PathBuf,
    pub artifact_root: PathBuf,
    pub task_config_dir: PathBuf,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct SourceConfig {
    pub scan_source_claim: String,
    pub scan_source_topic: String,
    pub fcu_source_claim: String,
    pub imu_source_claim: String,
    pub rangefinder_source_claim: String,
    pub slam_source_claim: String,
    #[serde(default)]
    pub required_real_topics: Vec<String>,
    #[serde(default)]
    pub forbidden_simulation_input_topics: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TaskConfig {
    pub id: String,
    pub family: String,
    pub description: String,
    #[serde(default)]
    pub capabilities: Vec<String>,
    #[serde(default)]
    pub task: BTreeMap<String, Value>,
    #[serde(default)]
    pub safety: BTreeMap<String, Value>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct PreflightConfig {
    pub valid_for_sec: f64,
    pub ros_distro: String,
    #[serde(default)]
    pub serial_mavlink: SerialMavlinkConfig,
    #[serde(default)]
    pub dependencies: PreflightDependencyConfig,
}

impl Default for PreflightConfig {
    fn default() -> Self {
        Self {
            valid_for_sec: 300.0,
            ros_distro: "humble".to_string(),
            serial_mavlink: SerialMavlinkConfig::default(),
            dependencies: PreflightDependencyConfig::default(),
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct SerialMavlinkConfig {
    pub enabled: bool,
    pub port: String,
    pub baud: u32,
    pub heartbeat_timeout_sec: f64,
    #[serde(default)]
    pub required_messages: Vec<String>,
    #[serde(default)]
    pub optional_messages: Vec<String>,
}

impl Default for SerialMavlinkConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            port: "/dev/ttyACM0".to_string(),
            baud: 115200,
            heartbeat_timeout_sec: 5.0,
            required_messages: vec![
                "HEARTBEAT".to_string(),
                "SYS_STATUS".to_string(),
                "ATTITUDE".to_string(),
            ],
            optional_messages: vec![
                "LOCAL_POSITION_NED".to_string(),
                "GLOBAL_POSITION_INT".to_string(),
                "RANGEFINDER".to_string(),
                "DISTANCE_SENSOR".to_string(),
                "HIGHRES_IMU".to_string(),
                "RAW_IMU".to_string(),
                "SCALED_IMU".to_string(),
            ],
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct PreflightDependencyConfig {
    #[serde(default)]
    pub required_command_groups: Vec<Vec<String>>,
    #[serde(default)]
    pub required_ros_packages: Vec<String>,
    #[serde(default)]
    pub required_python_modules: Vec<String>,
    #[serde(default)]
    pub required_process_services: Vec<String>,
}

impl Default for PreflightDependencyConfig {
    fn default() -> Self {
        Self {
            required_command_groups: vec![
                vec!["mavlink-routerd".to_string(), "mavlink-router".to_string()],
                vec!["ros2".to_string()],
            ],
            required_ros_packages: Vec::new(),
            required_python_modules: Vec::new(),
            required_process_services: Vec::new(),
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct PrepareConfig {
    #[serde(default)]
    pub dry_run: bool,
    pub fcu_bridge_mode: String,
    #[serde(default = "default_prepare_process_log_dir")]
    pub process_log_dir: PathBuf,
    #[serde(default = "default_prepare_summary_artifact_dir")]
    pub summary_artifact_dir: PathBuf,
    #[serde(default = "default_prepare_ros_topic_probe_timeout_sec")]
    pub ros_topic_probe_timeout_sec: f64,
    #[serde(default = "default_prepare_topic_freshness_window_sec")]
    pub topic_freshness_window_sec: f64,
    #[serde(default = "default_prepare_external_nav_yaw_required")]
    pub external_nav_yaw_required: bool,
    #[serde(default = "default_prepare_external_nav_yaw_status_topics")]
    pub external_nav_yaw_status_topics: Vec<String>,
    #[serde(default = "default_prepare_external_nav_yaw_ready_fields")]
    pub external_nav_yaw_ready_fields: Vec<String>,
    #[serde(default = "default_prepare_mavlink_router_serial_port")]
    pub mavlink_router_serial_port: String,
    #[serde(default = "default_prepare_mavlink_router_baud")]
    pub mavlink_router_baud: u32,
    #[serde(default = "default_prepare_mavlink_router_local_endpoint")]
    pub mavlink_router_local_endpoint: String,
    #[serde(default = "default_prepare_fcu_bridge_state_topic")]
    pub fcu_bridge_state_topic: String,
    #[serde(default = "default_prepare_height_rangefinder_required")]
    pub height_rangefinder_required: bool,
    #[serde(default = "default_prepare_required_upstream_topics")]
    pub required_upstream_topics: Vec<String>,
    #[serde(default = "default_prepare_forbidden_simulation_topics")]
    pub forbidden_simulation_topics: Vec<String>,
    #[serde(default = "default_prepare_mavlink_router_service")]
    pub mavlink_router: PrepareServiceConfig,
    #[serde(default = "default_prepare_navlab_mavlink_bridge_service")]
    pub navlab_mavlink_bridge: PrepareServiceConfig,
    #[serde(default = "default_prepare_mavros_service")]
    pub mavros: PrepareServiceConfig,
    #[serde(default = "default_prepare_lidar_service")]
    pub lidar: PrepareServiceConfig,
    #[serde(default = "default_prepare_slam_service")]
    pub slam: PrepareServiceConfig,
    #[serde(default = "default_prepare_rangefinder_bridge_service")]
    pub rangefinder_bridge: PrepareServiceConfig,
}

impl Default for PrepareConfig {
    fn default() -> Self {
        Self {
            dry_run: false,
            fcu_bridge_mode: "navlab_mavlink".to_string(),
            process_log_dir: default_prepare_process_log_dir(),
            summary_artifact_dir: default_prepare_summary_artifact_dir(),
            ros_topic_probe_timeout_sec: default_prepare_ros_topic_probe_timeout_sec(),
            topic_freshness_window_sec: default_prepare_topic_freshness_window_sec(),
            external_nav_yaw_required: default_prepare_external_nav_yaw_required(),
            external_nav_yaw_status_topics: default_prepare_external_nav_yaw_status_topics(),
            external_nav_yaw_ready_fields: default_prepare_external_nav_yaw_ready_fields(),
            mavlink_router_serial_port: default_prepare_mavlink_router_serial_port(),
            mavlink_router_baud: default_prepare_mavlink_router_baud(),
            mavlink_router_local_endpoint: default_prepare_mavlink_router_local_endpoint(),
            fcu_bridge_state_topic: default_prepare_fcu_bridge_state_topic(),
            height_rangefinder_required: default_prepare_height_rangefinder_required(),
            required_upstream_topics: default_prepare_required_upstream_topics(),
            forbidden_simulation_topics: default_prepare_forbidden_simulation_topics(),
            mavlink_router: default_prepare_mavlink_router_service(),
            navlab_mavlink_bridge: default_prepare_navlab_mavlink_bridge_service(),
            mavros: default_prepare_mavros_service(),
            lidar: default_prepare_lidar_service(),
            slam: default_prepare_slam_service(),
            rangefinder_bridge: default_prepare_rangefinder_bridge_service(),
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct PrepareServiceConfig {
    #[serde(default = "default_prepare_service_enabled")]
    pub enabled: bool,
    #[serde(default = "default_prepare_service_required")]
    pub required: bool,
    #[serde(default)]
    pub command: Vec<String>,
    #[serde(default)]
    pub cwd: String,
    #[serde(default)]
    pub env: BTreeMap<String, String>,
    #[serde(default = "default_prepare_service_startup_timeout_sec")]
    pub startup_timeout_sec: f64,
    #[serde(default)]
    pub health_topics: Vec<String>,
    #[serde(default = "default_prepare_service_shutdown_policy")]
    pub shutdown_policy: String,
    #[serde(default)]
    pub direct_serial_access_allowed: bool,
}

impl Default for PrepareServiceConfig {
    fn default() -> Self {
        Self {
            enabled: default_prepare_service_enabled(),
            required: default_prepare_service_required(),
            command: Vec::new(),
            cwd: String::new(),
            env: BTreeMap::new(),
            startup_timeout_sec: default_prepare_service_startup_timeout_sec(),
            health_topics: Vec::new(),
            shutdown_policy: default_prepare_service_shutdown_policy(),
            direct_serial_access_allowed: false,
        }
    }
}

fn default_prepare_process_log_dir() -> PathBuf {
    "artifacts/runtime_logs/real_prepare".into()
}

fn default_prepare_summary_artifact_dir() -> PathBuf {
    "artifacts/ros/navlab_real_prepare".into()
}

fn default_prepare_ros_topic_probe_timeout_sec() -> f64 {
    5.0
}

fn default_prepare_topic_freshness_window_sec() -> f64 {
    2.0
}

fn default_prepare_external_nav_yaw_required() -> bool {
    true
}

fn default_prepare_external_nav_yaw_status_topics() -> Vec<String> {
    vec![
        "/external_nav/status".to_string(),
        "/navlab/slam/status".to_string(),
    ]
}

fn default_prepare_external_nav_yaw_ready_fields() -> Vec<String> {
    vec![
        "external_nav_yaw_ready".to_string(),
        "yaw_ready".to_string(),
        "orientation_ready".to_string(),
        "ready".to_string(),
    ]
}

fn default_prepare_mavlink_router_serial_port() -> String {
    "/dev/ttyUSB1".to_string()
}

fn default_prepare_mavlink_router_baud() -> u32 {
    115200
}

fn default_prepare_mavlink_router_local_endpoint() -> String {
    "127.0.0.1:14550".to_string()
}

fn default_prepare_fcu_bridge_state_topic() -> String {
    "/navlab/mavlink/status".to_string()
}

fn default_prepare_height_rangefinder_required() -> bool {
    true
}

fn default_prepare_required_upstream_topics() -> Vec<String> {
    vec![
        "/scan".to_string(),
        "/imu/data".to_string(),
        "/imu".to_string(),
        "/tf".to_string(),
        "/tf_static".to_string(),
        "/slam/odom".to_string(),
        "/navlab/slam/status".to_string(),
    ]
}

fn default_prepare_forbidden_simulation_topics() -> Vec<String> {
    vec![
        "/gazebo/*".to_string(),
        "/scan_ideal".to_string(),
        "/sim/x2/status".to_string(),
        "/rangefinder/down/scan_ideal".to_string(),
    ]
}

fn default_prepare_service_enabled() -> bool {
    true
}

fn default_prepare_service_required() -> bool {
    true
}

fn default_prepare_service_startup_timeout_sec() -> f64 {
    8.0
}

fn default_prepare_service_shutdown_policy() -> String {
    "stop_on_wrapper_exit".to_string()
}

fn default_prepare_mavlink_router_service() -> PrepareServiceConfig {
    PrepareServiceConfig {
        command: vec![
            "mavlink-routerd".to_string(),
            "-e".to_string(),
            default_prepare_mavlink_router_local_endpoint(),
            format!(
                "{}:{}",
                default_prepare_mavlink_router_serial_port(),
                default_prepare_mavlink_router_baud()
            ),
        ],
        ..PrepareServiceConfig::default()
    }
}

fn default_prepare_navlab_mavlink_bridge_service() -> PrepareServiceConfig {
    PrepareServiceConfig {
        command: vec![
            "uv".to_string(),
            "run".to_string(),
            "--project".to_string(),
            "orchestration".to_string(),
            "python".to_string(),
            "-m".to_string(),
            "navlab.real.companion.nodes.mavlink_bridge".to_string(),
            "--ros-distro".to_string(),
            "humble".to_string(),
            "--mavlink-endpoint".to_string(),
            "tcp:127.0.0.1:14550".to_string(),
        ],
        health_topics: vec![
            "/navlab/mavlink/status".to_string(),
            "/navlab/fcu/local_position_pose".to_string(),
            "/mavlink_external_nav/status".to_string(),
            "/imu/data".to_string(),
            "/imu/status".to_string(),
        ],
        ..PrepareServiceConfig::default()
    }
}

fn default_prepare_mavros_service() -> PrepareServiceConfig {
    PrepareServiceConfig {
        enabled: false,
        command: vec![
            "ros2".to_string(),
            "launch".to_string(),
            "mavros".to_string(),
            "apm.launch".to_string(),
            "fcu_url:=udp://@127.0.0.1:14550".to_string(),
        ],
        health_topics: vec!["/mavros/state".to_string(), "/ap/v1/status".to_string()],
        ..PrepareServiceConfig::default()
    }
}

fn default_prepare_lidar_service() -> PrepareServiceConfig {
    PrepareServiceConfig {
        command: vec![
            "bash".to_string(),
            "-lc".to_string(),
            "source /opt/ros/humble/setup.bash && source install/setup.bash && PYTHONPATH=.:$PYTHONPATH /usr/bin/python3 -m navlab.real.companion.nodes.ydlidar_x2_scan --port /dev/ttyUSB0 --baud 115200 --scan-topic /scan --frame-id laser_frame".to_string(),
        ],
        health_topics: vec!["/scan".to_string()],
        ..PrepareServiceConfig::default()
    }
}

fn default_prepare_slam_service() -> PrepareServiceConfig {
    PrepareServiceConfig {
        command: vec![
            "ros2".to_string(),
            "launch".to_string(),
            "navlab_slam_bringup".to_string(),
            "navlab_slam_bringup.launch.py".to_string(),
            "use_sim_time:=false".to_string(),
            "launch_fake_odom:=false".to_string(),
            "launch_cartographer_backend:=true".to_string(),
            "publish_placeholder_odom:=false".to_string(),
            "cartographer_configuration_basename:=navlab_cartographer_2d_real.lua".to_string(),
            "scan_topic:=/scan".to_string(),
            "imu_source_topic:=/imu/data".to_string(),
            "imu_topic:=/imu".to_string(),
            "cartographer_odometry_topic:=/cartographer/odometry_input".to_string(),
            "odom_topic:=/slam/odom".to_string(),
            "external_nav_input_odom_topic:=/slam/odom".to_string(),
            "require_imu_for_external_nav:=false".to_string(),
            "require_height_for_external_nav:=false".to_string(),
            "laser_frame:=laser_frame".to_string(),
            "imu_frame:=imu_link".to_string(),
            "base_frame:=base_link".to_string(),
        ],
        health_topics: vec![
            "/imu".to_string(),
            "/slam/odom".to_string(),
            "/navlab/slam/status".to_string(),
            "/external_nav/status".to_string(),
        ],
        ..PrepareServiceConfig::default()
    }
}

fn default_prepare_rangefinder_bridge_service() -> PrepareServiceConfig {
    PrepareServiceConfig {
        command: vec![
            "bash".to_string(),
            "-lc".to_string(),
            "source /opt/ros/humble/setup.bash && source install/setup.bash && PYTHONPATH=.:$PWD/orchestration/.venv/lib/python3.11/site-packages:$PYTHONPATH /usr/bin/python3 -m navlab.real.companion.nodes.rangefinder_bridge --mavlink-endpoint tcp:127.0.0.1:14550 --range-topic /rangefinder/down/range --status-topic /rangefinder/down/status --frame-id rangefinder_down_frame --accepted-orientation 25".to_string(),
        ],
        health_topics: vec![
            "/rangefinder/down/range".to_string(),
            "/rangefinder/down/status".to_string(),
        ],
        ..PrepareServiceConfig::default()
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CommonDoctorConfig {
    pub external_nav_status_topic: String,
    pub mavlink_external_nav_status_topic: String,
}

impl Default for CommonDoctorConfig {
    fn default() -> Self {
        Self {
            external_nav_status_topic: "/external_nav/status".to_string(),
            mavlink_external_nav_status_topic: "/mavlink_external_nav/status".to_string(),
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TaskDoctorConfig {
    pub fcu_status_topic: String,
    pub fcu_bridge_state_topic: String,
}

impl Default for TaskDoctorConfig {
    fn default() -> Self {
        Self {
            fcu_status_topic: "/ap/v1/status".to_string(),
            fcu_bridge_state_topic: "/navlab/mavlink/status".to_string(),
        }
    }
}

impl Loader {
    pub fn new(config_path: impl Into<PathBuf>) -> Self {
        Self {
            config_path: config_path.into(),
        }
    }

    pub fn load_project(&self) -> Result<ProjectConfig> {
        let path = self.resolve_config_path();
        let source = fs::read_to_string(&path)
            .with_context(|| format!("read real project config {}", path.display()))?;
        toml::from_str(&source)
            .with_context(|| format!("parse real project config {}", path.display()))
    }

    pub fn load_tasks(&self, project: &ProjectConfig) -> Result<Vec<TaskConfig>> {
        let dir = self.task_config_dir(project);
        if !dir.is_dir() {
            bail!("real task config dir does not exist: {}", dir.display());
        }
        let mut tasks = Vec::new();
        for entry in
            fs::read_dir(&dir).with_context(|| format!("read task config dir {}", dir.display()))?
        {
            let path = entry?.path();
            if path.extension().and_then(|value| value.to_str()) != Some("yaml") {
                continue;
            }
            tasks.push(self.load_task_from_path(&path)?);
        }
        tasks.sort_by(|left, right| left.id.cmp(&right.id));
        Ok(tasks)
    }

    pub fn load_task(
        &self,
        project: &ProjectConfig,
        task_id: &str,
        task_config_path: Option<&Path>,
    ) -> Result<TaskConfig> {
        let path = match task_config_path {
            Some(path) => path.to_path_buf(),
            None => self
                .task_config_dir(project)
                .join(format!("{task_id}.yaml")),
        };
        self.load_task_from_path(&path)
    }

    fn load_task_from_path(&self, path: &Path) -> Result<TaskConfig> {
        let source = fs::read_to_string(path)
            .with_context(|| format!("read real task config {}", path.display()))?;
        serde_yaml::from_str(&source)
            .with_context(|| format!("parse real task config {}", path.display()))
    }

    fn resolve_config_path(&self) -> PathBuf {
        if self.config_path.is_absolute() {
            self.config_path.clone()
        } else {
            std::env::current_dir()
                .unwrap_or_else(|_| PathBuf::from("."))
                .join(&self.config_path)
        }
    }

    fn task_config_dir(&self, project: &ProjectConfig) -> PathBuf {
        let base = self
            .resolve_config_path()
            .parent()
            .map(Path::to_path_buf)
            .unwrap_or_else(|| PathBuf::from("."));
        if project.paths.task_config_dir.is_absolute() {
            project.paths.task_config_dir.clone()
        } else {
            base.join(&project.paths.task_config_dir)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loads_real_project_and_task_configs() {
        let loader = Loader::new("config.toml");
        let project = loader.load_project().expect("project config");
        assert_eq!(project.orchestration.family, "real");
        assert_eq!(project.orchestration.implementation, "rust");
        assert_eq!(project.preflight.ros_distro, "humble");
        assert_eq!(project.prepare.mavlink_router_serial_port, "/dev/ttyUSB1");
        assert_eq!(project.prepare.navlab_mavlink_bridge.health_topics.len(), 5);
        assert_eq!(
            project.common_doctor.external_nav_status_topic,
            "/external_nav/status"
        );
        assert_eq!(project.task_doctor.fcu_status_topic, "/ap/v1/status");
        assert_eq!(project.preflight.serial_mavlink.port, "/dev/ttyUSB1");
        assert!(
            project
                .preflight
                .dependencies
                .required_ros_packages
                .contains(&"cartographer_ros".to_string())
        );

        let tasks = loader.load_tasks(&project).expect("task configs");
        let task_ids = tasks
            .iter()
            .map(|task| task.id.as_str())
            .collect::<Vec<_>>();
        assert!(task_ids.contains(&"motor-debug"));
        assert!(task_ids.contains(&"hover"));
    }
}
