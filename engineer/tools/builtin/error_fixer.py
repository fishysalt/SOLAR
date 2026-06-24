"""错误诊断与修复 - LLM 自主诊断"""

import json
from pathlib import Path
from typing import Dict, Any, Optional

from shared.error_logger import get_error_logger


def diagnose_error(error_id: str) -> str:
    """
    诊断并修复错误（由 LLM 自主完成所有决策）
    
    这个工具只负责：
    1. 提供错误日志的完整内容
    2. 提供相关的 RAG 经验（如果有）
    3. 让 LLM 自己决定下一步
    
    LLM 可以：
    - 读取错误日志
    - 搜索解决方案
    - 检索 RAG 经验
    - 生成修复方案
    """
    logger = get_error_logger()
    error_log = logger.get_error(error_id)
    
    if not error_log:
        return f"❌ 错误 {error_id} 不存在"
    
    # 获取相关的 RAG 经验（自动检索，供 LLM 参考）
    from engineer.agent import get_engineer
    engineer = get_engineer()
    
    # 用错误信息作为查询，检索相关经验
    error_message = error_log.get("error", {}).get("message", "")
    error_type = error_log.get("error", {}).get("type", "")
    
    query = f"{error_type} {error_message}"
    relevant_experiences = engineer.knowledge_base.search(query, top_k=3)
    
    # 构建诊断上下文
    context = f"""
## 错误诊断任务

请诊断并修复以下错误：

### 错误信息
- **错误 ID**: {error_id}
- **出错的 Agent**: {error_log.get('agent')}
- **原始任务**: {error_log.get('original_task')}
- **错误类型**: {error_log.get('error', {}).get('type')}
- **错误消息**: {error_log.get('error', {}).get('message')}
- **详细信息**: {json.dumps(error_log.get('error', {}).get('details', {}), ensure_ascii=False, indent=2)}

### 相关历史经验
{self._format_experiences(relevant_experiences) if relevant_experiences else "暂无相关历史经验"}

## 诊断指引

1. **分析错误**：仔细阅读错误信息，理解问题本质
2. **搜索方案**：如果需要，使用搜索工具查找解决方案
3. **检索经验**：使用 `search_rag` 搜索类似问题的解决记录
4. **生成修复**：根据分析结果生成修复方案

## 可用的工具
- `read_text_file`: 读取错误日志文件（路径：{logger.get_error_path(error_id)}）
- `search_rag`: 搜索历史经验
- `ai_search_web`: 搜索互联网解决方案
- `browse_page`: 抓取网页内容
- `generate_local_tool`: 生成本地工具
- `normalize_mcp_config`: 生成 MCP 配置

请自主决定使用哪些工具，完成诊断和修复。
## 完成诊断后

1. 调用 `classify_treatment` 获取 RAG 分类建议
2. 调用 `record_treatment` 记录治疗结果（必须指定分类）
3. 分类名称使用已有分类或创建新分类

**分类示例**：
- `api_key_issues`: API Key 相关错误
- `tool_not_found`: 工具不存在
- `tool_generation`: 工具生成相关
- `mcp_config`: MCP 配置问题
- `network_timeout`: 网络超时
- `general`: 其他通用错误

"""

    return context

# engineer/tools/builtin/error_fixer.py
def record_treatment(
    error_id: str,
    diagnosis: str,
    solution: str,
    files_modified: str,
    rag_category: str = None,  # 新增：RAG 分类
    verification: str = "",
    status: str = "pending_verification"
) -> str:
    """
    记录治疗结果，并存入 RAG
    
    Args:
        error_id: 错误 ID
        diagnosis: 诊断结论
        solution: 修复方案
        files_modified: 修改的文件列表
        rag_category: RAG 分类（必须指定，先调用 classify_treatment 获取建议）
        verification: 验证结果
        status: 状态
    """
    from shared.error_logger import get_error_logger
    from .rag_manager import add_rag_record
    
    logger = get_error_logger()
    files_list = [f.strip() for f in files_modified.split(',') if f.strip()]
    
    # 1. 保存治疗记录
    result = logger.record_treatment(...)
    
    # 2. 存入 RAG（强制）
    if rag_category:
        rag_record = {
            "time": datetime.now().isoformat(),
            "tool": "engineer_diagnosis",
            "input": {
                "error_id": error_id,
                "diagnosis": diagnosis[:200],
                "solution": solution[:200]
            },
            "success": status == "verified",
            "output": f"治疗记录已保存: {result}",
            "error": None if status != "failed" else solution
        }
        add_rag_record(category=rag_category, record=rag_record)
        rag_note = f"\n📚 已存入 RAG 分类: `{rag_category}`"
    else:
        rag_note = "\n⚠️ 未指定 RAG 分类，请先调用 `classify_treatment` 获取建议"
    
    return f"""
✅ 治疗记录已保存

📁 记录文件: {result}
📋 错误 ID: {error_id}
🔧 修改文件: {files_modified}
📊 状态: {status}
{rag_note}
"""


def _format_experiences(self, experiences: list) -> str:
    """格式化 RAG 经验"""
    lines = []
    for exp in experiences:
        lines.append(f"- **{exp.get('source', '经验')}**: {exp.get('content', '')[:300]}")
    return "\n".join(lines)


# 工具定义
DIAGNOSE_ERROR_TOOL = {
    "name": "diagnose_error",
    "description": """诊断并修复错误。

这是一个自主诊断工具，你（LLM）需要：
1. 分析错误信息
2. 决定使用哪些工具（搜索、RAG、读取日志等）
3. 执行修复
4. 返回诊断报告

参数：
- error_id: 错误 ID（如 "creator_error_001"）

你会收到完整的错误上下文和历史经验，请自主完成诊断。
""",
    "func": diagnose_error,
    "parameters": {
        "type": "object",
        "properties": {
            "error_id": {"type": "string", "description": "错误 ID"}
        },
        "required": ["error_id"]
    }
}

# 在 error_fixer.py 末尾添加

RECORD_TREATMENT_TOOL = {
    "name": "record_treatment",
    "description": """记录诊断和治疗结果。

在完成错误诊断和修复后调用此工具保存治疗记录。

参数：
- error_id: 错误 ID
- diagnosis: 诊断结论
- solution: 修复方案描述
- files_modified: 修改的文件列表（逗号分隔）
- verification: 验证结果
- status: 状态（pending_verification/verified/failed）
""",
    "func": record_treatment,
    "parameters": {
        "type": "object",
        "properties": {
            "error_id": {"type": "string", "description": "错误 ID"},
            "diagnosis": {"type": "string", "description": "诊断结论"},
            "solution": {"type": "string", "description": "修复方案"},
            "files_modified": {"type": "string", "description": "修改的文件，逗号分隔"},
            "verification": {"type": "string", "description": "验证结果", "default": ""},
            "status": {"type": "string", "description": "状态", "enum": ["pending_verification", "verified", "failed"], "default": "pending_verification"}
        },
        "required": ["error_id", "diagnosis", "solution", "files_modified"]
    }
}