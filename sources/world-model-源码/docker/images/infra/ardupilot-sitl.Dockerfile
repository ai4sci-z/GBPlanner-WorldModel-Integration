FROM ubuntu:24.04 AS ardupilot-sitl-build

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    ccache \
    cmake \
    curl \
    g++ \
    gawk \
    gcc \
    genromfs \
    git \
    iproute2 \
    libtool \
    libxml2-dev \
    libxslt1-dev \
    make \
    net-tools \
    pkg-config \
    procps \
    python3 \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-venv \
    python3-wheel \
    python3-lxml \
    python3-numpy \
    python3-pexpect \
    python3-serial \
    python3-yaml \
    && python3 -m pip install --break-system-packages --no-cache-dir \
    dronecan \
    empy==3.3.4 \
    future \
    intelhex \
    MAVProxy \
    pymavlink \
    && rm -rf /var/lib/apt/lists/*

COPY third_party/ardupilot /opt/ardupilot
WORKDIR /opt/ardupilot
RUN test -f Tools/autotest/sim_vehicle.py \
    || (echo "ArduPilot source missing: initialize submodule at ardupilot/" >&2; exit 2)
RUN rm -rf .git .gitmodules \
    && git init -q \
    && git config user.email "container-build@navlab.local" \
    && git config user.name "navlab container build" \
    && git commit --allow-empty -q -m "container build metadata"
RUN ./waf configure --board sitl --no-submodule-update \
    && ./waf copter \
    && strip /opt/ardupilot/build/sitl/bin/arducopter \
    && find /opt/ardupilot -type f \( -name '*.o' -o -name '*.d' \) -delete \
    && rm -rf /opt/ardupilot/.git

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV ARDUPILOT_BIN=/usr/local/bin/arducopter

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    ca-certificates \
    iproute2 \
    net-tools \
    procps \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ardupilot-sitl-build /opt/ardupilot/build/sitl/bin/arducopter /usr/local/bin/arducopter

WORKDIR /workspace
