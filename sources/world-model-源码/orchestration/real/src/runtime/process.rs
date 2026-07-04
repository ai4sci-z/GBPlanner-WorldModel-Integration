use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File, OpenOptions};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use thiserror::Error;

#[cfg(unix)]
use std::os::unix::process::CommandExt;

#[derive(Debug, Error)]
pub enum RuntimeSpecError {
    #[error("runtime spec name must not be empty")]
    EmptyName,
    #[error("{name}: env keys must be non-empty strings")]
    EmptyEnvKey { name: String },
    #[error("service {name}: process backend requires command")]
    ServiceMissingCommand { name: String },
    #[error("service {name}: process backend does not accept image={image:?}")]
    ServiceImageUnsupported { name: String, image: String },
    #[error("probe {name}: command is required")]
    ProbeMissingCommand { name: String },
    #[error("probe {name}: timeout_sec must be positive")]
    ProbeInvalidTimeout { name: String },
    #[error("probe {name}: process backend does not accept image={image:?}")]
    ProbeImageUnsupported { name: String, image: String },
    #[error("process service {name} failed to start: {source}")]
    ServiceStart {
        name: String,
        #[source]
        source: std::io::Error,
    },
    #[error("process probe {name} failed to run: {source}")]
    ProbeRun {
        name: String,
        #[source]
        source: std::io::Error,
    },
    #[error("process handle {identifier} is unknown")]
    UnknownHandle { identifier: String },
    #[error("process backend state lock poisoned")]
    LockPoisoned,
    #[error("process log path {path} failed: {source}")]
    LogPath {
        path: PathBuf,
        #[source]
        source: std::io::Error,
    },
}

#[derive(Debug, Clone)]
pub struct ServiceSpec {
    pub name: String,
    pub command: Vec<String>,
    pub image: Option<String>,
    pub env: BTreeMap<String, String>,
    pub cwd: Option<PathBuf>,
    pub required: bool,
    pub log_path: Option<PathBuf>,
}

impl ServiceSpec {
    pub fn validate_for_process(&self) -> Result<(), RuntimeSpecError> {
        validate_name(&self.name)?;
        validate_env(&self.name, &self.env)?;
        if self.command.is_empty() {
            return Err(RuntimeSpecError::ServiceMissingCommand {
                name: self.name.clone(),
            });
        }
        if let Some(image) = &self.image {
            return Err(RuntimeSpecError::ServiceImageUnsupported {
                name: self.name.clone(),
                image: image.clone(),
            });
        }
        Ok(())
    }
}

#[derive(Debug, Clone)]
pub struct ProbeSpec {
    pub name: String,
    pub command: Vec<String>,
    pub image: Option<String>,
    pub env: BTreeMap<String, String>,
    pub cwd: Option<PathBuf>,
    pub timeout_sec: Option<f64>,
    pub log_path: Option<PathBuf>,
    pub required: bool,
}

impl ProbeSpec {
    pub fn validate_for_process(&self) -> Result<(), RuntimeSpecError> {
        validate_name(&self.name)?;
        validate_env(&self.name, &self.env)?;
        if self.command.is_empty() {
            return Err(RuntimeSpecError::ProbeMissingCommand {
                name: self.name.clone(),
            });
        }
        if self.timeout_sec.is_some_and(|timeout| timeout <= 0.0) {
            return Err(RuntimeSpecError::ProbeInvalidTimeout {
                name: self.name.clone(),
            });
        }
        if let Some(image) = &self.image {
            return Err(RuntimeSpecError::ProbeImageUnsupported {
                name: self.name.clone(),
                image: image.clone(),
            });
        }
        Ok(())
    }
}

#[derive(Debug, Clone)]
pub struct RuntimeHandle {
    pub backend: String,
    pub service_name: String,
    pub identifier: String,
    pub command: Vec<String>,
    pub started_at: f64,
    pub log_path: Option<PathBuf>,
    pub pid: Option<u32>,
}

#[derive(Debug, Clone)]
pub struct ProbeResult {
    pub backend: String,
    pub name: String,
    pub return_code: i32,
    pub stdout: String,
    pub stderr: String,
    pub log_path: Option<PathBuf>,
}

impl ProbeResult {
    pub fn ok(&self) -> bool {
        self.return_code == 0
    }
}

#[derive(Debug)]
struct ManagedProcess {
    child: Child,
}

#[derive(Debug, Clone)]
pub struct ProcessBackend {
    default_log_dir: PathBuf,
    dry_run: bool,
    managed: Arc<Mutex<BTreeMap<u32, ManagedProcess>>>,
    dry_run_handles: Arc<Mutex<BTreeSet<String>>>,
}

impl ProcessBackend {
    pub fn new(default_log_dir: impl Into<PathBuf>, dry_run: bool) -> Self {
        Self {
            default_log_dir: default_log_dir.into(),
            dry_run,
            managed: Arc::new(Mutex::new(BTreeMap::new())),
            dry_run_handles: Arc::new(Mutex::new(BTreeSet::new())),
        }
    }

    pub fn start_service(&self, spec: ServiceSpec) -> Result<RuntimeHandle, RuntimeSpecError> {
        spec.validate_for_process()?;
        let log_path = spec
            .log_path
            .clone()
            .unwrap_or_else(|| self.default_log_dir.join(format!("{}.log", spec.name)));
        if self.dry_run {
            write_text(
                &log_path,
                &format_dry_run(&spec.name, &spec.command, spec.cwd.as_deref(), &spec.env),
            )?;
            let identifier = format!("dry-run:{}", spec.name);
            self.dry_run_handles
                .lock()
                .map_err(|_| RuntimeSpecError::LockPoisoned)?
                .insert(identifier.clone());
            return Ok(RuntimeHandle {
                backend: "process".to_string(),
                service_name: spec.name,
                identifier,
                command: spec.command,
                started_at: now_epoch_sec(),
                log_path: Some(log_path),
                pid: None,
            });
        }

        let log_file = open_log_file(&log_path)?;
        let stderr_file = log_file
            .try_clone()
            .map_err(|source| RuntimeSpecError::LogPath {
                path: log_path.clone(),
                source,
            })?;
        let mut command = Command::new(&spec.command[0]);
        command.args(&spec.command[1..]);
        command.envs(&spec.env);
        if let Some(cwd) = &spec.cwd {
            command.current_dir(cwd);
        }
        command.stdout(Stdio::from(log_file));
        command.stderr(Stdio::from(stderr_file));
        #[cfg(unix)]
        {
            command.process_group(0);
        }
        let child = command
            .spawn()
            .map_err(|source| RuntimeSpecError::ServiceStart {
                name: spec.name.clone(),
                source,
            })?;
        let pid = child.id();
        self.managed
            .lock()
            .map_err(|_| RuntimeSpecError::LockPoisoned)?
            .insert(pid, ManagedProcess { child });
        Ok(RuntimeHandle {
            backend: "process".to_string(),
            service_name: spec.name,
            identifier: pid.to_string(),
            command: spec.command,
            started_at: now_epoch_sec(),
            log_path: Some(log_path),
            pid: Some(pid),
        })
    }

    pub fn run_probe(&self, spec: ProbeSpec) -> Result<ProbeResult, RuntimeSpecError> {
        spec.validate_for_process()?;
        if self.dry_run {
            let stdout = format_dry_run(&spec.name, &spec.command, spec.cwd.as_deref(), &spec.env);
            if let Some(path) = &spec.log_path {
                write_text(path, &stdout)?;
            }
            return Ok(ProbeResult {
                backend: "process".to_string(),
                name: spec.name,
                return_code: 0,
                stdout,
                stderr: String::new(),
                log_path: spec.log_path,
            });
        }

        let mut command = Command::new(&spec.command[0]);
        command.args(&spec.command[1..]);
        command.envs(&spec.env);
        if let Some(cwd) = &spec.cwd {
            command.current_dir(cwd);
        }
        command.stdout(Stdio::piped());
        command.stderr(Stdio::piped());
        #[cfg(unix)]
        {
            command.process_group(0);
        }
        let child = command
            .spawn()
            .map_err(|source| RuntimeSpecError::ProbeRun {
                name: spec.name.clone(),
                source,
            })?;
        let output = wait_probe_output(child, spec.timeout_sec).map_err(|source| {
            RuntimeSpecError::ProbeRun {
                name: spec.name.clone(),
                source,
            }
        })?;
        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        if let Some(path) = &spec.log_path {
            write_text(path, &join_output(&stdout, &stderr))?;
        }
        Ok(ProbeResult {
            backend: "process".to_string(),
            name: spec.name,
            return_code: output.status.code().unwrap_or(-1),
            stdout,
            stderr,
            log_path: spec.log_path,
        })
    }

    pub fn wait(
        &self,
        handle: &RuntimeHandle,
        timeout_sec: Option<f64>,
    ) -> Result<i32, RuntimeSpecError> {
        if self.is_dry_run_handle(&handle.identifier)? {
            return Ok(0);
        }
        let Some(pid) = handle.pid else {
            return Err(RuntimeSpecError::UnknownHandle {
                identifier: handle.identifier.clone(),
            });
        };
        let deadline = timeout_sec.map(|timeout| Instant::now() + Duration::from_secs_f64(timeout));
        loop {
            {
                let mut managed = self
                    .managed
                    .lock()
                    .map_err(|_| RuntimeSpecError::LockPoisoned)?;
                let process =
                    managed
                        .get_mut(&pid)
                        .ok_or_else(|| RuntimeSpecError::UnknownHandle {
                            identifier: handle.identifier.clone(),
                        })?;
                if let Some(status) =
                    process
                        .child
                        .try_wait()
                        .map_err(|source| RuntimeSpecError::ProbeRun {
                            name: handle.service_name.clone(),
                            source,
                        })?
                {
                    managed.remove(&pid);
                    return Ok(status.code().unwrap_or(-1));
                }
            }
            if deadline.is_some_and(|deadline| Instant::now() >= deadline) {
                return Ok(-1);
            }
            thread::sleep(Duration::from_millis(20));
        }
    }

    pub fn stop(&self, handle: &RuntimeHandle, timeout_sec: f64) -> Result<(), RuntimeSpecError> {
        if self.is_dry_run_handle(&handle.identifier)? {
            return Ok(());
        }
        let Some(pid) = handle.pid else {
            return Err(RuntimeSpecError::UnknownHandle {
                identifier: handle.identifier.clone(),
            });
        };
        terminate_process_group(pid);
        let deadline = Instant::now() + Duration::from_secs_f64(timeout_sec.max(0.0));
        loop {
            {
                let mut managed = self
                    .managed
                    .lock()
                    .map_err(|_| RuntimeSpecError::LockPoisoned)?;
                let Some(process) = managed.get_mut(&pid) else {
                    return Ok(());
                };
                if process
                    .child
                    .try_wait()
                    .map_err(|source| RuntimeSpecError::ProbeRun {
                        name: handle.service_name.clone(),
                        source,
                    })?
                    .is_some()
                {
                    managed.remove(&pid);
                    return Ok(());
                }
                if Instant::now() >= deadline {
                    kill_process_group(pid);
                    let _ = process.child.kill();
                    let _ = process.child.wait();
                    managed.remove(&pid);
                    return Ok(());
                }
            }
            thread::sleep(Duration::from_millis(20));
        }
    }

    pub fn logs(&self, handle: &RuntimeHandle, tail: usize) -> Result<String, RuntimeSpecError> {
        match &handle.log_path {
            Some(path) => tail_log(path, tail),
            None => Ok(String::new()),
        }
    }

    fn is_dry_run_handle(&self, identifier: &str) -> Result<bool, RuntimeSpecError> {
        Ok(self
            .dry_run_handles
            .lock()
            .map_err(|_| RuntimeSpecError::LockPoisoned)?
            .contains(identifier))
    }
}

fn validate_name(name: &str) -> Result<(), RuntimeSpecError> {
    if name.trim().is_empty() {
        return Err(RuntimeSpecError::EmptyName);
    }
    Ok(())
}

fn validate_env(name: &str, env: &BTreeMap<String, String>) -> Result<(), RuntimeSpecError> {
    if env.keys().any(|key| key.is_empty()) {
        return Err(RuntimeSpecError::EmptyEnvKey {
            name: name.to_string(),
        });
    }
    Ok(())
}

fn open_log_file(path: &Path) -> Result<File, RuntimeSpecError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|source| RuntimeSpecError::LogPath {
            path: parent.to_path_buf(),
            source,
        })?;
    }
    OpenOptions::new()
        .create(true)
        .truncate(true)
        .write(true)
        .open(path)
        .map_err(|source| RuntimeSpecError::LogPath {
            path: path.to_path_buf(),
            source,
        })
}

fn write_text(path: &Path, text: &str) -> Result<(), RuntimeSpecError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|source| RuntimeSpecError::LogPath {
            path: parent.to_path_buf(),
            source,
        })?;
    }
    fs::write(path, text).map_err(|source| RuntimeSpecError::LogPath {
        path: path.to_path_buf(),
        source,
    })
}

fn tail_log(path: &Path, tail: usize) -> Result<String, RuntimeSpecError> {
    let mut source = String::new();
    File::open(path)
        .map_err(|source| RuntimeSpecError::LogPath {
            path: path.to_path_buf(),
            source,
        })?
        .read_to_string(&mut source)
        .map_err(|source| RuntimeSpecError::LogPath {
            path: path.to_path_buf(),
            source,
        })?;
    if tail == 0 {
        return Ok(String::new());
    }
    let lines: Vec<&str> = source.lines().collect();
    let start = lines.len().saturating_sub(tail);
    Ok(lines[start..].join("\n"))
}

fn format_dry_run(
    name: &str,
    command: &[String],
    cwd: Option<&Path>,
    env: &BTreeMap<String, String>,
) -> String {
    format!(
        "dry-run service={name}\ncwd={}\nenv={env:?}\ncommand={}\n",
        cwd.map(|path| path.display().to_string())
            .unwrap_or_else(|| "<inherit>".to_string()),
        command.join(" ")
    )
}

fn join_output(stdout: &str, stderr: &str) -> String {
    if stderr.is_empty() {
        stdout.to_string()
    } else {
        format!("{stdout}\n--- stderr ---\n{stderr}")
    }
}

fn wait_probe_output(
    mut child: Child,
    timeout_sec: Option<f64>,
) -> Result<std::process::Output, std::io::Error> {
    let Some(timeout_sec) = timeout_sec else {
        return child.wait_with_output();
    };
    let deadline = Instant::now() + Duration::from_secs_f64(timeout_sec);
    loop {
        if child.try_wait()?.is_some() {
            return child.wait_with_output();
        }
        if Instant::now() >= deadline {
            terminate_process_group(child.id());
            let _ = child.kill();
            return child.wait_with_output();
        }
        thread::sleep(Duration::from_millis(20));
    }
}

fn now_epoch_sec() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs_f64())
        .unwrap_or_default()
}

#[cfg(unix)]
fn terminate_process_group(pid: u32) {
    unsafe {
        libc::killpg(pid as libc::pid_t, libc::SIGTERM);
    }
}

#[cfg(not(unix))]
fn terminate_process_group(_pid: u32) {}

#[cfg(unix)]
fn kill_process_group(pid: u32) {
    unsafe {
        libc::killpg(pid as libc::pid_t, libc::SIGKILL);
    }
}

#[cfg(not(unix))]
fn kill_process_group(_pid: u32) {}

#[cfg(test)]
mod tests {
    use super::*;

    fn rust_exe() -> String {
        std::env::var("CARGO").unwrap_or_else(|_| "cargo".to_string())
    }

    #[test]
    fn service_spec_requires_command() {
        let error = ServiceSpec {
            name: "companion".to_string(),
            command: vec![],
            image: None,
            env: BTreeMap::new(),
            cwd: None,
            required: true,
            log_path: None,
        }
        .validate_for_process()
        .expect_err("error");

        assert!(
            error
                .to_string()
                .contains("process backend requires command")
        );
    }

    #[test]
    fn service_spec_rejects_image() {
        let error = ServiceSpec {
            name: "companion".to_string(),
            command: vec!["echo".to_string(), "ok".to_string()],
            image: Some("image:tag".to_string()),
            env: BTreeMap::new(),
            cwd: None,
            required: true,
            log_path: None,
        }
        .validate_for_process()
        .expect_err("error");

        assert!(error.to_string().contains("does not accept image"));
    }

    #[test]
    fn process_backend_dry_run_does_not_start_process() {
        let temp = tempfile::tempdir().expect("tempdir");
        let backend = ProcessBackend::new(temp.path(), true);
        let handle = backend
            .start_service(ServiceSpec {
                name: "dry".to_string(),
                command: vec!["echo".to_string(), "ok".to_string()],
                image: None,
                env: BTreeMap::new(),
                cwd: None,
                required: true,
                log_path: None,
            })
            .expect("handle");

        assert_eq!(handle.identifier, "dry-run:dry");
        assert_eq!(backend.wait(&handle, None).expect("wait"), 0);
        assert!(
            fs::read_to_string(temp.path().join("dry.log"))
                .expect("log")
                .contains("command=echo ok")
        );
    }

    #[test]
    fn process_backend_runs_probe_and_writes_log() {
        let temp = tempfile::tempdir().expect("tempdir");
        let log_path = temp.path().join("probe.log");
        let backend = ProcessBackend::new(temp.path(), false);
        let result = backend
            .run_probe(ProbeSpec {
                name: "hello".to_string(),
                command: vec![
                    "sh".to_string(),
                    "-c".to_string(),
                    "printf 'hello process\\n'".to_string(),
                ],
                image: None,
                env: BTreeMap::new(),
                cwd: None,
                timeout_sec: Some(5.0),
                log_path: Some(log_path.clone()),
                required: true,
            })
            .expect("probe");

        assert!(result.ok());
        assert!(result.stdout.contains("hello process"));
        assert!(
            fs::read_to_string(log_path)
                .expect("log")
                .contains("hello process")
        );
    }

    #[test]
    fn process_backend_starts_waits_and_tails_service_log() {
        let temp = tempfile::tempdir().expect("tempdir");
        let backend = ProcessBackend::new(temp.path(), false);
        let handle = backend
            .start_service(ServiceSpec {
                name: "short".to_string(),
                command: vec![
                    "sh".to_string(),
                    "-c".to_string(),
                    "printf 'line1\\nline2\\n'".to_string(),
                ],
                image: None,
                env: BTreeMap::new(),
                cwd: None,
                required: true,
                log_path: Some(temp.path().join("short.log")),
            })
            .expect("handle");

        assert_eq!(handle.backend, "process");
        assert!(handle.pid.is_some());
        assert_eq!(backend.wait(&handle, Some(5.0)).expect("wait"), 0);
        assert_eq!(backend.logs(&handle, 1).expect("logs"), "line2");
    }

    #[test]
    fn process_backend_wait_returns_nonzero_rc() {
        let temp = tempfile::tempdir().expect("tempdir");
        let backend = ProcessBackend::new(temp.path(), false);
        let handle = backend
            .start_service(ServiceSpec {
                name: "failing".to_string(),
                command: vec!["sh".to_string(), "-c".to_string(), "exit 13".to_string()],
                image: None,
                env: BTreeMap::new(),
                cwd: None,
                required: true,
                log_path: Some(temp.path().join("failing.log")),
            })
            .expect("handle");

        assert_eq!(backend.wait(&handle, Some(5.0)).expect("wait"), 13);
    }

    #[test]
    fn process_backend_stop_terminates_service() {
        let temp = tempfile::tempdir().expect("tempdir");
        let backend = ProcessBackend::new(temp.path(), false);
        let handle = backend
            .start_service(ServiceSpec {
                name: "sleeping".to_string(),
                command: vec!["sh".to_string(), "-c".to_string(), "sleep 30".to_string()],
                image: None,
                env: BTreeMap::new(),
                cwd: None,
                required: true,
                log_path: Some(temp.path().join("sleeping.log")),
            })
            .expect("handle");

        backend.stop(&handle, 0.2).expect("stop");
        assert!(
            matches!(
                backend.wait(&handle, Some(0.1)),
                Err(RuntimeSpecError::UnknownHandle { .. })
            ),
            "stopped handle should be removed"
        );
    }

    #[test]
    fn probe_timeout_kills_process() {
        let temp = tempfile::tempdir().expect("tempdir");
        let backend = ProcessBackend::new(temp.path(), false);
        let result = backend
            .run_probe(ProbeSpec {
                name: "timeout".to_string(),
                command: vec!["sh".to_string(), "-c".to_string(), "sleep 5".to_string()],
                image: None,
                env: BTreeMap::new(),
                cwd: None,
                timeout_sec: Some(0.05),
                log_path: None,
                required: true,
            })
            .expect("probe");

        assert!(!result.ok());
    }

    #[test]
    fn empty_env_key_is_rejected() {
        let mut env = BTreeMap::new();
        env.insert(String::new(), "bad".to_string());
        let error = ProbeSpec {
            name: "probe".to_string(),
            command: vec![rust_exe()],
            image: None,
            env,
            cwd: None,
            timeout_sec: Some(1.0),
            log_path: None,
            required: true,
        }
        .validate_for_process()
        .expect_err("error");

        assert!(error.to_string().contains("env keys"));
    }
}
