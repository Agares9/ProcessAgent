# 数据处理方式

##### 采用“原文归档 + 文档治理库 + 结构化工艺库 + 向量库”四层结构，不直接把 PDF 转换成纯文本后全部塞进 Milvus。

  ## 一、采用的数据流

  本地 PDF
    ↓
  文件登记与哈希
    ↓
  文本/表格解析
    ↓
  文档清洗与章节识别
    ↓
  元数据抽取
    ↓
  人工审核
    ↓
  语义分块
    ↓
  MongoDB/PostgreSQL 文档治理库
    ↓
  Milvus 向量索引

  同时保留原始 PDF，结构：

```
  manufacturing-data/
  ├── raw/          原始 PDF，不修改
  ├── parsed/       文本和表格解析结果
  ├── normalized/   标准化 Markdown/JSON
  ├── chunks/       向量化 JSONL
  ├── manifests/    来源、许可、版本、哈希
  ├── reviewed/     审核通过
  └── rejected/     失败或待处理
```



  ## 二、工业标准和实例分开处理

  因为面向企业场景的数据分为国家标准和可行案例：不把“标准”和“案例”放在同一套元数据规则里。

  ### 标准文档

  重点字段：

  {
    "doc_type": "standard",
    "standard_no": "GB/T xxxx",
    "standard_title": "...",
    "organization": "国家标准",
    "status": "active",
    "edition": "2024",
    "effective_date": "2025-01-01",
    "supersedes": "...",
    "scope": "适用范围",
    "process": ["machining"],
    "license": "licensed_or_public"
  }

  标准的回答重点是：

  要求是什么
  适用范围是什么
  检验方法是什么
  限制条件是什么
  当前是否有效

  ### 工艺案例

  重点字段：

  {
    "doc_type": "case_study",
    "case_title": "...",
    "industry": ["automotive"],
    "process": ["compressed_air"],
    "company": "Example Corp",
    "plant_scale": "...",
    "baseline": "...",
    "measure": "...",
    "energy_saving": "...",
    "emission_reduction": "...",
    "investment": "...",
    "payback": "...",
    "measurement_method": "...",
    "applicability": "...",
    "limitations": "...,
    "evidence_level": "A"
  }

  案例的回答重点是：

  谁在什么工厂、什么条件下、采用什么措施、取得什么结果

  ## 三、先做 PDF 解析，不要直接向量化

  ### 文字型 PDF

  先用 PyMuPDF：

  import fitz

  doc = fitz.open("input.pdf")

  pages = []
  for page_no, page in enumerate(doc, start=1):
      pages.append({
          "page": page_no,
          "text": page.get_text("text")
      })

  保留页码，否则以后无法生成可靠引用。

  ### 表格

  表格要同时保存：

  表格 JSON
  +
  可读文本描述

  例如：

  {
    "table_id": "doc-001-table-02",
    "headers": ["参数", "最小值", "最大值", "单位"],
    "rows": [
      ["温度", "180", "220", "°C"]
    ],
    "page": 12
  }

  同时生成：

  参数：温度；范围：180–220 °C；来源：第12页。

  ### 扫描页

  只对没有有效文本的页面 OCR，不要全量 OCR。

  ## 四、统一 Markdown 格式

  每个 PDF 生成一个 Markdown 文件：

---
  doc_id: standard-gb-001
  doc_type: standard
  title: 一般公差
  language: zh
  source_org: 国家标准
  standard_no: GB/T xxxx
  status: active
  process:
    - machining
    source_url: https://...
    license: licensed

```
  retrieved_at: 2026-08-21
  ---

  # 一般公差

  ## 1. 适用范围

  ...

  ## 2. 技术要求

  ...

  ## 3. 检验方法

  ...
```



  ## 来源定位

```
原文件：standard-gb-001.pdf

  - 页码：第 12–18 页

  英文 PDF 保留英文原文，增加：

  language: en
  summary_zh: 中文摘要
  keywords_zh:

   - 压缩空气
     - 泄漏治理
```



  没有把所有英文全文翻译成中文，成本高且可能破坏参数。

  ## 五、分块策略

按章节和语义切分，而不是简单按字符切割。

  ### 标准

  一个条款或一个完整小节作为一个 chunk

  不要把：

  适用范围
  技术要求
  例外条件

  拆到不同 chunk。

  ### 案例

  尽量让一个 chunk 包含：

  背景 + 改造措施 + 条件 + 结果

  推荐：

  500–1000 tokens
  重叠 80–150 tokens

  每个 chunk 带完整元数据：

  {
    "chunk_id": "case-001-0007",
    "doc_id": "case-001",
    "text": "该工厂通过空压站群控改造……",
    "doc_type": "case_study",
    "language": "zh",
    "industry": ["automotive"],
    "process": ["compressed_air"],
    "section": "节能结果",
    "page_start": 5,
    "page_end": 6,
    "source_url": "https://...",
    "evidence_level": "A",
    "review_status": "approved"
  }

  ## 六、MongoDB 和 Milvus 怎么分工

  ### MongoDB/PostgreSQL 保存

  - 原始文档记录；
  - 文档版本；
  - 许可证；
  - 审核状态；
  - 标准状态；
  - 工艺和设备字段；
  - 案例结构化指标；
  - 表格；
  - 文档关系；
  - 处理日志；
  - 权限信息。

  ### Milvus 保存

  - chunk 文本；
  - embedding；
  - doc_id；
  - chunk_id；
  - 行业；
  - 工艺；
  - 材料；
  - 设备；
  - 文档类型；
  - 证据等级；
  - 版本状态；
  - 权限标识。

  Milvus 负责召回，不负责完整文档治理。

  ## 七、检索时使用混合检索

  制造业不只依赖向量相似度。

 比如

```
用户问：

  304不锈钢、3–8 mm板厚的GMAW参数范围是什么？

  应该先解析出：

  {
    "process": "GMAW",
    "material": "304 stainless steel",
    "thickness_mm": [3, 8]
  }

  然后执行：

  关键词检索
  +
  向量检索
  +
  metadata filter
  +
  数值条件过滤
  +
  reranker 重排

  建议检索优先级：

  现行标准

  > 企业验证案例
  > 厂商验证资料
  > 权威技术报告
  > 论文
  > 专利实施例
```



  ## 八、标准和案例要设置不同的证据等级

**采用以下分级：**

  A：法规、强制标准
  B：现行国家/行业标准
  C：企业生产验证
  D：设备/材料厂商验证
  E：论文和技术报告
  F：专利实施例、行业文章

  回答中明确区分：

  标准要求
  厂商推荐值
  企业案例结果
  论文实验结果
  专利实施例

  不能把案例结果说成普遍适用，也不能把专利参数说成生产标准。