use std::sync::OnceLock;

use anyhow::Result;
use tracing_appender::non_blocking::WorkerGuard;
use tracing_subscriber::{EnvFilter, fmt, layer::SubscriberExt, util::SubscriberInitExt};

use super::{LogFormat, LogRotation, LoggingConfig};

static LOG_GUARD: OnceLock<WorkerGuard> = OnceLock::new();

pub fn init_logging(config: LoggingConfig) -> Result<()> {
    let env_filter =
        EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new(config.level.clone()));

    match (config.format, config.file_enabled) {
        (LogFormat::Human, false) => tracing_subscriber::registry()
            .with(env_filter)
            .with(fmt::layer().compact())
            .try_init()?,
        (LogFormat::Json, false) => tracing_subscriber::registry()
            .with(env_filter)
            .with(fmt::layer().json())
            .try_init()?,
        (LogFormat::Human, true) => {
            let (writer, guard) = rolling_writer(&config);
            let _ = LOG_GUARD.set(guard);
            tracing_subscriber::registry()
                .with(env_filter)
                .with(fmt::layer().compact())
                .with(fmt::layer().with_writer(writer))
                .try_init()?;
        }
        (LogFormat::Json, true) => {
            let (writer, guard) = rolling_writer(&config);
            let _ = LOG_GUARD.set(guard);
            tracing_subscriber::registry()
                .with(env_filter)
                .with(fmt::layer().json())
                .with(fmt::layer().json().with_writer(writer))
                .try_init()?;
        }
    }
    Ok(())
}

fn rolling_writer(
    config: &LoggingConfig,
) -> (tracing_appender::non_blocking::NonBlocking, WorkerGuard) {
    let appender = match config.rotation {
        LogRotation::Never => {
            tracing_appender::rolling::never(&config.directory, &config.file_prefix)
        }
        LogRotation::Hourly => {
            tracing_appender::rolling::hourly(&config.directory, &config.file_prefix)
        }
        LogRotation::Daily => {
            tracing_appender::rolling::daily(&config.directory, &config.file_prefix)
        }
    };
    tracing_appender::non_blocking(appender)
}
