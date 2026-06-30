# WSL 使用与本机复现指南(可照做,命令均已实测)

> 目标:让你能自己打开 WSL、验证镜像、跑仿真。每条命令都在本机验证过。最后更新 2026-06-30。

## 1. 怎么打开 WSL / 进入 Ubuntu
任选一种:
- **开始菜单**搜 **`Ubuntu`** → 回车;或搜 **`wsl`** → 回车。
- 或开 **PowerShell**,输入 `wsl` 回车。

进来后提示符是 **`ai4s@AI4S:~$`**(有 `:~$` 就对了,这是 Linux,不是 PowerShell)。
> 区别:PowerShell 是 `PS C:\Users\25006>`;WSL/Ubuntu 是 `ai4s@AI4S:~$`。Linux 命令(docker/git/ls)要在后者敲。

## 2. 已配好的环境(无需重装,知道即可)
| 项 | 值 |
|---|---|
| 系统 | Ubuntu 22.04(用户 `ai4s`) |
| Go | **`/usr/local/go/bin/go`**(1.24)。⚠️ 直接敲 `go` 是旧的 1.18,要用全路径或先 `export PATH=/usr/local/go/bin:$PATH` |
| Docker | 已装,`ai4s` 可直接用 |
| 代理 | clash `127.0.0.1:7897`(拉 github/dockerhub 要它,Windows 上 clash 开着) |
| 项目仓库 | `~/ws/world-model` |
| 我们的文档/代码 | `/mnt/c/CCproject/GBPlanner-WorldModel-Integration`(= Windows 的 `C:\CCproject\...`) |

## 3. 验证 9 个镜像都建好了(核心,30 秒)
```bash
docker images | grep navlab
```
应看到 9 个 `navlab/*:humble`(ros-base、ardupilot-sitl、mavlink-router、gazebo-headless、fast-lio、companion、slam-cartographer、gazebo-sensor、official-baseline)。**数到 9 个 = 镜像复现成功。**

## 4. 跑仿真看画面
### 4.1 GBPlanner 仿真(预研B,镜像已就绪)
```bash
cp -r /mnt/c/CCproject/GBPlanner-WorldModel-Integration/runbooks/gbplanner_ref ~/gbplanner_ref   # 只需一次
cd ~/gbplanner_ref
bash build_and_run.sh
```
预期:桌面弹出 Gazebo + RViz(详见 [实跑操作手册_图文版.md](实跑操作手册_图文版.md))。

### 4.2 world-model 探索(预研A)
```bash
cd ~/ws/world-model/orchestration/sim
/usr/local/go/bin/go run ./cmd/navlab-sim run exploration
```
> ⚠️ 当前运行时管线(SLAM/探针)还在调试,可能 `status=blocked`;调通后会真正探索并出 `artifacts/.../summary.json` 指标。

### 4.3 平台自检/任务清单(快速确认环境)
```bash
cd ~/ws/world-model/orchestration/sim
/usr/local/go/bin/go run ./cmd/navlab-sim doctor       # 平台自检
/usr/local/go/bin/go run ./cmd/navlab-sim list-tasks   # 看 5 个任务
```

## 5. 退出 / 重进
- 退出:输 `exit` 回车。
- 重进:开始菜单再点 Ubuntu,或 PowerShell 输 `wsl`。
- 重启整个 WSL(偶尔需要):PowerShell 里 `wsl --shutdown`,再重开 Ubuntu。

## 6. 常见坑(避免返修)
| 现象 | 原因 / 解决 |
|---|---|
| `go` 版本报错 | 用 `/usr/local/go/bin/go`,别用裸 `go`(旧1.18) |
| 拉 github/镜像失败 | 确认 Windows 的 clash 开着(代理 127.0.0.1:7897) |
| 命令"找不到" | 看提示符:Linux 命令要在 `ai4s@AI4S:~$` 里敲,不是 PowerShell |
| GUI 不弹 | 必须在 WSL2(WSLg)里跑;`echo $DISPLAY` 应非空 |
