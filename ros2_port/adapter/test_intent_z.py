#!/usr/bin/env python3
"""M5 z闭环 adapter 侧纯函数 intent_z 的单元测试(纯函数级,不 import rclpy)。

trajectory_to_intent.py 模块级 import rclpy,宿主未必装 ROS;
故用 ast 只抽取 intent_z 函数定义执行,测试与 ROS 运行时完全解耦。
"""
import ast
import math
import pathlib

_SRC_PATH = pathlib.Path(__file__).with_name("trajectory_to_intent.py")
_tree = ast.parse(_SRC_PATH.read_text(encoding="utf-8"))
_fn = next(n for n in _tree.body
           if isinstance(n, ast.FunctionDef) and n.name == "intent_z")
_ns = {}
exec(compile(ast.Module(body=[_fn], type_ignores=[]), str(_SRC_PATH), "exec"), _ns)
intent_z = _ns["intent_z"]


# 1) 有 z:运动 intent 带当前目标航点 z
def test_motion_with_valid_z():
    assert intent_z(1.2, None) == 1.2
    # 有 wp_z 时优先 wp_z,不用 last_z
    assert intent_z(2.0, 0.8) == 2.0
    # 边界内典型规划高度
    assert intent_z(0.5, None) == 0.5


# 2) 无 z(从未有):不带字段
def test_never_had_z_returns_none():
    assert intent_z(None, None) is None


# 3) hold 保持 last_z:无当前目标但 last_z 已知
def test_hold_keeps_last_z():
    assert intent_z(None, 0.8) == 0.8


# 4) 异常值:NaN / None / 负数 / 非数值 / 边界外
def test_nan_excluded_by_comparison_chain():
    # NaN 任何比较为 False,天然被 sanity 链排除
    assert intent_z(float("nan"), None) is None
    # NaN wp_z 不得污染:回退 last_z
    assert intent_z(float("nan"), 0.9) == 0.9
    # last_z 也为 NaN(防御,正常路径不会写入)→ 不带字段
    assert intent_z(float("nan"), float("nan")) is None


def test_negative_z_rejected():
    assert intent_z(-0.5, None) is None
    # 负数 wp_z 回退 last_z,不把悬停高度打回默认
    assert intent_z(-0.5, 1.1) == 1.1


def test_non_numeric_rejected():
    assert intent_z("abc", None) is None
    assert intent_z(object(), None) is None
    assert intent_z("abc", 0.7) == 0.7


def test_sanity_bounds():
    # 与控制器侧 sanity 同口径:0.05 < z < 100(开区间)
    assert intent_z(0.05, None) is None
    assert intent_z(100.0, None) is None
    assert intent_z(0.06, None) == 0.06
    assert intent_z(99.9, None) == 99.9
    # 超界 wp_z 回退 last_z
    assert intent_z(150.0, 1.5) == 1.5


def test_returns_float_type():
    z = intent_z(1, None)  # int 可转 float
    assert isinstance(z, float) and z == 1.0
    z2 = intent_z(None, "1.5")  # 可转 float 的字符串(防御)
    assert isinstance(z2, float) and math.isclose(z2, 1.5)

def test_disabled_gate_contract_note():
    """对抗验证修正契约:z_m 附带被 (enabled and not killed) 门控(见 trajectory_to_intent.py
    z_m 附带处)。纯函数 intent_z 本身与门控无关——本用例锚定该契约存在,防止回归时删除门控。"""
    import re
    src = open(__file__.replace("test_intent_z.py", "trajectory_to_intent.py")).read()
    assert re.search(r"if self\.enabled and not self\.killed:\s*\n\s*z_m = intent_z", src), \
        "z_m 附带必须由 enabled/killed 门控包裹(对抗验证 2026-07-28)"
