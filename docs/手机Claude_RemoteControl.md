> 📌 **状态戳(2026-07-06 晚·全绿后)**:本文含历史阶段内容。**当前权威状态**以 [RESUME_新窗口接管_2026-07-06.md](../RESUME_新窗口接管_2026-07-06.md) + [Bug 台账](../docs/world-model端到端Bug台账_给作者PR.md) 为准。要点:jazzy 9/9 已验真;**run `20260706T130626` 已端到端全绿**(TASK_STATUS_OK/4探针全ok/3目标/SIM+0.72m,无hack,B15+B16 已修);但 frontier_lite 多跑基线**稳定性差**(6次全绿2/6,达标率40%,根因=启动耗时蚕食探索窗口);当前主线=**B2.5 自写薄桥接真 GBPlanner**(官方 ros1_bridge 与 zenoh 均已实验判死)→3D lidar(官方 lidar_3d 组件)→同口径对比;**PR 延后**(用户指示:等最终桥接跑通后统一定稿)。

# 用手机 Claude 远程接管本项目会话(Remote Control)

> 📌 **2026-07-03 校核**:本文内容仍有效。项目最新全景与"你在这里"路线图见 [README](../README.md);运行时排坑最新进展见 [运行时排错记录_humble.md](运行时排错记录_humble.md)。

> 需求:在手机上的 Claude App 里,连到"这个正跑在你电脑上的 Claude Code 会话",随时查看/继续。
> 关键:Claude **仍在你电脑本机运行**(代码、WSL、Docker、仿真都在你电脑上,不上云),手机只是远程接管界面。最后更新 2026-06-29。

## 前提
- Claude Code 版本 **≥ 2.1.51**(偏旧先更新)。
- 电脑和手机登录**同一个 claude.ai 账号**。

## 步骤
1. **电脑(本会话)**:开启 **Remote Control(远程控制)**。开启后会显示一个**会话链接 + 二维码**(文档说可按空格键显示二维码)。
2. **手机**:打开 **Claude App** → **扫这个二维码** → 即接管本会话;或用手机浏览器打开那个链接(claude.ai/code)。
3. 首次连接用 **Face ID / Touch ID / Windows Hello / passkey** 确认即可。

## 官方出处(准确,非凭印象)
- [Continue local sessions from any device with Remote Control — Claude Code Docs](https://code.claude.com/docs/en/remote-control)
- 该功能为 research preview;开启的确切入口(`/` 命令或菜单)以官方文档为准,扫码流程一致。

## 用途(对本项目)
- 镜像构建/仿真常常要跑很久;你可以离开电脑,用手机随时看进度、发指令(比如"截图""跑 exploration")。
- 组会时也可用手机接管演示。
