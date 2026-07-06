> **[HISTORICAL]** 环境搭建教程(环境已建成)。当前状态以 [CURRENT_STATUS.md](../../CURRENT_STATUS.md) 为准。

# Runbook 01 · 环境搭建(WSL2 + Docker)+ P0 启动

> 适用机器:ThinkBook 16p G6,Win11 家庭版 25H2,Ultra 9 275HX / 32G / RTX5060 8G / C 盘剩 ~835G。
> 目标:把这台新机配成 GBPlanner↔world-model 的开发环境。**通用工具装默认位置(复用),项目代码放 WSL Linux 文件系统。**
> 图例:🟢=我(Claude)已替你完成 / 🔴=需你在**管理员**终端执行(含重启) / 🔵=在 WSL Ubuntu 内执行。

---

## A. 已完成(🟢 Claude 已装,用户级,默认位置)

| 工具 | 版本 | 位置 |
|---|---|---|
| Git | 2.54 | C:\Program Files\Git(原有) |
| VS Code | 1.126 | 原有;已加扩展 Remote-WSL / Docker / Dev Containers / Python |
| winget | 1.28 | 系统自带 |
| GitHub CLI `gh` | 2.95 | WinGet 用户目录 |
| Python(真) | 3.12.10 | %LocalAppData%\Programs\Python\Python312(已盖过 Store stub) |
| uv | 0.11.25 | WinGet 用户目录 |
| Node.js LTS | 24.18 | WinGet 用户目录 |
| pandoc | 3.10 | WinGet 用户目录 |

> 这些都是"通用开发工具",以后别的项目通用。**robotics 专用工具链(ROS2/colcon/cmake/Go/GBPlanner)将装在 WSL Ubuntu 里,不污染 Windows。**

---

## B. 🔴 第 1 步:启用 WSL2 + 安装 Ubuntu 22.04(需管理员 + 重启)

> 为什么 22.04:ROS2 **Humble** 官方对应 Ubuntu 22.04,与 world-model 默认镜像 `navlab/*:humble-latest` 对齐。

1. 开始菜单搜 **PowerShell** → 右键 **以管理员身份运行**,执行:
   ```powershell
   wsl --install -d Ubuntu-22.04
   wsl --set-default-version 2
   ```
2. **重启电脑**(首次启用虚拟化功能必需)。
3. 重启后 Ubuntu 会自动启动,提示创建 **UNIX 用户名和密码**(记住密码,后面 sudo 要用)。
4. 验证(普通 PowerShell 即可):
   ```powershell
   wsl -l -v        # 应看到 Ubuntu-22.04  Running  2
   ```

> 若虚拟化没开:进 BIOS 打开 Intel VT-x / Virtualization。本机 `HypervisorPresent=True`,大概率已开。

---

## C. 🔵 第 2 步:Docker —— 用 WSL 内原生 engine(推荐,默认路径)

> 决策已定:**这次干活在 WSL2 内 → 装 WSL 原生 docker engine**(更轻,无常驻 Windows 后台服务,与真实 Linux 部署一致)。
> ⚠️ **不要同时再装 Docker Desktop**:两个 dockerd 守护进程会抢 socket 冲突。二选一即可。

🔵 在 Ubuntu 内执行:
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER        # 加入 docker 组
# 退出并重开 WSL 终端(或 `wsl --shutdown` 后重进)使组生效
docker run hello-world               # 验证
```
> WSL2(systemd 默认开启)下 docker 服务会自动起;若没起:`sudo service docker start`。

**(可选替代,不与上面并用)Docker Desktop:** 仅当你想要 GUI 管理面板时,管理员 PowerShell 跑
`winget install --id Docker.DockerDesktop -e --accept-source-agreements --accept-package-agreements`,
然后 Settings → Resources → WSL Integration 开 `Ubuntu-22.04`。**选了这个就别再装 WSL 原生 engine。**

---

## D. 🔵 第 3 步:WSL Ubuntu 基础环境

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential cmake git curl wget python3-pip python3-venv golang-go
# 代码放 Linux 文件系统,绝不放 /mnt/c 下编译!
mkdir -p ~/ws && cd ~/ws
git clone https://github.com/SZ-surveying/world-model.git
```

> NVIDIA GPU:Win 侧装好 NVIDIA 驱动后,WSL2 自动透传 CUDA;无需在 WSL 内装驱动。需要 GPU 容器时再装 `nvidia-container-toolkit`。

---

## E. 🔵 P0-A:跑通 world-model 现有基线(看 frontier_lite 探索)

```bash
cd ~/ws/world-model
# 1) 摸清启动方式(README + Go CLI)
ls docker/compose; cat README.md | head -60
cd orchestration/sim && go run ./cmd/navlab-sim --help
# 2) 拉镜像并起 exploration 基线任务(具体子命令以 --help 为准)
docker compose -f ../../docker/compose/*.yml pull   # 文件名以实际为准
# 目标:看到 Gazebo(headless)+ ArduPilot SITL + Cartographer 跑起来,
#       exploration 任务用 frontier_lite 让无人机凑几个目标点(这就是要替换的占位)。
```

> 这一步只为**确认基线能跑 + 理解现状**,不改代码。GUI 可视化优先用 headless + rosbag,避免 WSL2 Gazebo GUI 折腾。

---

## F. 🔵 P0-B:跑官方 GBPlanner 参考 sim(ROS1 Noetic,只为看懂算法)

**已为你写好一键 Dockerfile**,不用手敲 catkin。在 WSL2 内:
```bash
cp -r /mnt/c/CCproject/runbooks/gbplanner_ref ~/ws/gbplanner_ref
cd ~/ws/gbplanner_ref
bash build_and_run.sh          # 构建(首次约 10–25 分钟编译)+ 跑 rmf_sim.launch
# 或 bash build_and_run.sh shell   # 只进容器 shell
```
细节与排错见 [gbplanner_ref/README.md](gbplanner_ref/README.md)。

**P0 观察清单(录下来,供 P1 复刻):**
- voxblox 地图分辨率 / 截断距离(`voxblox_sim_config.yaml`)
- 增益权重、采样数、传感器 FOV(`gbplanner_config.yaml`)
- 输入:`/<robot>/velodyne_points`(3D)+ `odometry`;TF `world→navigation`
- 输出:PCI 经 service 触发(`std_srvs/Trigger`、`pci_search`、`pci_global`),发布参考轨迹(`geometry_msgs/Pose` 序列)+ `planner_msgs/PlannerStatus`

> WSLg 一般能转发 RViz GUI;若 Gazebo GPU 渲染卡,改 headless + 录 rosbag 看数据。

---

## G. 完成 P0 后 → 进入 P1

P1 起在 `~/ws` 下新建 `gbplanner_core`(纯 C++/CMake,无 ROS),按施工手册 §5 抽核心 + 合成地图 demo + 单测。详见 [GBPlanner集成施工手册.md](../GBPlanner集成施工手册.md)。

---

## 决策(已定)

1. ✅ Docker:**WSL 内原生 engine**(干活在 WSL2 内),不装 Docker Desktop,不并存两个 dockerd。
2. ✅ P0-B GBPlanner 参考环境:**已写成一键 Dockerfile**,见 `runbooks/gbplanner_ref/`(`bash build_and_run.sh`)。

## 你现在要做的(就两步,管理员 + 重启)
1. 🔴 管理员 PowerShell:`wsl --install -d Ubuntu-22.04` → 重启 → 建 UNIX 用户(§B)
2. 🔵 重启后在 Ubuntu 内:装 docker engine(§C)→ 基础环境 & clone(§D)→ 跑 P0(§E/§F)

*最后更新:2026-06-29 · Windows 通用工具已装;WSL2/Docker 待你管理员执行;P0-B Dockerfile 已就绪。*
