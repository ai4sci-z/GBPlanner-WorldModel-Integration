use criterion::{Criterion, criterion_group, criterion_main};
use navlab_real_orchestration::config::TaskConfig;
use navlab_real_orchestration::tasks::{MotorDebugOverrides, build_motor_debug_plan};
use serde_json::json;

fn task_config() -> TaskConfig {
    TaskConfig {
        id: "motor-debug".to_string(),
        family: "real".to_string(),
        description: "bench".to_string(),
        capabilities: vec![],
        task: serde_json::from_value(json!({
            "motor_percent": 5.0,
            "motor_sec": 5.0,
            "motor_count": 4
        }))
        .expect("task map"),
        safety: serde_json::from_value(json!({
            "confirm_manual_takeover": true,
            "confirm_kill_switch": true,
            "confirm_safe_area": true,
            "confirm_no_props": true
        }))
        .expect("safety map"),
    }
}

fn bench_motor_debug_plan(c: &mut Criterion) {
    let config = task_config();
    c.bench_function("motor_debug_plan", |b| {
        b.iter(|| build_motor_debug_plan(&config, MotorDebugOverrides::default()).expect("plan"))
    });
}

criterion_group!(benches, bench_motor_debug_plan);
criterion_main!(benches);
