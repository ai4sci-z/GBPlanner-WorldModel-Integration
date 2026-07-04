use anyhow::Result;
use clap::Parser;
use navlab_real_orchestration::cli::{Cli, run};

#[tokio::main]
async fn main() -> Result<()> {
    run(Cli::parse()).await
}
