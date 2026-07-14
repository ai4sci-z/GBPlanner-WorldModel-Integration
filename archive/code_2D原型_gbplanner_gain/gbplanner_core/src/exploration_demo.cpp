// GBPlanner 核心决策演示(对应 mentor md):
//   合成一个"已探索房间 + 右侧开口通向未知"的俯视地图,
//   在机器人周围采样候选方向,对每个算体积增益+惩罚,选增益最高的方向,
//   打印决策表 + ASCII 俯视图,并写出一张 SVG 可视化图。
#include "gbplanner_core/dense_voxel_map.hpp"
#include "gbplanner_core/exploration_planner.hpp"
#include <algorithm>
#include <cstdio>

using namespace gbp;

int main(int argc, char** argv) {
  const double res = 0.1;
  const int nx = 50, ny = 30;
  DenseVoxelMap map(Vec3{0, 0, 0}, res, nx, ny, 1, VoxelState::Unknown);
  // 已探索的房间(空闲)
  map.fillBox(Vec3{1.0, 1.0, 0.0}, Vec3{2.5, 2.0, 0.1}, VoxelState::Free);
  // 三面墙(已占据);右侧 x>2.5 不设墙 = 开口,通向未知走廊
  map.fillBox(Vec3{0.9, 1.0, 0.0}, Vec3{1.0, 2.0, 0.1}, VoxelState::Occupied);  // 左墙
  map.fillBox(Vec3{1.0, 2.0, 0.0}, Vec3{2.5, 2.1, 0.1}, VoxelState::Occupied);  // 上墙
  map.fillBox(Vec3{1.0, 0.9, 0.0}, Vec3{2.5, 1.0, 0.1}, VoxelState::Occupied);  // 下墙

  Vec3 robot{1.5, 1.5, 0.05};
  double heading = 0.0;
  PlannerParams pp;
  pp.num_candidates = 16; pp.radius = 0.4; pp.k_dist = 1.0; pp.k_turn = 2.0;
  pp.sensor = SensorModel{}; pp.sensor.max_range = 3.0; pp.sensor.h_rays = 72;
  pp.sensor.v_rays = 1; pp.sensor.v_fov_deg = 0.0;  // 2D(单层)

  auto cands = planExploration(map, robot, heading, pp);

  std::printf("=== GBPlanner 核心决策演示(体积增益选路,对应 mentor md)===\n");
  std::printf("机器人 (%.1f, %.1f);右侧有开口通向未知走廊。候选方向 %zu 个:\n\n",
              robot.x, robot.y, cands.size());
  std::printf("候选  方向(度)  体积增益(m³)  距离罚  转向罚  综合评分   选中\n");
  Vec3 goal = robot;
  for (size_t i = 0; i < cands.size(); ++i) {
    const auto& c = cands[i];
    if (c.chosen) goal = c.point;
    std::printf("%3zu   %6.0f     %9.3f    %5.2f   %5.2f   %8.3f   %s\n", i,
                c.heading * 180.0 / 3.14159265, c.gain, pp.k_dist * c.dist,
                pp.k_turn * c.turn, c.score, c.chosen ? "<== 选它(增益最高)" : "");
  }

  std::printf("\n=== 俯视地图(# 墙  . 已探索  ? 未知  R 机器人  * 选中目标)===\n");
  for (int j = ny - 1; j >= 0; --j) {
    for (int i = 0; i < nx; ++i) {
      Vec3 c{(i + 0.5) * res, (j + 0.5) * res, 0.05};
      auto s = map.getState(c);
      char ch = (s == VoxelState::Occupied) ? '#' : (s == VoxelState::Free ? '.' : '?');
      if (static_cast<int>(robot.x / res) == i && static_cast<int>(robot.y / res) == j) ch = 'R';
      else if (static_cast<int>(goal.x / res) == i && static_cast<int>(goal.y / res) == j) ch = '*';
      std::printf("%c", ch);
    }
    std::printf("\n");
  }

  // === 写 SVG 可视化 ===
  const char* out = (argc > 1) ? argv[1] : "gain_decision.svg";
  FILE* f = std::fopen(out, "w");
  if (f) {
    const int cell = 12, top = 46;
    const int W = nx * cell, H = ny * cell + top;
    auto cx = [&](double x) { return static_cast<int>(x / res) * cell + cell / 2; };
    auto cy = [&](double y) { return top + (ny - 1 - static_cast<int>(y / res)) * cell + cell / 2; };
    std::fprintf(f, "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 %d %d\" font-family=\"Segoe UI, Microsoft YaHei, sans-serif\">\n", W, H);
    std::fprintf(f, "<rect width=\"%d\" height=\"%d\" fill=\"#ffffff\"/>\n", W, H);
    std::fprintf(f, "<text x=\"%d\" y=\"20\" text-anchor=\"middle\" font-size=\"16\" font-weight=\"bold\" fill=\"#111\">GBPlanner 核心决策:对每个候选方向算体积增益,选增益最高且避障的方向</text>\n", W / 2);
    std::fprintf(f, "<text x=\"%d\" y=\"38\" text-anchor=\"middle\" font-size=\"12\" fill=\"#6b7280\">深灰=墙  浅绿=已探索  灰=未知  蓝=机器人  绿圈大小=各方向增益  红线+黄=被选中</text>\n", W / 2);
    for (int j = 0; j < ny; ++j)
      for (int i = 0; i < nx; ++i) {
        Vec3 c{(i + 0.5) * res, (j + 0.5) * res, 0.05};
        auto s = map.getState(c);
        const char* col = (s == VoxelState::Occupied) ? "#374151" : (s == VoxelState::Free ? "#bbf7d0" : "#e5e7eb");
        std::fprintf(f, "<rect x=\"%d\" y=\"%d\" width=\"%d\" height=\"%d\" fill=\"%s\" stroke=\"#f9fafb\" stroke-width=\"0.5\"/>\n", i * cell, top + (ny - 1 - j) * cell, cell, cell, col);
      }
    double gmax = 1e-6;
    for (auto& c : cands) gmax = std::max(gmax, c.gain);
    for (auto& c : cands) {
      int rx = cx(robot.x), ry = cy(robot.y), px = cx(c.point.x), py = cy(c.point.y);
      std::fprintf(f, "<line x1=\"%d\" y1=\"%d\" x2=\"%d\" y2=\"%d\" stroke=\"%s\" stroke-width=\"%s\" opacity=\"0.85\"/>\n", rx, ry, px, py, c.chosen ? "#dc2626" : "#16a34a", c.chosen ? "3.5" : "1.4");
      int r = 3 + static_cast<int>(c.gain / gmax * 6.0);
      std::fprintf(f, "<circle cx=\"%d\" cy=\"%d\" r=\"%d\" fill=\"%s\"/>\n", px, py, r, c.chosen ? "#facc15" : "#16a34a");
    }
    std::fprintf(f, "<circle cx=\"%d\" cy=\"%d\" r=\"6\" fill=\"#2563eb\"/>\n", cx(robot.x), cy(robot.y));
    double cg = 0;
    for (auto& c : cands) if (c.chosen) cg = c.gain;
    std::fprintf(f, "<text x=\"%d\" y=\"%d\" text-anchor=\"middle\" font-size=\"13\" font-weight=\"bold\" fill=\"#b91c1c\">选中方向的体积增益 = %.2f m³(朝右侧开口,能看见最多未知空间)</text>\n", W / 2, H - 8, cg);
    std::fprintf(f, "</svg>\n");
    std::fclose(f);
    std::printf("\nSVG 可视化已写入: %s\n", out);
  }
  return 0;
}
