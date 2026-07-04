FROM ubuntu:24.04 AS mavlink-router-build

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    git \
    meson \
    ninja-build \
    pkg-config \
    python3 \
    && rm -rf /var/lib/apt/lists/*

COPY third_party/mavlink-router /tmp/mavlink-router
WORKDIR /tmp/mavlink-router
RUN test -f meson.build \
    || (echo "mavlink-router source missing: initialize submodule at mavlink-router/" >&2; exit 2)
RUN meson setup -Dsystemdsystemunitdir=/usr/lib/systemd/system --buildtype=release build \
    && ninja -C build \
    && ninja -C build install

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    iproute2 \
    net-tools \
    procps \
    && rm -rf /var/lib/apt/lists/*

COPY --from=mavlink-router-build /usr/bin/mavlink-routerd /usr/bin/mavlink-routerd

WORKDIR /workspace
