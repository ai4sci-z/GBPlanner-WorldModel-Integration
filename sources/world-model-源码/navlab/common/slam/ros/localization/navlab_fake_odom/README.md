# navlab_fake_odom

Deterministic odometry publisher for isolated bridge smoke tests.

This package is not part of the real SLAM feedback path. Use it only when you
want to verify downstream `/odom -> /external_nav/odom` behavior without
Cartographer.

Example:

```bash
ros2 launch navlab_fake_odom navlab_fake_odom.launch.py mode:=line
```
