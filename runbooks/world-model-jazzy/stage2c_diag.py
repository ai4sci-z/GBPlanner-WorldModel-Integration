#!/usr/bin/env python3
# 阶段2c 诊断:查 zenoh-bridge-ros1 可用 tags(docker hub API)。
import json, urllib.request

url = "https://registry.hub.docker.com/v2/repositories/eclipse/zenoh-bridge-ros1/tags?page_size=25"
try:
    with urllib.request.urlopen(url, timeout=20) as r:
        d = json.load(r)
    for t in d.get("results", []):
        print(t.get("name"), " updated:", str(t.get("last_updated", ""))[:10])
except Exception as exc:
    print("HUB_QUERY_FAILED:", exc)
