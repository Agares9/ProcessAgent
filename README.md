# 制造业 PDF 知识库处理

原始资料位于 `文档/`，保持不变。处理输出使用 `manufacturing-data/`：

`raw/`（建议复制或软链接原始 PDF）、`parsed/`（逐页原始提取）、`normalized/`（Markdown）、`chunks/`（JSONL）、`manifests/`、`reviewed/`、`rejected/`。

先运行少量样本：

```powershell
python scripts/pdf_pipeline.py --sample --input 文档 --output manufacturing-data
```

也可显式传入 PDF。脚本不会默认批量扫描全部文件；PyMuPDF 提取为空的页面标记为 `needs_ocr`，只有传入 `--ocr-command` 才会调用 OCR。来源 URL、许可、工艺和案例字段默认为待人工确认。
