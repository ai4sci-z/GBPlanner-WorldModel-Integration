#pragma once
// ROS1 logging macro shims for the ROS-free gbplanner core (M3).
// Same names and printf-style semantics as rosconsole so the 200+ call
// sites vendor over unchanged; output goes to stderr.
#include <chrono>
#include <cstdio>

#define GBC_LOG_(tag, ...)                  \
  do {                                      \
    std::fprintf(stderr, "[" tag "] ");     \
    std::fprintf(stderr, __VA_ARGS__);      \
    std::fprintf(stderr, "\n");             \
  } while (0)

#define ROS_DEBUG(...) GBC_LOG_("DEBUG", __VA_ARGS__)
#define ROS_INFO(...) GBC_LOG_("INFO", __VA_ARGS__)
#define ROS_WARN(...) GBC_LOG_("WARN", __VA_ARGS__)
#define ROS_ERROR(...) GBC_LOG_("ERROR", __VA_ARGS__)
#define ROS_FATAL(...) GBC_LOG_("FATAL", __VA_ARGS__)

#define ROS_INFO_COND(cond, ...) \
  do {                           \
    if (cond) ROS_INFO(__VA_ARGS__); \
  } while (0)
#define ROS_WARN_COND(cond, ...) \
  do {                           \
    if (cond) ROS_WARN(__VA_ARGS__); \
  } while (0)
#define ROS_ERROR_COND(cond, ...) \
  do {                            \
    if (cond) ROS_ERROR(__VA_ARGS__); \
  } while (0)

// Per-call-site wall-clock throttle, matching rosconsole behaviour closely
// enough for the two call sites the core has.
#define ROS_WARN_THROTTLE(period_sec, ...)                                   \
  do {                                                                       \
    static std::chrono::steady_clock::time_point gbc_last_;                  \
    const auto gbc_now_ = std::chrono::steady_clock::now();                  \
    if (gbc_now_ - gbc_last_ >=                                              \
        std::chrono::duration_cast<std::chrono::steady_clock::duration>(    \
            std::chrono::duration<double>(period_sec))) {                    \
      gbc_last_ = gbc_now_;                                                  \
      ROS_WARN(__VA_ARGS__);                                                 \
    }                                                                        \
  } while (0)
