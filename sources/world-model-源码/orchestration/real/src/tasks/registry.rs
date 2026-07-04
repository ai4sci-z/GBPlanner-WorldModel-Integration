use std::collections::BTreeMap;
use std::sync::Arc;

use anyhow::Result;

use crate::config::TaskConfig;
use crate::errors::RealOrchestrationError;
use crate::tasks::{ConfiguredTask, MotorDebugTask, RealHoverTask, RealTask};

#[derive(Clone)]
pub struct Registry {
    tasks: BTreeMap<&'static str, Arc<dyn RealTask>>,
}

impl Default for Registry {
    fn default() -> Self {
        let mut registry = Self {
            tasks: BTreeMap::new(),
        };
        registry.register(MotorDebugTask);
        registry.register(RealHoverTask);
        registry
    }
}

impl Registry {
    pub fn register<T>(&mut self, task: T)
    where
        T: RealTask + 'static,
    {
        self.tasks.insert(task.id(), Arc::new(task));
    }

    pub fn create(&self, task_id: &str) -> Option<Arc<dyn RealTask>> {
        self.tasks.get(task_id.trim()).cloned()
    }

    pub fn configure(&self, configs: &[TaskConfig]) -> Result<Vec<ConfiguredTask>> {
        let mut configured = Vec::new();
        for config in configs {
            if !self.tasks.contains_key(config.id.as_str()) {
                return Err(RealOrchestrationError::UnknownTaskConfig(config.id.clone()).into());
            }
            configured.push(ConfiguredTask {
                id: config.id.clone(),
                family: config.family.clone(),
                description: config.description.clone(),
                capabilities: config.capabilities.clone(),
            });
        }
        Ok(configured)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_exposes_motor_debug_and_hover() {
        let registry = Registry::default();
        assert!(registry.create("motor-debug").is_some());
        assert!(registry.create("hover").is_some());
        assert!(registry.create("unknown").is_none());
    }
}
