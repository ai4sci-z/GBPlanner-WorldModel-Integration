ARG ROS_DISTRO=humble
ARG INFRA_TAG=humble-latest
ARG ROS_BASE_IMAGE=navlab/ros-base:${INFRA_TAG}

FROM ${ROS_BASE_IMAGE} AS sim-python-builder

COPY --from=ghcr.io/astral-sh/uv:0.11.16-python3.11-alpine /usr/local/bin/uv /usr/local/bin/uv

WORKDIR /workspace

ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/opt/sim-venv

COPY navlab/pyproject.toml navlab/uv.lock /workspace/navlab/

RUN uv sync \
  --project /workspace/navlab \
  --frozen \
  --no-dev \
  --group companion \
  --no-install-project


FROM ${ROS_BASE_IMAGE} AS sim-python-runtime

ENV VIRTUAL_ENV=/opt/sim-venv
ENV PATH=/opt/sim-venv/bin:$PATH

COPY --from=sim-python-builder /opt/sim-venv /opt/sim-venv
