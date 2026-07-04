-- Sets the AHRS/EKF origin to a specified Location.
--
-- SITL loads Lua scripts from the "scripts" directory under the simulator
-- working directory when SCR_ENABLE=1. The Go sim runtime copies this profile
-- script into sitl_work/scripts before launching ArduPilot.

local MAV_SEVERITY = {EMERGENCY=0, ALERT=1, CRITICAL=2, ERROR=3, WARNING=4, NOTICE=5, INFO=6, DEBUG=7}
local SEND_TEXT_PREFIX = "ahrs-set-origin: "
local DEFAULT_AHRS_ORIG_LAT = -35.363262
local DEFAULT_AHRS_ORIG_LON = 149.165237
local DEFAULT_AHRS_ORIG_ALT = 584

local function param_or_default(name, default_value)
    local value = param:get(name)
    if value == nil then
        return default_value
    end
    return value
end

gcs:send_text(MAV_SEVERITY.INFO, SEND_TEXT_PREFIX .. "started")

function update()
    if not ahrs:initialised() then
        return update, 5000
    end

    if ahrs:get_origin() then
        gcs:send_text(MAV_SEVERITY.WARNING, SEND_TEXT_PREFIX .. "EKF origin already set")
        return
    end

    local origin_lat = param_or_default("AHRS_ORIG_LAT", DEFAULT_AHRS_ORIG_LAT)
    local origin_lon = param_or_default("AHRS_ORIG_LON", DEFAULT_AHRS_ORIG_LON)
    local origin_alt = param_or_default("AHRS_ORIG_ALT", DEFAULT_AHRS_ORIG_ALT)

    if origin_lat == 0 and origin_lon == 0 and origin_alt == 0 then
        return update, 5000
    end

    local location = Location()
    location:lat(math.floor(origin_lat * 10000000.0))
    location:lng(math.floor(origin_lon * 10000000.0))
    location:alt(math.floor(origin_alt * 100.0))

    if ahrs:set_origin(location) then
        gcs:send_text(MAV_SEVERITY.INFO, string.format(SEND_TEXT_PREFIX .. "origin set Lat:%.7f Lon:%.7f Alt:%.1f", origin_lat, origin_lon, origin_alt))
    else
        gcs:send_text(MAV_SEVERITY.WARNING, SEND_TEXT_PREFIX .. "failed to set origin")
    end

    return
end

return update()
