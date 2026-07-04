use std::fs;
use std::path::{Path, PathBuf};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let manifest_dir = PathBuf::from(std::env::var("CARGO_MANIFEST_DIR")?);
    let repo_root = manifest_dir
        .parent()
        .and_then(Path::parent)
        .and_then(Path::parent)
        .ok_or("failed to resolve repository root")?;
    let proto_dir = repo_root.join("contracts").join("proto");
    let mut protos = Vec::new();
    collect_proto_files(&proto_dir, &mut protos)?;
    protos.sort();

    for proto in &protos {
        println!("cargo:rerun-if-changed={}", proto.display());
    }
    println!("cargo:rerun-if-changed={}", proto_dir.display());

    prost_build::Config::new().compile_protos(&protos, &[proto_dir])?;
    Ok(())
}

fn collect_proto_files(dir: &Path, protos: &mut Vec<PathBuf>) -> std::io::Result<()> {
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            collect_proto_files(&path, protos)?;
        } else if path
            .extension()
            .is_some_and(|extension| extension == "proto")
        {
            protos.push(path);
        }
    }
    Ok(())
}
