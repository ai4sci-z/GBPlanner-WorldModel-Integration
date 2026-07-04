from __future__ import annotations

import math

from navlab.sim.gazebo_sensor.x2.scan_source import IdealLaserScan, resample_ideal_scan_to_x2_samples


def test_resample_ideal_scan_uses_ros_front_left_rear_right_angles() -> None:
    scan = IdealLaserScan(
        ranges=(5.0, 2.0, 1.0, 3.0, 5.0),
        angle_min_rad=-math.pi,
        angle_increment_rad=math.pi / 2.0,
    )

    samples = resample_ideal_scan_to_x2_samples(
        scan,
        sample_count=4,
        range_min_m=0.1,
        range_max_m=8.0,
    )

    assert [sample.angle_deg for sample in samples] == [0.0, 90.0, 180.0, 270.0]
    assert [sample.range_m for sample in samples] == [1.0, 3.0, 5.0, 2.0]


def test_resample_ideal_scan_keeps_front_obstacle_at_zero_degrees() -> None:
    scan = IdealLaserScan(
        ranges=(8.0, 8.0, 1.2, 8.0, 8.0),
        angle_min_rad=-math.pi,
        angle_increment_rad=math.pi / 2.0,
    )

    samples = resample_ideal_scan_to_x2_samples(
        scan,
        sample_count=4,
        range_min_m=0.1,
        range_max_m=8.0,
    )

    assert samples[0].angle_deg == 0.0
    assert samples[0].range_m == 1.2


def test_resample_ideal_scan_clamps_ranges_and_keeps_invalid_as_nan() -> None:
    scan = IdealLaserScan(
        ranges=(math.inf, -1.0, 12.0, 4.0, 5.0),
        angle_min_rad=-math.pi,
        angle_increment_rad=math.pi / 2.0,
    )

    samples = resample_ideal_scan_to_x2_samples(
        scan,
        sample_count=4,
        range_min_m=0.1,
        range_max_m=8.0,
    )

    assert samples[0].range_m == 8.0
    assert samples[1].range_m == 4.0
    assert math.isnan(samples[2].range_m)
    assert samples[3].range_m == 0.1


def test_resample_ideal_scan_dropout_is_configurable() -> None:
    scan = IdealLaserScan(
        ranges=(1.0, 1.0, 1.0, 1.0),
        angle_min_rad=0.0,
        angle_increment_rad=math.pi / 2.0,
    )

    samples = resample_ideal_scan_to_x2_samples(
        scan,
        sample_count=4,
        range_min_m=0.1,
        range_max_m=8.0,
        dropout_rate=1.0,
        random_seed=7,
    )

    assert all(math.isnan(sample.range_m) for sample in samples)


def test_resample_ideal_scan_distance_related_noise_is_seeded() -> None:
    scan = IdealLaserScan(
        ranges=(1.0, 5.0),
        angle_min_rad=-math.pi,
        angle_increment_rad=math.pi,
    )

    first = resample_ideal_scan_to_x2_samples(
        scan,
        sample_count=2,
        range_min_m=0.1,
        range_max_m=8.0,
        noise_stddev_per_m=0.05,
        random_seed=1,
    )
    second = resample_ideal_scan_to_x2_samples(
        scan,
        sample_count=2,
        range_min_m=0.1,
        range_max_m=8.0,
        noise_stddev_per_m=0.05,
        random_seed=1,
    )

    assert [sample.range_m for sample in first] == [sample.range_m for sample in second]
    assert first[0].range_m != 1.0
    assert first[1].range_m != 5.0
