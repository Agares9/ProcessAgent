# ProcessAgent Backend

后端提供通用企业场景决策 Agent 的统一运行时。所有行业共享同一套意图识别、记忆、编排、Skill 执行、检索和验证链路。

## 主要模块

```text
app/harness/    通用 Orchestrator、核心 Skill、领域处理器和任务执行器
app/memory/     会话、用户和企业事实记忆
app/retrieval/  BM25、向量和混合检索
app/pipeline/   文档解析、切分和索引
app/storage/    SQLite 等数据存储
scripts/        CLI 和维护脚本
tests/          单元、路由和工作流测试
```

统一入口是 `ScenarioOrchestratorFacade`。制造业旧入口 `ManufacturingOrchestratorFacade` 仅作为兼容别名保留。

核心 Skill 为：

```text
retrieve / understand / analyze / compare
calculate / optimize / check / verify
```

## 本地运行

```powershell
conda activate medix-swarm
python -m pip install -r requirements.txt
python -m scripts.run_manufacturing_agents
```

## 测试

```powershell
conda activate medix-swarm
cd D:\workfile\ProcessAgent
python -m pytest backend/tests/test_scenario_routing.py backend/tests/test_task_executor.py -q
```

默认使用本地 SQLite、Chroma 和语义 Embedding 配置。DeepSeek LLM、Embedding 和知识库均通过启动检查后服务才会进入 ready 状态；当前后端是可运行的通用编排基础版本，领域业务规则和跨行业评测仍在持续完善。
