# 制造业 PDF 知识库处理

## 本地 RAG 入库

`manufacturing-data/` 中的资料已经完成解析和分块。本地方案使用 SQLite 保存文档与 Chunk，
使用 Chroma 保存向量，Embedding 使用本地 `BAAI/bge-small-zh-v1.5`，不需要 Docker。

```powershell
conda activate medix-swarm
cd D:\workfile\ProcessAgent\backend

python -m scripts.import_manufacturing_rag --source ../manufacturing-data --dry-run
python -m scripts.import_manufacturing_rag --source ../manufacturing-data
python -m scripts.query_local_rag "如何降低工业压缩空气系统的能源浪费"
```

持久化文件位于 `local-data/`，该目录不会提交到 Git。重复执行导入命令会按 `doc_id` 和
`chunk_id` 覆盖更新，不会重复累积。

原始资料位于 `文档/`，保持不变。处理输出使用 `manufacturing-data/`：

`raw/`（建议复制或软链接原始 PDF）、`parsed/`（逐页原始提取）、`normalized/`（Markdown）、`chunks/`（JSONL）、`manifests/`、`reviewed/`、`rejected/`。

先运行少量样本：

```powershell
python scripts/pdf_pipeline.py --sample --input 文档 --output manufacturing-data
```

也可显式传入 PDF。脚本不会默认批量扫描全部文件；PyMuPDF 提取为空的页面标记为 `needs_ocr`，只有传入 `--ocr-command` 才会调用 OCR。来源 URL、许可、工艺和案例字段默认为待人工确认。
