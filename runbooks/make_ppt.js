const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.defineLayout({ name: "W", width: 13.33, height: 7.5 });
p.layout = "W";

const NAVY="1E2761", INK="1F2937", ICE="CADCFC", WHITE="FFFFFF";
const GRAY="6B7280", LGRAY="F1F5F9", GREEN="16A34A", RED="DC2626", AMBER="B45309";
const F="Microsoft YaHei";
const IMG="C:/CCproject/GBPlanner-WorldModel-Integration/images/gain_decision.png";

function title(s, t, sub){
  s.addText(t, { x:0.6, y:0.45, w:12.1, h:0.7, fontFace:F, fontSize:30, bold:true, color:NAVY });
  if(sub) s.addText(sub, { x:0.62, y:1.15, w:12.0, h:0.45, fontFace:F, fontSize:15, color:GRAY });
}
function card(s, x, y, w, h, fill){
  s.addShape(p.ShapeType.roundRect, { x, y, w, h, fill:{ color: fill||LGRAY }, line:{ color:"E2E8F0", width:1 }, rectRadius:0.08 });
}

let s = p.addSlide(); s.background={ color:NAVY };
s.addText("GBPlanner 自主探索算法\n集成进 world-model 仿真平台", { x:0.8, y:2.1, w:11.7, h:1.8, fontFace:F, fontSize:38, bold:true, color:WHITE, lineSpacingMultiple:1.05 });
s.addText("项目进展汇报", { x:0.85, y:4.0, w:10, h:0.5, fontFace:F, fontSize:20, color:ICE });
s.addText("把只会按脚本动的探索,换成看地图、挑未知最多的路", { x:0.85, y:4.6, w:11.5, h:0.5, fontFace:F, fontSize:16, italic:true, color:ICE });
s.addText("2026-06", { x:0.85, y:6.4, w:4, h:0.4, fontFace:F, fontSize:14, color:ICE });

s = p.addSlide(); s.background={ color:WHITE };
title(s, "任务目标(来自 mentor 的算法说明)");
card(s, 0.6, 1.7, 7.4, 4.9);
s.addText("把 GBPlanner 加入 world-model,替换它现有的占位探索 frontier_lite。", { x:0.9, y:1.95, w:6.8, h:0.8, fontFace:F, fontSize:18, bold:true, color:INK });
s.addText([
  { text:"GBPlanner 是什么(mentor md 原意):\n", options:{ bold:true, color:NAVY, fontSize:16 } },
  { text:"一个自主探索决策模块——\n", options:{ fontSize:15, color:INK } },
  { text:"• 输入:机器人位姿 + 3D 占据地图(已占据/空闲/未知)+ 可通行性\n", options:{ fontSize:15, color:INK } },
  { text:"• 决策:用光线投射算每条路能看见多少未知空间(体积增益),选最高\n", options:{ fontSize:15, color:INK } },
  { text:"• 输出:一系列目标航点(waypoints)", options:{ fontSize:15, color:INK } },
], { x:0.9, y:2.85, w:6.9, h:3.5, fontFace:F, lineSpacingMultiple:1.25, valign:"top" });
card(s, 8.3, 1.7, 4.4, 4.9, "EEF2FF");
s.addText("一句话", { x:8.55, y:1.95, w:3.9, h:0.4, fontFace:F, fontSize:14, bold:true, color:NAVY });
s.addText("地图 + 位姿\n↓\nGBPlanner\n↓\n目标航点", { x:8.55, y:2.6, w:3.9, h:3.5, fontFace:F, fontSize:22, bold:true, color:NAVY, align:"center", valign:"top", lineSpacingMultiple:1.3 });

s = p.addSlide(); s.background={ color:WHITE };
title(s, "两个系统,三道鸿沟");
card(s, 0.6, 1.7, 6.0, 2.5, "EFF6FF");
s.addText("world-model(目标平台)", { x:0.85, y:1.9, w:5.5, h:0.4, fontFace:F, fontSize:16, bold:true, color:NAVY });
s.addText("ROS2 无人机仿真平台\nGazebo + ArduPilot 飞控 + Cartographer(2D 建图)\n现有探索策略 = frontier_lite", { x:0.85, y:2.4, w:5.5, h:1.6, fontFace:F, fontSize:14, color:INK, lineSpacingMultiple:1.25, valign:"top" });
card(s, 6.9, 1.7, 5.8, 2.5, "F0FDF4");
s.addText("GBPlanner(要集成的算法)", { x:7.15, y:1.9, w:5.3, h:0.4, fontFace:F, fontSize:16, bold:true, color:GREEN });
s.addText("ROS1 C++ 图搜索探索算法\nvoxblox 3D 体素地图 + 光线投射体积增益\n输出航点(经 PCI 控制接口)", { x:7.15, y:2.4, w:5.3, h:1.6, fontFace:F, fontSize:14, color:INK, lineSpacingMultiple:1.25, valign:"top" });
card(s, 0.6, 4.45, 12.1, 2.15, "FFF7ED");
s.addText("三道鸿沟 → 因此选「桥接方案(ros1_bridge)」", { x:0.85, y:4.6, w:11.6, h:0.4, fontFace:F, fontSize:16, bold:true, color:AMBER });
s.addText("①  ROS1 与 ROS2 两代框架不互通       ②  算法要 3D 占据地图,仿真无人机只有 2D 雷达       ③  输出与控制器接口不同", { x:0.85, y:5.15, w:11.6, h:1.2, fontFace:F, fontSize:14.5, color:INK, lineSpacingMultiple:1.3, valign:"top" });

s = p.addSlide(); s.background={ color:WHITE };
title(s, "核心发现①:现有探索是脚本占位,不是算法", "证据来自真实源码 exploration_workflow_runtime.py.tmpl");
card(s, 0.6, 1.95, 7.2, 4.6, "0F172A");
s.addText("frontier_lite 的决策核心:", { x:0.85, y:2.15, w:6.7, h:0.4, fontFace:F, fontSize:14, color:ICE });
s.addText("pattern = [前进, 前进+左扭, 前进+右扭]\ncmd = pattern[ goal_index % 3 ]   // 按计时器循环\n// 节点只订阅 /slam/odom,不订阅任何地图", { x:0.85, y:2.6, w:6.7, h:1.8, fontFace:"Consolas", fontSize:13.5, color:"A7F3D0", lineSpacingMultiple:1.3, valign:"top" });
s.addText("→ 只证明无人机能被指挥着动,完全不看地图、不做探索决策。", { x:0.85, y:4.7, w:6.7, h:1.6, fontFace:F, fontSize:14.5, color:WHITE, lineSpacingMultiple:1.25, valign:"top" });
card(s, 8.1, 1.95, 4.6, 2.15, "F8FAFC");
s.addText("0", { x:8.1, y:2.05, w:4.6, h:0.95, fontFace:F, fontSize:50, bold:true, color:RED, align:"center" });
s.addText("个地图输入", { x:8.1, y:3.1, w:4.6, h:0.4, fontFace:F, fontSize:15, color:GRAY, align:"center" });
card(s, 8.1, 4.4, 4.6, 2.15, "F8FAFC");
s.addText("3", { x:8.1, y:4.5, w:4.6, h:0.95, fontFace:F, fontSize:50, bold:true, color:AMBER, align:"center" });
s.addText("个写死动作循环", { x:8.1, y:5.55, w:4.6, h:0.4, fontFace:F, fontSize:15, color:GRAY, align:"center" });

s = p.addSlide(); s.background={ color:WHITE };
title(s, "核心发现②:GBPlanner 怎么加进去");
s.addText("插入点 = world-model 那个探索决策节点。把它的脚本循环换成 GBPlanner 的读地图→算增益→选航点。插口不变,只换决策内核。", { x:0.6, y:1.55, w:12.1, h:0.85, fontFace:F, fontSize:16, color:INK, lineSpacingMultiple:1.25 });
const steps = [
  ["①","装 3D 的眼睛","给仿真无人机加 3D 雷达(对齐 OS064)+ 3D 建图(octomap/voxblox),产出占据地图"],
  ["②","接大脑(桥接)","ros1_bridge:把 3D 地图+位姿喂给 ROS1 的 GBPlanner,把它输出的航点接回 ROS2"],
  ["③","换决策驱动飞","航点转 /navlab/fcu/setpoint/intent,替换脚本动作;策略标为 gbplanner"],
];
steps.forEach((st,i)=>{
  const x = 0.6 + i*4.15;
  card(s, x, 2.65, 3.9, 3.7, "EEF2FF");
  s.addText(st[0], { x:x+0.25, y:2.85, w:1.2, h:0.9, fontFace:F, fontSize:40, bold:true, color:NAVY });
  s.addText(st[1], { x:x+0.25, y:3.85, w:3.4, h:0.5, fontFace:F, fontSize:18, bold:true, color:INK });
  s.addText(st[2], { x:x+0.25, y:4.4, w:3.45, h:1.8, fontFace:F, fontSize:13.5, color:INK, lineSpacingMultiple:1.25, valign:"top" });
});

s = p.addSlide(); s.background={ color:WHITE };
title(s, "可运行成果:体积增益决策演示(真能跑)", "纯 C++,零基础设施依赖;30 秒可自己复现,直接对应 mentor md 核心");
s.addImage({ path:IMG, x:0.6, y:1.75, w:7.4, h:4.64 });
card(s, 8.25, 1.75, 4.45, 4.64, "F8FAFC");
s.addText("它做了什么", { x:8.5, y:1.95, w:4.0, h:0.4, fontFace:F, fontSize:16, bold:true, color:NAVY });
s.addText([
  { text:"对 16 个方向各算体积增益,选增益最高且避障的方向。\n\n", options:{ fontSize:14, color:INK } },
  { text:"朝右侧开口(未知最多):增益 0.420 m³ → 被选中\n", options:{ fontSize:14, color:GREEN, bold:true } },
  { text:"朝墙(挡住):增益仅 0.15~0.21 m³\n\n", options:{ fontSize:14, color:INK } },
  { text:"这正是看哪里没探过就往哪里去。", options:{ fontSize:14, color:INK, italic:true } },
], { x:8.5, y:2.5, w:3.95, h:3.7, fontFace:F, lineSpacingMultiple:1.2, valign:"top" });

s = p.addSlide(); s.background={ color:WHITE };
title(s, "真集成进展:两条腿往前推", "决策层原型(ROS2 原生)+ 真版 GBPlanner 桥接地基(锁定方案)");
card(s, 0.6, 1.75, 6.0, 4.0, "F0FDF4");
s.addText("① 决策层原型:gbplanner_gain", { x:0.85, y:1.92, w:5.5, h:0.4, fontFace:F, fontSize:15, bold:true, color:GREEN });
s.addText([
  { text:"在 world-model 真实代码里新增可选策略(加法,不动 frontier_lite):\n", options:{ fontSize:13, color:INK } },
  { text:"• 订阅占据栅格 /map → 24 方向光线投射数未知栅格(2D 体积增益)→ 减转向惩罚选向\n", options:{ fontSize:13, color:INK } },
  { text:"• 把 pattern[i%3] 脚本循环换成看地图挑未知最多方向\n", options:{ fontSize:13, color:GREEN, bold:true } },
  { text:"验证:go build/vet/test + 两策略 py_compile 全过\n", options:{ fontSize:12.5, color:INK } },
  { text:"边界:2D 原型,非完整 ROS1 GBPlanner", options:{ fontSize:12, color:AMBER, italic:true } },
], { x:0.85, y:2.4, w:5.5, h:3.3, fontFace:F, lineSpacingMultiple:1.25, valign:"top" });
card(s, 6.9, 1.75, 5.8, 4.0, "EFF6FF");
s.addText("② 真版桥接地基:ros1_bridge", { x:7.15, y:1.92, w:5.3, h:0.4, fontFace:F, fontSize:15, bold:true, color:NAVY });
s.addText([
  { text:"从 gbplanner-ref 源码逐条证实真版 GBPlanner 的 I/O 契约:\n", options:{ fontSize:13, color:INK } },
  { text:"• 进:点云 PointCloud2 + 里程计 + TF(标准类型)\n", options:{ fontSize:13, color:INK } },
  { text:"• 出:command/trajectory(标准 MultiDOFJointTrajectory)\n", options:{ fontSize:13, color:INK } },
  { text:"• 关键去风险:自定义 planner_msgs 留 ROS1 内,跨桥全是标准类型 → ros1_bridge 开箱\n", options:{ fontSize:13, color:NAVY, bold:true } },
  { text:"已产出:桥接话题映射 + ROS2 出口适配器(轨迹→intent,py_compile 过)", options:{ fontSize:12.5, color:INK } },
], { x:7.15, y:2.4, w:5.3, h:3.3, fontFace:F, lineSpacingMultiple:1.22, valign:"top" });
card(s, 0.6, 5.95, 12.1, 0.7, "FFF7ED");
s.addText("诚实边界:完整端到端(加 3D 雷达 + 起桥 + 两侧同跑)是后续重活,受 world-model 运行时阻塞(见下页)。", { x:0.85, y:6.05, w:11.6, h:0.5, fontFace:F, fontSize:13, color:AMBER, valign:"top" });

s = p.addSlide(); s.background={ color:WHITE };
title(s, "工程战果:连修 3 个 humble 真 bug,把平台往前推", "只信真实产物(docker images / 日志 / py_compile),不信退出码");
card(s, 0.6, 1.8, 7.4, 4.8, "0F172A");
s.addText("给 world-model 作者的真实可提交修复(均有实测证据)", { x:0.85, y:1.98, w:6.9, h:0.4, fontFace:F, fontSize:14.5, bold:true, color:ICE });
s.addText([
  { text:"① tomllib(头号):SLAM 在 Py3.10 一启动就崩(tomllib 是 3.11+)\n   → 回退 tomli;实测重跑后 SLAM 越过此崩溃\n\n", options:{ fontSize:13, color:"A7F3D0" } },
  { text:"② 空 launch 参数:humble 拒绝空值 name:= → SLAM 起不来\n   → 跳过空参;实测 cartographer 节点真正运行起来\n\n", options:{ fontSize:13, color:"A7F3D0" } },
  { text:"③ 模板 %% 编译 bug:生成脚本无法编译 → 改单 %(独立次要)\n\n", options:{ fontSize:13, color:ICE } },
  { text:"成效:world-model 从「装不起来」→ 9 镜像齐 → SLAM 从「一崩」推进到「cartographer 真运行,只差激光数据」", options:{ fontSize:13.5, color:WHITE, bold:true } },
], { x:0.85, y:2.45, w:6.9, h:4.0, fontFace:F, lineSpacingMultiple:1.2, valign:"top" });
card(s, 8.3, 1.8, 4.4, 4.8, "EFF6FF");
s.addText("PR + Issue 已备好", { x:8.55, y:1.98, w:3.9, h:0.4, fontFace:F, fontSize:14.5, bold:true, color:NAVY });
s.addText([
  { text:"1 个 PR(4 commit:3 fix + 1 feat)+ 1 个 Issue\n\n", options:{ fontSize:13, color:INK, bold:true } },
  { text:"物料齐全(integration/world-model-PR/):\n", options:{ fontSize:12.5, color:INK } },
  { text:"• PR/Issue 正文 + 补丁\n• 修复/渲染证据\n• 手动提交分步教程\n\n", options:{ fontSize:12.5, color:INK } },
  { text:"状态:待亲自提交到作者仓库 → 任务闭环", options:{ fontSize:13, color:AMBER, bold:true } },
], { x:8.55, y:2.45, w:3.9, h:4.0, fontFace:F, lineSpacingMultiple:1.25, valign:"top" });

s = p.addSlide(); s.background={ color:WHITE };
title(s, "一次探索:复现仿真平台(及时止损)");
card(s, 0.6, 1.8, 12.1, 1.7, LGRAY);
s.addText("我们曾尝试在本机完整复现 world-model 的 9 个 Docker 镜像,以端到端运行平台。", { x:0.9, y:2.0, w:11.5, h:0.5, fontFace:F, fontSize:16, bold:true, color:INK });
s.addText("但该平台为特定 Linux/CI 环境(Ubuntu 24.04)设计,本机从源码构建遭遇一连串版本兼容问题(编译器、Python、Gazebo、Fast-CDR 等)。", { x:0.9, y:2.55, w:11.5, h:0.8, fontFace:F, fontSize:14.5, color:INK, lineSpacingMultiple:1.2, valign:"top" });
card(s, 0.6, 3.7, 12.1, 2.9, "F0FDF4");
s.addText("关键判断 & 调整", { x:0.9, y:3.9, w:11.5, h:0.4, fontFace:F, fontSize:16, bold:true, color:GREEN });
s.addText("• 复现整个平台并非本任务核心——核心是算法理解 + 集成设计。\n• 据此及时调整方向:聚焦算法本身,靠读源码论证缺陷、设计集成、让核心算法真跑起来。\n• 教训:别为复现别人的基础设施过度投入;换 MacBook 也不解决(同样用 Docker/Linux,Apple 芯片反而更难)。", { x:0.9, y:4.4, w:11.5, h:2.0, fontFace:F, fontSize:14.5, color:INK, lineSpacingMultiple:1.3, valign:"top" });

s = p.addSlide(); s.background={ color:WHITE };
title(s, "当前状态与下一步");
card(s, 0.6, 1.8, 6.0, 4.8, "F0FDF4");
s.addText("✓ 已完成(扎实)", { x:0.85, y:2.0, w:5.5, h:0.4, fontFace:F, fontSize:17, bold:true, color:GREEN });
s.addText("• 摸清两个系统 + 三道鸿沟,定下桥接方案\n• 算法核心可运行:体积增益决策演示 + 单测\n• gbplanner_gain 决策层原型接进 world-model 结构\n• 阶段4 桥接地基:源码证实真版 I/O 契约 + ROS2 适配器\n• 连修 3 个 humble 真 bug,SLAM 从一崩→cartographer 真运行\n• 9/9 镜像构建成功;缺陷有代码铁证\n• PR/Issue 物料备好 + 完整文档 + GitHub 私有仓", { x:0.85, y:2.5, w:5.5, h:3.9, fontFace:F, fontSize:13, color:INK, lineSpacingMultiple:1.3, valign:"top" });
card(s, 6.9, 1.8, 5.8, 4.8, "EFF6FF");
s.addText("→ 进行中 / 下一步", { x:7.15, y:2.0, w:5.3, h:0.4, fontFace:F, fontSize:17, bold:true, color:NAVY });
s.addText("• 接着剥运行时坑:让 /scan 到达 cartographer → SLAM healthy\n• 跑通 exploration,取 frontier_lite 真实指标 + 验证 gbplanner_gain\n• 完整路线:加 3D 雷达 + 起 ros1_bridge 接真版 GBPlanner\n• 同场景量化对比;把 PR + Issue 提交给作者(任务闭环)", { x:7.15, y:2.5, w:5.3, h:3.9, fontFace:F, fontSize:13, color:INK, lineSpacingMultiple:1.35, valign:"top" });

s = p.addSlide(); s.background={ color:NAVY };
s.addText("frontier_lite 闭眼按脚本动;\nGBPlanner 睁眼挑未知最多的路。", { x:0.9, y:2.4, w:11.6, h:1.8, fontFace:F, fontSize:32, bold:true, color:WHITE, lineSpacingMultiple:1.15 });
s.addText("这几天:看懂了系统、设计清楚了集成、核心算法真跑起来,\n还把决策内核接进了真实代码、修了一个真 bug、备好了给作者的 PR。", { x:0.95, y:4.4, w:11.5, h:1.0, fontFace:F, fontSize:17, color:ICE, lineSpacingMultiple:1.2 });

const OUT = process.env.PPT_OUT || "C:/CCproject/GBPlanner-WorldModel-Integration/GBPlanner项目进展汇报.pptx";
p.writeFile({ fileName: OUT }).then(f=>console.log("OK "+f));
