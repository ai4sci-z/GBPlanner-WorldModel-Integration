#!/usr/bin/env python3
# 把干净版 backends.py 的 CartographerBackend.command 改成跳过空 launch 参数(49d3551 修法)。
import io
p = "/home/ai4s/ws-clean/world-model/navlab/common/slam/backends.py"
s = open(p, encoding="utf-8").read()
old = '        launch_args = [f"{key}:={launch_value(value)}" for key, value in config.launch_argument_map().items()]'
new = (
    "        launch_args = []\n"
    "        for key, value in config.launch_argument_map().items():\n"
    "            rendered = launch_value(value)\n"
    "            if rendered == \"\":\n"
    "                # ROS 2 launch rejects empty 'name:=' arguments (e.g. an unset\n"
    "                # cartographer_configuration_directory); omit them so the launch\n"
    "                # file's own default value is used instead. (jazzy rejects too)\n"
    "                continue\n"
    "            launch_args.append(f\"{key}:={rendered}\")"
)
if old not in s:
    print("PATTERN_NOT_FOUND"); raise SystemExit(2)
s = s.replace(old, new)
open(p, "w", encoding="utf-8").write(s)
print("PATCHED")
# 验证语法
import py_compile
py_compile.compile(p, doraise=True)
print("PY_COMPILE_OK")
