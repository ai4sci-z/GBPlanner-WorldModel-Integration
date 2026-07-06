#!/usr/bin/env python3
# 修死锁:起飞完成前,别把探索工作流的 setpoint/intent 转发给飞控(cmd_vel/位置保持),
# 否则"保持当前位置"指令覆盖 GUIDED takeoff 爬升(CTUN.DAlt 被摁在当前高度)→永不起飞→
# 控制器永不ready→工作流永远发hold intent→死循环。加 bootstrap_ready 门破锁。
p = "/home/ai4s/ws-clean/world-model/orchestration/sim/internal/tasks/helpers/templates/python/fcu_controller_runtime.py.tmpl"
s = open(p, encoding="utf-8").read()

old = '''        state["setpoint_intent"] = payload
        state["setpoint_intent_count"] += 1
        state["last_setpoint_intent_ms"] = int(time.time() * 1000)
        publish_cmd_vel_from_intent(payload)
        send_mavlink_local_position_setpoint(payload)'''

new = '''        state["setpoint_intent"] = payload
        state["setpoint_intent_count"] += 1
        state["last_setpoint_intent_ms"] = int(time.time() * 1000)
        # Do not forward exploration intent to the FCU until takeoff has
        # completed. Before takeoff the intent is a stationary "hold" that,
        # forwarded as cmd_vel / local-position setpoint, overrides the GUIDED
        # takeoff climb (CTUN.DAlt pinned to the current altitude) so the
        # vehicle never leaves the ground; takeoff then never reports ok, the
        # controller never becomes ready and the workflow keeps emitting hold
        # intent -- a deadlock. Only forward once the FCU bootstrap (incl.
        # takeoff) is ready.
        if bootstrap_ready(state):
            publish_cmd_vel_from_intent(payload)
            send_mavlink_local_position_setpoint(payload)'''

assert old in s, "anchor not found"
assert s.count(old) == 1, f"count={s.count(old)}"
s = s.replace(old, new)
open(p, "w", encoding="utf-8").write(s)
print("PATCHED on_setpoint_intent with bootstrap_ready gate")
