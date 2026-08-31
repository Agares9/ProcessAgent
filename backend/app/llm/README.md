# LLM 客户端层

统一 OpenAI 兼容接口（httpx 异步），区分 DeepSeek 与中转站。

## 文件

- `client.py` —— `LLMClient` 基类：自然语言 `complete`、兼容入口 `complete_json`、流式 `stream`
- `structured.py` —— 结构化输出统一适配层：JSON Schema、解析、Pydantic 校验和一次修复
- `errors.py` —— `StructuredOutputError` 统一错误协议
- `deepseek.py` —— DeepSeek 主力对话模型（`deepseek-v4-flash`）
- `relay.py` —— 中转站客户端（OpenAI 兼容，含 `/embeddings`）
- `embeddings.py` —— 向量模型（relay `text-embedding-3-large` / 本地 / 确定性 hash 回退）

## 约定

- 对话模型：DeepSeek（`DEEPSEEK_*` 环境变量）
- Embedding 与 bge reranker：中转站（`RELAY_*`，OpenAI 兼容）；该中转站不支持 bge-m3 embedding。
- 未配置 Key 时快速失败（抛 `LLMError`），不切换到本地规则。
- 要求 JSON 的 Agent 必须使用 `StructuredLLM`；自然语言回答继续使用 `LLMClient.complete()`。
- 当前试行接入 `ScenarioIntentAgent` 与 `LeadAgent`，其结构错误修复失败后明确终止请求。
