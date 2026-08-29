# 面向银行业监管制度与统计报表的可信 RAG 问答

本项目提供一个面向银行监管制度和统计报表的本地可信问答原型。回答可给出可信状态、来源引用和证据定位；对表格取数可给出工作表、单元格、表头和计算轨迹。

## 源码公开版

这是**源码公开版**：仓库不包含原始监管附件、预构建知识库、预构建索引或开发评测数据。特别是，不包含预构建索引，也不包含开发评测数据。

使用者须自行获得合法可访问的数据，并自行确认其访问条件、处理条件和再分发权。不得因为本项目提供了解析或索引代码，就推定第三方材料可以公开、复制或再分发。数据与凭证边界见 [DATA_AND_SECURITY.md](DATA_AND_SECURITY.md)。

## 运行环境

- Python：3.10 或更高版本
- 操作系统：macOS / Linux
- 默认 Web 端口：`8501`

应用不要求 API Key，也不调用外部模型服务。首次安装 Python 依赖可能需要网络；构建索引和运行问答均在本地执行。

## 安装、构建与启动

在项目根目录执行：

```bash
python -m pip install -r requirements.txt
python scripts/build_index.py --attachments-dir /absolute/path/to/your/attachments
bash run.sh
```

启动后访问：

```text
http://localhost:8501
```

`build_index.py` 读取你本地提供的附件，将派生的中间产物写入 `data/processed/`，并将索引写入 `outputs/indexes/`。这些路径均被 Git 忽略，不应提交或公开。`run.sh` 只在索引文件存在且结构完整时启动应用；缺少索引时会拒绝启动。

旧版 `.xls` 优先使用 `xlrd` 结构化解析；若无法结构化解析，构建会报告失败，不会将二进制乱码写入索引。旧版 `.doc` 的解析在 macOS 上可能依赖系统自带的 `textutil`。

## 测试

安装开发依赖并执行测试：

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

公开仓库的测试不依赖原始监管附件、预构建索引或开发评测结果。若你使用自备数据进行本地评估，请将评测记录保留在 Git 忽略目录中，且不要把题目、答案、证据或派生索引提交到公开仓库。

## 许可

本项目代码采用 [MIT License](LICENSE)。该许可仅适用于本仓库中由项目作者拥有版权的代码和文档；不授予任何第三方数据、监管材料、附件或其派生内容的访问、复制或再分发权利。
