#[derive(Debug, thiserror::Error)]
pub enum RealOrchestrationError {
    #[error("unknown real task {0:?}")]
    UnknownTask(String),

    #[error("unknown real task config {0:?}")]
    UnknownTaskConfig(String),
}
