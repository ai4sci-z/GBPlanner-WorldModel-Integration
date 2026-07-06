#!/usr/bin/env python3
# 打印最新 run 的 model_overlay.sdf 中所有 sensor 块概要(名字/类型/topic/水平垂直样本)。
import glob
import os
import re
import sys

base = "/home/ai4s/ws-clean/world-model/artifacts/sim/exploration"
run = sys.argv[1] if len(sys.argv) > 1 else sorted(os.listdir(base))[-1]
path = os.path.join(base, run, "runtime", "config", "model_overlay.sdf")
print("file:", path)
text = open(path, encoding="utf-8").read()
print("total model name(s):", re.findall(r'<model name=.([^"\']+).', text)[:3])
print("includes:", re.findall(r"<uri>model://([^<]+)</uri>", text))
for m in re.finditer(r'<sensor name=.([^"\']+). type=.([^"\']+).>(.*?)</sensor>', text, re.S):
    name, typ, body = m.groups()
    topic = re.search(r"<topic>([^<]+)</topic>", body)
    hs = re.search(r"<horizontal>.*?<samples>(\d+)</samples>", body, re.S)
    vs = re.search(r"<vertical>.*?<samples>(\d+)</samples>", body, re.S)
    vmin = re.search(r"<vertical>.*?<min_angle>([-\d.]+)</min_angle>", body, re.S)
    vmax = re.search(r"<vertical>.*?<max_angle>([-\d.]+)</max_angle>", body, re.S)
    print("sensor=%-22s type=%-12s topic=%-30s hsamples=%s vsamples=%s vrange=[%s,%s]" % (
        name, typ, topic.group(1) if topic else "-",
        hs.group(1) if hs else "-", vs.group(1) if vs else "-",
        vmin.group(1) if vmin else "-", vmax.group(1) if vmax else "-"))
