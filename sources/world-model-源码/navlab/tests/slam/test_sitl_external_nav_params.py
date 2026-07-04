from __future__ import annotations

from pathlib import Path


def _load_params() -> dict[str, str]:
    params: dict[str, str] = {}
    for raw_line in Path("docker/profiles/navlab-sitl-external-nav.parm").read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split(maxsplit=1)
        params[key] = value
    return params


def test_sitl_external_nav_uses_debug_param_external_nav_prearm_profile() -> None:
    params = _load_params()

    assert params["GPS1_TYPE"] == "0"
    assert params["AHRS_EKF_TYPE"] == "3"
    assert params["VISO_TYPE"] == "1"
    assert params["ARMING_CHECK"] == "1043902"
    assert params["EK3_GPS_CHECK"] == "0"
    assert params["EK3_SRC1_POSXY"] == "6"
    assert params["EK3_SRC1_POSZ"] == "2"
    assert params["EK3_SRC1_VELXY"] == "0"
    assert params["EK3_SRC1_VELZ"] == "0"
    assert params["EK3_SRC1_YAW"] == "1"
    assert params["SCR_ENABLE"] == "1"
    assert params["AHRS_ORIG_LAT"] == "-35.363262"
    assert params["AHRS_ORIG_LON"] == "149.165237"
    assert params["AHRS_ORIG_ALT"] == "584"


def test_sitl_external_nav_disables_gps1_without_gps1_transport_params() -> None:
    params = _load_params()

    assert params["GPS1_TYPE"] == "0"
    for key in (
        "GPS1_COM_PORT",
        "GPS1_DELAY_MS",
        "GPS1_GNSS_MODE",
        "GPS1_MB_TYPE",
        "GPS1_POS_X",
        "GPS1_POS_Y",
        "GPS1_POS_Z",
        "GPS1_RATE_MS",
    ):
        assert key not in params


def test_down_rangefinder_uses_real_benewake_serial_profile() -> None:
    params = _load_params()

    assert params["EK3_RNG_USE_HGT"] == "-1"
    assert params["SERIAL7_BAUD"] == "115"
    assert params["SERIAL7_OPTIONS"] == "0"
    assert params["SERIAL7_PROTOCOL"] == "9"
    assert params["RNGFND1_PIN"] == "-1"
    assert params["RNGFND1_SCALING"] == "3"
    assert params["RNGFND1_OFFSET"] == "0"
    assert params["RNGFND1_TYPE"] == "20"
    assert params["RNGFND1_MIN_CM"] == "10"
    assert params["RNGFND1_MAX_CM"] == "1200"
    assert params["RNGFND1_GNDCLEAR"] == "15"
    assert params["RNGFND1_ORIENT"] == "25"
    assert params["RNGFND1_POS_X"] == "0"
    assert params["RNGFND1_POS_Y"] == "0"
    assert params["RNGFND1_POS_Z"] == "0"
    assert params["EK3_SRC1_POSZ"] == "2"


def test_sitl_lua_origin_script_is_runtime_profile_input() -> None:
    script = Path("docker/profiles/ahrs-set-origin.lua")

    assert script.exists()
    assert not Path("docs/ahrs-set-origin.lua").exists()

    text = script.read_text(encoding="utf-8")
    assert "param:get(name)" in text
    assert 'param_or_default("AHRS_ORIG_LAT"' in text
    assert 'param_or_default("AHRS_ORIG_LON"' in text
    assert 'param_or_default("AHRS_ORIG_ALT"' in text
    assert "param:add_table" not in text
    assert "param:add_param" not in text
    assert "DEFAULT_AHRS_ORIG_LAT = -35.363262" in text
    assert "DEFAULT_AHRS_ORIG_LON = 149.165237" in text
    assert "DEFAULT_AHRS_ORIG_ALT = 584" in text
    assert "sitl_work/scripts" in text
