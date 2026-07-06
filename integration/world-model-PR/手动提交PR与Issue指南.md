# 手动提交 PR 与 Issue 给 world-model 作者 —— 分步教程

> 🚧 **提交前置检查(2026-07-06 晚更新,未满足前禁止执行本教程)**:
> 1. ✅ exploration 端到端全绿(run `20260706T130626`,4 探针全 ok、3/3 目标)。
> 2. ✅ clean diff 无参数 hack(提交链 `79643b9→77d951a→dada2db`,286 行)。
> 3. ❌ **真 GBPlanner 桥接集成跑通(用户指示的统一定稿前置)——当前未满足**。
> 4. ⏳ `PR_BODY.md`/`ISSUE_BODY.md` 定稿(现为 DRAFT,需吸收 B16+基线数据)。
> 5. `gh auth status` 已登录、fork = `ai4sci-z`。
> 上述③④未满足前,**不要**按下面步骤提交。

> 目标:把已经做好、已验证、已 commit 的改动,作为 **1 个 Issue + 1 个 PR** 亲手提交到
> `SZ-surveying/world-model`。本文给两条路:**A 用 `gh` 命令行**(快,gh 已登录)、**B 用网页**(直观)。
> 你只需照抄。任何一步看不懂就停下问我。

---

## 0. 现在手头有什么(都已就绪)

- 本地仓库:WSL 里 `~/ws/world-model`,已在分支 **`feat/gbplanner-gain-exploration-strategy`** 上,
  含 2 个 commit:
  - `fix(exploration): ...%%...` —— 修编译 bug
  - `feat(exploration): ...gbplanner_gain...` —— 加策略
- PR 文案:本目录 `PR_description.md`
- Issue 文案:本目录 `ISSUE_frontier_lite_and_compile_bug.md`
- 改动补丁备份:本目录 `gbplanner_gain.patch`
- 证据:本目录 `rendered_frontier_lite.py` / `rendered_gbplanner_gain.py`(都能 `py_compile` 过)

> ⚠️ 你**不能**直接往 `SZ-surveying/world-model` push(没权限)。标准做法:**先 fork 到你自己的账号
> `ai4sci-z`,push 到你的 fork,再从 fork 发 PR 到原仓库**。

---

## 路线 A:用 `gh` 命令行(推荐,最快)

在 WSL 里执行(逐条)。`$WM` 是仓库路径,先设一下:

```bash
WM=~/ws/world-model
cd "$WM"
gh auth status          # 确认已登录为 ai4sci-z;没登录就 gh auth login
```

### A1. Fork 到你的账号(只需一次)

```bash
gh repo fork SZ-surveying/world-model --remote --remote-name fork --clone=false
```

- 这会在 `https://github.com/ai4sci-z/world-model` 建一个 fork,并把它加成本地 remote `fork`。
- 验证:`git remote -v` 应能看到 `fork  https://github.com/ai4sci-z/world-model.git`。

### A2. 把分支推到你的 fork

```bash
git -C "$WM" push -u fork feat/gbplanner-gain-exploration-strategy
```

> 如果卡 TLS/超时(本机偶发):重试一次;或先 `git -C "$WM" config http.proxy http://127.0.0.1:7897` 再 push。

### A3. 先开 Issue(PR 要引用它的编号)

```bash
gh issue create \
  --repo SZ-surveying/world-model \
  --title "exploration: generated runtime script fails to compile; frontier_lite is open-loop (ignores the map)" \
  --body-file /mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/world-model-PR/ISSUE_BODY.md
```

> 注意:`--body-file` 要的是**纯正文**,不含本仓 md 里那层 ```` ```markdown ```` 围栏。
> 我已为你单独导出纯正文文件 `ISSUE_BODY.md` 和 `PR_BODY.md`(见本目录),直接用它们即可。

记下返回的 Issue 链接里的编号,例如 `#12`。

### A4. 把 PR 正文里的 `#<ISSUE_NUMBER>` 换成真实编号

```bash
# 假设 Issue 是 12
sed "s/#<ISSUE_NUMBER>/#12/" \
  /mnt/c/CCproject/GBPlanner-WorldModel-Integration/integration/world-model-PR/PR_BODY.md \
  > /tmp/PR_BODY_final.md
```

### A5. 开 PR(从你的 fork 分支 → 原仓库 main)

```bash
gh pr create \
  --repo SZ-surveying/world-model \
  --base main \
  --head ai4sci-z:feat/gbplanner-gain-exploration-strategy \
  --title "exploration: fix generated-script compile bug and add map-aware gbplanner_gain strategy" \
  --body-file /tmp/PR_BODY_final.md
```

返回的链接就是你的 PR。**完成。** 把 Issue 链接 + PR 链接发我,我帮你存档。

---

## 路线 B:用网页(不想碰命令行时)

### B1. Fork
打开 `https://github.com/SZ-surveying/world-model` → 右上角 **Fork** → 选你的账号 `ai4sci-z` → 创建。

### B2. 推分支到 fork
WSL 里:
```bash
cd ~/ws/world-model
git remote add fork https://github.com/ai4sci-z/world-model.git   # 若已加过会报已存在,忽略
git push -u fork feat/gbplanner-gain-exploration-strategy
```

### B3. 开 Issue
原仓库页面 → **Issues** 标签 → **New issue** →
- 标题、正文照抄 `ISSUE_frontier_lite_and_compile_bug.md` 里 ```` ```markdown ```` 围栏内的内容
- 提交,记下编号(如 `#12`)。

### B4. 开 PR
- 推完分支后,GitHub 通常会在你的 fork 页面顶部弹 **"Compare & pull request"** 黄条 → 点它;
  没弹就去你的 fork → **Pull requests** → **New pull request** → 点 **compare across forks**。
- 选:**base repository = `SZ-surveying/world-model`,base = `main`**;
  **head repository = `ai4sci-z/world-model`,compare = `feat/gbplanner-gain-exploration-strategy`**。
- 标题、正文照抄 `PR_description.md` 围栏内的内容;把正文里的 `#<ISSUE_NUMBER>` 改成第 B3 步的真实编号。
- **Create pull request。**

---

## 提交后:作者会怎么看 / 你怎么应对

- 作者可能要求改 API(配置项名、topic 名)、加测试、跑 CI。看到评论别慌,贴给我,我帮你改。
- 你的本地分支随时能继续改:在 `~/ws/world-model` 的 `feat/...` 分支上改 → `git commit` → `git push fork`,
  PR 会自动更新。
- CI 若失败,多半是 `go test` / lint。把日志贴我。

## 自查清单(提交前对一遍)

- [ ] `gh auth status` 是 `ai4sci-z`
- [ ] `git -C ~/ws/world-model log --oneline -2` 能看到 fix + feat 两个 commit
- [ ] PR 的 base 是 `SZ-surveying/world-model:main`,head 是 `ai4sci-z:feat/gbplanner-gain-exploration-strategy`
- [ ] PR 正文里的 `#<ISSUE_NUMBER>` 已替换成真实 Issue 编号
- [ ] 没有把 `orchestration/sim/config.toml`(本机 humble 改动)带进 PR —— 它**不在**这两个 commit 里,放心
