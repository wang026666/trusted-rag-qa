# 面向银行业监管制度与统计报表的可信RAG问答

本项目对银行监管制度和统计报表提供本地可信问答。回答同时给出可信状态、引用来源、原始证据；表格取数提供工作表、单元格、表头和计算轨迹。

## 运行环境

推荐运行环境：

- Python：3.10
- 操作系统：macOS / Linux

已验证环境：

- macOS（Apple Silicon）+ Python 3.10
- Web 端口：`8501`

运行版只依赖预构建索引，可在安装依赖完成后离线使用。首次安装 Python 依赖需要网络；运行问答不需要联网，也不需要 API Key。默认配置不读取本地配置文件，也不调用外部模型服务。

## 安装与启动

在项目根目录执行：

```bash
python -m pip install -r requirements.txt
bash run.sh
```

启动后访问：

```text
http://localhost:8501
```

`run.sh` 只检查必要索引并启动应用，不会运行评测、审计、打包、封存或重建任务。

## 索引与数据

运行所需索引已经预构建并随项目提供：

```text
outputs/indexes/bm25_index.json
outputs/indexes/vector_index.json
```

因此正常运行不需要原始附件，也不需要重新构建索引。

项目同时保留团队开发的文档解析、Excel/XLS/XLSX 解析、文本切分、表格结构化和索引构建源码。仅当需要从原始附件重建索引时，执行：

```bash
python scripts/build_index.py --attachments-dir /path/to/nfra_page_attachments_500
```

重建会解析附件并更新 `outputs/indexes/`。旧版 `.xls` 优先通过 `xlrd` 结构化解析；若无法结构化解析，构建将报告失败而不会把二进制乱码写入索引。完整附件重建已在 macOS 上验证；其中旧版 `.doc` 解析依赖系统自带的 `textutil`。

## 测试

执行全部核心与真实数据回归测试：

```bash
python -m unittest discover -s tests -q
```

真实数据回归覆盖：

- 商业银行大额风险暴露制度问答；
- `2025年9月北京原保险保费收入合计`，断言结果为 `3267.58`；
- `火星上有多少家商业银行`，断言拒答；
- `2026年银行业总资产、总负债（月度）` 的真实 XLS 取数，断言 `2026年1月总资产=4806061.691219`。

## 真实量化评测

项目随附可复现实测结果：

```text
evaluation/qa_eval.jsonl
evaluation/metrics.json
```

执行以下命令会基于 `qa_eval.jsonl` 中的“基于赛题资料构建的 300 题四选一 MCQ 开发评测集”和 10 个独立资料外/依据不足压力样本重新生成两份文件：

```bash
python scripts/run_eval.py
```

300 题开发评测集按原始 MCQ 协议调用 `engine.answer(question, top_k=5, options=options)`；正确性仅由预测选项是否与评测集 `answer` 字段完全相等判定。结果分别报告单事实检索、多事实检索、表格取数、表格比较、表格计算，以及制度合并、表格合并和来源命中率。资料外拒答属于独立的 `free_form_eval`，不混入 300 题开发评测集准确率。`qa_eval.jsonl` 同时保留评测题字段、逐题预测及已恢复历史逐题基线的差异记录。

## 轻量知识库清单

```text
knowledge_base/manifest.jsonl
```

该清单包含 500 份已索引资料的 `doc_id`、标题、来源字段、文件类型、相对本地路径和 SHA-256；不包含原始附件或解析中间文件。原始归档中未保留可准确映射的来源页面 URL 和附件 URL，因此 `source_url` 与 `attachment_url` 保持为空，不对其进行猜测或补造。
