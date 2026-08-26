# 通用场景编排层

Harness 是 ProcessAgent 的统一决策编排层，制造、零售、运输、医药、能源、建筑和金融都使用同一条入口。

## 工作流

```text
ScenarioIntentAgent
  → industry / domain / business_domain / scenario_type
  → ScenarioSkillMatcher
  → ScenarioOrchestratorFacade
  → TaskExecutor
  → 核心 Skill
  → 领域处理器
  → VerifierAgent / OrchestratorAgent
```

## 核心 Skill

对外只暴露 8 个稳定入口：

`retrieve`、`understand`、`analyze`、`compare`、`calculate`、`optimize`、`check`、`verify`。

领域规则通过 `skill_registry.py` 注册，每个领域保持 1～2 个领域处理器。制造业旧 Skill 名称在网关中保留兼容映射，不参与新的规划协议。

## 关键文件

- `orchestrator.py`：统一 `ScenarioOrchestratorFacade` 和结果编排元数据
- `agents/manufacturing_agents.py`：通用意图、上下文和任务规划，保留制造业兼容入口
- `skill_registry.py`：核心 Skill 与领域注册表
- `skill_matcher.py`：行业/领域到核心 Skill 的路由
- `domain_skills.py`：各领域的确定性指标和业务规则
- `manufacturing_skills.py`：受控 Skill 网关和兼容实现
- `task_executor.py`：任务依赖、超时、核心 Skill 分发和 `TaskResult`

## 兼容原则

已有制造业脚本、测试和历史任务可以继续使用旧名称；新代码应使用核心 Skill，并通过 `calculation_type`、`analysis_type` 和场景上下文选择具体领域逻辑。
