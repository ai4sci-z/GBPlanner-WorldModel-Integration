use std::path::PathBuf;

use clap::ValueEnum;

#[derive(Debug, Clone, Copy, ValueEnum)]
pub enum LogFormat {
    Human,
    Json,
}

#[derive(Debug, Clone, Copy, ValueEnum)]
pub enum LogRotation {
    Never,
    Hourly,
    Daily,
}

#[derive(Debug, Clone)]
pub struct LoggingConfig {
    pub level: String,
    pub format: LogFormat,
    pub file_enabled: bool,
    pub directory: PathBuf,
    pub rotation: LogRotation,
    pub file_prefix: String,
}
