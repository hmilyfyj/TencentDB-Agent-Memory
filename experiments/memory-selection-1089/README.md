本目录是 ISSUE-1089 的合成对照实验，不是正式记忆接入。测试不会修改 Multica 智能体、既有代理、Hub 或业务数据库。结论见 `REPORT.md`，原始结果通过任务附件交付。

## 固定版本与安装

- TencentDB Core：本 fork 的 `f9ab423b37fe21385246fc1cd64e3c53fc9c0dfd`；实验代码另外提交。
- Hy-Memory：`Tencent-Hunyuan/Hy-Memory@9737431cf8965124b115f0e26cb0ff1e5cafa323`，SDK 2.0.14。
- Python 3.12.11、Node 24.15.0；fastembed 0.9.1、onnxruntime 1.31.1、Chroma 1.5.9、openai Python 2.54.0。
- 向量：`BAAI/bge-small-zh-v1.5`，512维，fastembed 的 Qdrant ONNX 发布物。文件校验和在每批结果的 `embedding-files.json`。
- 本轮模型为调用者自己已授权的 `auto/gpt-6.1-sol`，返回别名 `group/auto-gpt-6-1-sol`。供应商没有披露不可变的底层快照或单价，不将别名当作精确模型版本。

在任务自己的工作目录建立环境；不要在其他智能体的目录执行，也不要复制其他智能体的配置。

```sh
uv venv .venv --python 3.12.11
uv pip install --python .venv/bin/python 'git+https://github.com/Tencent-Hunyuan/Hy-Memory.git@9737431cf8965124b115f0e26cb0ff1e5cafa323' fastembed==0.9.1
```

Core 在本仓库 `MemoryCore` 目录执行 `npm install --ignore-scripts`，保留平台对应的 optional dependencies；`tsx` 需要 esbuild 的平台二进制。本轮完整 Python 依赖快照和实际 npm lock 在证据附件中。使用附件 lock 配合 `npm ci --ignore-scripts` 可减少依赖版本变化。不要运行仓库的一键部署脚本。

## 执行

脚本使用命令行指定的**当前调用者自己的** Codex 配置，只在内存中复用其模型入口及请求头，不打印或保存真实凭据。也可以通过 `EVAL_LLM_BASE_URL`、`EVAL_LLM_API_KEY`、`EVAL_LLM_MODEL` 传入独立获授权的 OpenAI 兼容连接，省略 `--codex-config`。不要以其他智能体或管理员的模型密钥代替缺失凭据。

```sh
python3 experiments/memory-selection-1089/run.py --self-check

HF_HOME="$PWD/evidence/hf-cache" HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_TELEMETRY=1 \
  .venv/bin/python experiments/memory-selection-1089/run.py \
  --codex-config "$CODEX_HOME/config.toml" --out evidence/main

# 与 primary batch 隔离：验证 pro 聊天场景的原生项目参数。
.venv/bin/python experiments/memory-selection-1089/run.py \
  --codex-config "$CODEX_HOME/config.toml" --backend hy-native-pro --out evidence/native-pro

# 与聊天模式比较，使用完整相同输入，避免将配置差异当作产品能力差异。
.venv/bin/python experiments/memory-selection-1089/run.py \
  --codex-config "$CODEX_HOME/config.toml" --backend tdai --core-prompt-mode code --out evidence/core-code-all

# 单独观察原生 Skill 抽取与按 ID 读取，不把经验召回当作 Skill 发布。
.venv/bin/python experiments/memory-selection-1089/run.py \
  --codex-config "$CODEX_HOME/config.toml" --backend tdai-skills --out evidence/core-skills

# 新库中登记合成owner/team/agent，单独检查手工Skill管理；不使用现有管理员凭据。
.venv/bin/python experiments/memory-selection-1089/run.py \
  --codex-config "$CODEX_HOME/config.toml" --backend tdai-skill-management --out evidence/skill-management

python3 experiments/memory-selection-1089/summarize.py \
  evidence/main evidence/native-pro evidence/core-code-all evidence/core-skills evidence/skill-management > metrics.json
```

上述路径按实际 checkout 和虚拟环境位置调整。`--out` 必须为不存在的新目录；每批独立库、独立会话，模型权重缓存可以共用。补测 `--backend tdai-code` 只运行工具轨迹与对应问题，然后运行 Skill 检查。设置 HF 环境变量可用于全部批次；未经授权不使用已有 Hugging Face 私有令牌。

14 段输入含两个真正并行发起的项目写入，15 个新会话问题。`dataset.json` 中的 `expected`、`forbidden` 仅供评分，两个字段均不进入模型问题。脚本自检覆盖盲测请求及工具调用配对。公共范围是明确写好的合成夹具；不能把它当作自动公共提炼。Hy 的范围映射使用合成 `user_id` 命名空间，Core 使用合成 team/agent；这些映射本身没有实现服务端授权。

每次 SDK/API 输入、响应、模型原始请求与响应、耗时及 usage 保存在 `events.jsonl`。`add` 成功不等于提炼成功，队列 idle 也不等于提炼成功，应核对 `raw:*`、`raw-trace:*`、`extracted:*` 和 `recall:*`。字符串缺失只是诊断，须阅读实际答案及上下文；不要将一次小样本结果解释为总体准确率。模拟 503 的路径与真实模型入口分开；不会关闭模型服务。

## 生命周期与清理

本机桥接和 Core 只绑定 loopback 临时端口，由前台脚本管理。正常结束或 Ctrl+C 时关闭桥接、等待 Node 子进程退出，记录 PID 和端口；不会停止任何既有进程。Skill 检查最多等180秒，每个模型请求最多60秒，观测日志只读取末尾64KB，遇到 extractor 未初始化立即结束该项。没有后台完成机制，不要将脚本放到后台后退出任务。

保留并校验原始 JSON、必要日志和依赖快照后，可删除本批 `hy-*`、`tdai*` 数据子目录中的合成数据库；不要删除其他任务的数据。发布附件前检查真实密钥没有进入文件。本轮清理记录在附件 `cleanup.json`。
