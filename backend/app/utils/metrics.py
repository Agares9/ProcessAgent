"""Prometheus 指标：问答时延、检索命中率、采纳率、成本等。"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

QUERY_TOTAL = Counter("processagent_query_total", "总问答次数", ["dept", "intent"])
QUERY_LATENCY = Histogram("processagent_query_latency_seconds", "端到端问答时延", ["dept"])
LLM_LATENCY = Histogram("processagent_llm_latency_seconds", "LLM 调用时延", ["model"])
RETRIEVAL_HIT = Counter("processagent_retrieval_hit_total", "检索命中次数", ["dept"])
RETRIEVAL_MISS = Counter("processagent_retrieval_miss_total", "检索未命中次数", ["dept"])
ADOPTION = Counter("processagent_answer_adoption_total", "回答采纳/点踩次数", ["kind"])
LLM_COST = Gauge("processagent_llm_cost_yuan", "累计 LLM 成本（元）")
FEEDBACK_TOTAL = Counter("processagent_feedback_total", "反馈总数", ["kind"])
SKILL_TRIGGER = Counter("processagent_skill_trigger_total", "Skill 触发次数", ["skill"])
DEPT_AGENT_REQUEST = Counter("processagent_dept_agent_requests_total", "部门 Agent 请求数", ["dept", "status"])
DEPT_AGENT_INFLIGHT = Gauge("processagent_dept_agent_inflight", "部门 Agent 当前在途请求数", ["dept"])
PI_AGENT_EXECUTION = Counter("processagent_pi_agent_execution_total", "pi Agent 执行次数", ["agent", "status"])
STRUCTURED_LLM_REQUEST = Counter(
    "processagent_structured_llm_requests_total", "结构化 LLM 请求次数", ["agent", "format", "outcome"]
)
STRUCTURED_LLM_REPAIR = Counter(
    "processagent_structured_llm_repairs_total", "结构化 LLM 修复次数", ["agent", "outcome"]
)
STRUCTURED_LLM_LATENCY = Histogram(
    "processagent_structured_llm_duration_seconds", "结构化 LLM 端到端时延", ["agent"]
)
STRUCTURED_LLM_VALIDATION_ERROR = Counter(
    "processagent_structured_llm_validation_errors_total", "结构化输出字段校验错误", ["agent", "field"]
)


def record_retrieval_hit(dept: str, hit: bool) -> None:
    (RETRIEVAL_HIT if hit else RETRIEVAL_MISS).labels(dept=dept).inc()


def record_adoption(kind: str) -> None:
    ADOPTION.labels(kind=kind).inc()
