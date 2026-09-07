# Nautilus v1 实现总结

## 文件清单（实际）

**7 个文件已创建**，位于 `...\AIAgent\mycodingagent\nautilus\`：

| 文件 | 实际行数 | 职责 |
|------|---------|------|
| `pyproject.toml` | 16 | 项目元数据 + openai 依赖 + CLI 入口 |
| `nautilus/__init__.py` | 1 | 版本号 |
| `nautilus/prompts.py` | 20 | 系统提示词（定义 agent 行为准则） |
| `nautilus/tools.py` | 189 | 4 个工具 schema + read_file/write_file/edit_file/bash + execute_tool 路由 |
| `nautilus/llm.py` | 19 | OpenAI 兼容 client 工厂 |
| `nautilus/agent.py` | 81 | **核心 ReAct 循环**（think→act→observe→repeat） |
| `nautilus/__main__.py` | 68 | CLI 入口（argparse） |

**总计 378 行 Python**（比 ~200 目标略多，主要是工具 schema 的 JSON 定义和 edit_file 的精确匹配逻辑占了不少行）。

## 验证结果

- ✅ 所有模块导入正常
- ✅ CLI `--help` 输出正确
- ✅ 四个工具函数实测可用（write→read roundtrip、edit 精确替换+多处匹配拦截、bash 成功/失败均正确捕获）

## 使用方式

```bash
cd ".../AIAgent/mycodingagent/nautilus"
pip install -e .
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://xxx   # 可选，OpenAI 兼容 API
nautilus "创建一个 hello.py，运行它，确认输出 hello world"
```

## 核心洞察

这就是整个 agent 的本质——**LLM + 4 个工具 + 一个 while 循环**。Claude Code 的 51 万行是在这 378 行之上叠加安全/UX/扩展/多 agent 的工程化。
