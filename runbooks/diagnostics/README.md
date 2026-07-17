# diagnostics/ 诊断脚本工具箱(预研A 排错战役沉淀,2026-07-04 归档)

> 每个脚本对应一种可复用的调试方法;方法原理与实战案例见 **[docs/预研A排错战役实录_35轮实验全解.md](../../docs/archive/预研A排错战役实录_35轮实验全解.md)**。
> 运行方式统一:`wsl -d Ubuntu-22.04 bash <脚本>`(.py 用 `python3 <脚本>`)。路径均指向 WSL 侧 `~/ws/world-model`。

| 脚本 | 方法 | 用途 |
|---|---|---|
| `验尸_最新run的blockers与SLAM.sh` | post-mortem | 一键读最新 exploration run 的 blockers 清单 + SLAM 质量,是每轮实验后的**第一件事** |
| `验尸_探针原始采样细节.sh` | post-mortem | 展开 summary 里每个探针的原始采样(ok/rc/有无 stdout/解析状态)——blocker 名会骗人,原始采样不会 |
| `守株待兔_容器一出现就inspect.sh` | event-driven capture | 每 2 秒蹲守目标容器,出现瞬间 `docker inspect` 存档——解决"容器活不过手动探针"的竞态 |
| `存活监测_容器30秒三采样.sh` | liveness probe | 1:1 复刻某服务的启动方式并每 10 秒采样存活状态,定位"启动即死 vs 若干秒后死" |
| `AB实验_uid1000复现与GZ_PARTITION治愈.sh` | ablation + 复现/治愈双实验 | 坑#12 的定案武器:A 组忠实复刻失败环境,B 组只加一个修复变量——**同时拿到复现与治愈证据** |
| `组播自测_单收.py` | network self-test | 20 行验证本机组播基本收发(gz 同款组播组/端口) |
| `组播自测_多socket分发.py` | network self-test | 验证多个 REUSEADDR socket 共享端口时内核组播分发是否正常(3收1发) |
| `组播嗅探_gz发现端口.py` | packet sniffing | 蹲 239.255.0.7:10317 抓 gz-transport 发现报文,统计来源/频率——区分"没发"和"没收到" |

**使用要点**
1. 任何容器相关实验前,确保有 WSL 看门进程(实操手册 §0 铁律)。
2. 探针身份要与被测服务一致(`--user`/env),否则 gz 分区不同会"全盲"(坑#12 教训)。
3. 结论只认脚本输出的真实产物,不认退出码。
