from __future__ import annotations

import json
from typing import Any

DEFAULT_SIM_LOG_TOPIC = "/sim/log"


def encode_sim_log(*, source: str, event: str, **fields: Any) -> str:
    payload = {"source": source, "event": event, **fields}
    return json.dumps(payload, ensure_ascii=True)
