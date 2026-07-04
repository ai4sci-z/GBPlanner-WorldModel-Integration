from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ARDUPILOT_GZ = REPO_ROOT.parent / "ardupilot_gz"
DEFAULT_MAZE = DEFAULT_ARDUPILOT_GZ / "ardupilot_gz_gazebo/worlds/maze.sdf"
DEFAULT_OUTPUT = REPO_ROOT / "docs/images/official_maze_topdown.svg"


@dataclass(frozen=True, slots=True)
class Wall:
    name: str
    x: float
    y: float
    yaw: float
    length: float
    thickness: float
    height: float


def parse_walls(path: Path) -> list[Wall]:
    root = ET.parse(path).getroot()
    model = root.find(".//model[@name='maze']")
    if model is None:
        raise ValueError(f"maze model not found in {path}")
    walls: list[Wall] = []
    for link in model.findall("link"):
        name = link.get("name") or "wall"
        pose_el = link.find("pose")
        link_pose = _pose_values(pose_el.text if pose_el is not None else None)
        link_yaw = link_pose[5]
        if pose_el is not None and pose_el.get("degrees") == "true":
            link_yaw = math.radians(link_yaw)
        collision = link.find("collision")
        if collision is None:
            continue
        collision_pose = _pose_values(collision.findtext("pose"))
        size_text = collision.findtext(".//box/size")
        if not size_text:
            continue
        length, thickness, height = (float(item) for item in size_text.split()[:3])
        cx, cy = collision_pose[0], collision_pose[1]
        x = link_pose[0] + math.cos(link_yaw) * cx - math.sin(link_yaw) * cy
        y = link_pose[1] + math.sin(link_yaw) * cx + math.cos(link_yaw) * cy
        walls.append(Wall(name=name, x=x, y=y, yaw=link_yaw, length=length, thickness=thickness, height=height))
    return walls


def _pose_values(text: str | None) -> tuple[float, float, float, float, float, float]:
    values = [float(item) for item in (text or "0 0 0 0 0 0").split()]
    values += [0.0] * (6 - len(values))
    return tuple(values[:6])  # type: ignore[return-value]


def render_svg(walls: list[Wall], *, maze_path: Path) -> str:
    width = 1200
    height = 1200
    margin = 85
    world_min = -11.0
    world_max = 11.0
    scale = (width - 2 * margin) / (world_max - world_min)

    def sx(x: float) -> float:
        return margin + (x - world_min) * scale

    def sy(y: float) -> float:
        return height - margin - (y - world_min) * scale

    def rect_points(wall: Wall) -> str:
        half_l = wall.length / 2.0
        half_t = wall.thickness / 2.0
        local = [(-half_l, -half_t), (half_l, -half_t), (half_l, half_t), (-half_l, half_t)]
        points: list[str] = []
        for lx, ly in local:
            x = wall.x + math.cos(wall.yaw) * lx - math.sin(wall.yaw) * ly
            y = wall.y + math.sin(wall.yaw) * lx + math.cos(wall.yaw) * ly
            points.append(f"{sx(x):.1f},{sy(y):.1f}")
        return " ".join(points)

    grid = []
    for value in range(-10, 11, 5):
        grid.append(
            f'<line x1="{sx(value):.1f}" y1="{sy(world_min):.1f}" '
            f'x2="{sx(value):.1f}" y2="{sy(world_max):.1f}" class="grid"/>'
        )
        grid.append(
            f'<line x1="{sx(world_min):.1f}" y1="{sy(value):.1f}" '
            f'x2="{sx(world_max):.1f}" y2="{sy(value):.1f}" class="grid"/>'
        )
        grid.append(f'<text x="{sx(value):.1f}" y="{sy(world_min) + 34:.1f}" class="tick">{value}</text>')
        grid.append(f'<text x="{sx(world_min) - 28:.1f}" y="{sy(value) + 4:.1f}" class="tick">{value}</text>')

    wall_shapes = []
    labels = []
    for wall in walls:
        wall_shapes.append(f'<polygon points="{rect_points(wall)}" class="wall"><title>{wall.name}</title></polygon>')
        labels.append(f'<text x="{sx(wall.x):.1f}" y="{sy(wall.y) - 7:.1f}" class="label">{wall.name}</text>')

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <style>
    .bg {{ fill: #f8faf8; }}
    .grid {{ stroke: #d4ddd9; stroke-width: 1; }}
    .axis {{ stroke: #6a7f78; stroke-width: 2; stroke-dasharray: 7 6; }}
    .wall {{ fill: #343a40; stroke: #111; stroke-width: 1; }}
    .label {{ font: 18px monospace; fill: #26312d; text-anchor: middle; }}
    .tick {{ font: 16px monospace; fill: #60706b; text-anchor: middle; }}
    .note {{ font: 20px sans-serif; fill: #26312d; }}
    .start {{ fill: #2f80ed; stroke: white; stroke-width: 4; }}
  </style>
  <rect width="100%" height="100%" class="bg"/>
  <text x="60" y="48" class="note">Official ArduPilot Gazebo maze.sdf top-down wall geometry</text>
  <text x="60" y="78" class="note">Source: {maze_path}</text>
  {chr(10).join(grid)}
  <line x1="{sx(0):.1f}" y1="{sy(world_min):.1f}" x2="{sx(0):.1f}" y2="{sy(world_max):.1f}" class="axis"/>
  <line x1="{sx(world_min):.1f}" y1="{sy(0):.1f}" x2="{sx(world_max):.1f}" y2="{sy(0):.1f}" class="axis"/>
  {chr(10).join(wall_shapes)}
  {chr(10).join(labels)}
  <circle cx="{sx(0):.1f}" cy="{sy(0):.1f}" r="9" class="start"><title>Nominal start / origin</title></circle>
  <text x="{sx(0) + 14:.1f}" y="{sy(0) - 14:.1f}" class="note">origin</text>
</svg>
'''


def render_topdown_svg(maze_path: Path, output_path: Path) -> Path:
    resolved_maze = maze_path.expanduser()
    resolved_output = output_path.expanduser()
    walls = parse_walls(resolved_maze)
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text(render_svg(walls, maze_path=resolved_maze), encoding="utf-8")
    return resolved_output
