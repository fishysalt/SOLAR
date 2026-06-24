"""RAG 自生成管理 - 每个功能一个 txt 文件"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from conductor.utils import log_with_timestamp


# 功能分类配置文件（新增功能只需添加一项）
RAG_CATEGORIES = {
    "video_generation": {
        "file": "video_generation.txt",
        "description": "视频生成记录",
        "max_records": 15
    },
    "image_generation": {
        "file": "image_generation.txt",
        "description": "图片生成记录",
        "max_records": 15
    },
    "mcp_tool": {
        "file": "mcp_tool.txt",
        "description": "MCP 工具调用记录",
        "max_records": 15
    }
}



def search_rag_structured(keyword: str) -> List[Dict]:
    """返回结构化的搜索结果"""
    keyword_lower = keyword.lower()
    matches = []
    
    for cat in RAG_CATEGORIES.keys():
        records = _load_records(cat)
        for rec in records:
            if (keyword_lower in rec.get("tool", "").lower() or
                keyword_lower in json.dumps(rec.get("input", {}), ensure_ascii=False).lower()):
                matches.append({
                    "category": cat,
                    "tool": rec.get("tool"),
                    "input": rec.get("input"),
                    "success": rec.get("success"),
                    "output": rec.get("output"),
                    "error": rec.get("error"),
                    "time": rec.get("time")
                })
    
    return matches


def _get_rag_dir() -> Path:
    """获取 RAG 目录"""
    current_dir = Path(__file__).parent
    engineer_root = current_dir.parent.parent
    rag_dir = engineer_root / "rag"
    rag_dir.mkdir(parents=True, exist_ok=True)
    return rag_dir


def _load_records(category: str) -> List[Dict]:
    """加载指定分类的记录（从 txt 文件）"""
    if category not in RAG_CATEGORIES:
        return []
    
    rag_dir = _get_rag_dir()
    file_path = rag_dir / RAG_CATEGORIES[category]["file"]
    
    if not file_path.exists():
        return []
    
    records = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception as e:
        log_with_timestamp("rag_manager", "ERROR", f"加载记录失败: {e}")
    
    return records


def _save_records(category: str, records: List[Dict]) -> bool:
    """保存记录到 txt 文件（每行一条 JSON）"""
    if category not in RAG_CATEGORIES:
        return False
    
    rag_dir = _get_rag_dir()
    file_path = rag_dir / RAG_CATEGORIES[category]["file"]
    
    # 限制记录数量（保留最近的 max_records 条）
    max_records = RAG_CATEGORIES[category]["max_records"]
    if len(records) > max_records:
        records = records[-max_records:]
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
        return True
    except Exception as e:
        log_with_timestamp("rag_manager", "ERROR", f"保存记录失败: {e}")
        return False


def add_rag_record(category: str, record: Dict) -> str:
    """
    添加一条 RAG 记录（供工具调用）
    
    Args:
        category: 功能分类（video_generation, image_generation, mcp_tool）
        record: 记录内容，包含 tool, input, success, output, error
    """
    if category not in RAG_CATEGORIES:
        return f"❌ 无效分类: {category}。可用: {', '.join(RAG_CATEGORIES.keys())}"
    
    # 确保必填字段
    if "tool" not in record:
        return "❌ 记录缺少 tool 字段"
    
    records = _load_records(category)
    records.append(record)
    
    if _save_records(category, records):
        return f"✅ 已记录到 {category}"
    else:
        return "❌ 保存失败"


def list_rag_categories() -> str:
    """列出所有 RAG 分类及统计"""
    result = ["📚 RAG 知识库分类:\n"]
    for cat, info in RAG_CATEGORIES.items():
        records = _load_records(cat)
        success_count = sum(1 for r in records if r.get("success", False))
        fail_count = len(records) - success_count
        result.append(f"- **{cat}**: {info['description']}")
        result.append(f"  记录: {len(records)}/{info['max_records']} (成功:{success_count} 失败:{fail_count})")
        result.append("")
    return "\n".join(result)


def view_rag_records(category: str = None, limit: int = 10) -> str:
    """查看 RAG 记录"""
    if category:
        if category not in RAG_CATEGORIES:
            return f"❌ 无效分类: {category}"
        categories = [category]
    else:
        categories = list(RAG_CATEGORIES.keys())
    
    result = []
    for cat in categories:
        records = _load_records(cat)
        if not records:
            result.append(f"### {cat}: 暂无记录")
            continue
        
        result.append(f"### {cat}: {len(records)} 条记录")
        for rec in records[-limit:]:
            status = "✅" if rec.get("success") else "❌"
            result.append(f"\n{status} **{rec.get('tool', 'unknown')}** @ {rec.get('time', '')[:16]}")
            result.append(f"   输入: {json.dumps(rec.get('input', {}), ensure_ascii=False)[:100]}")
            if rec.get("success"):
                result.append(f"   输出: {rec.get('output', '')[:100]}")
            else:
                result.append(f"   错误: {rec.get('error', '')[:100]}")
        result.append("")
    
    return "\n".join(result) if result else "📭 暂无记录"


def clear_rag_category(category: str, confirm: bool = False) -> str:
    """清空指定分类的所有记录"""
    if category not in RAG_CATEGORIES:
        return f"❌ 无效分类: {category}"
    
    records = _load_records(category)
    if not records:
        return f"📭 分类 '{category}' 已为空"
    
    if not confirm:
        return f"⚠️ 确认清空 '{category}'（共 {len(records)} 条）？再次调用并设置 confirm=true"
    
    _save_records(category, [])
    return f"✅ 已清空 '{category}'"


def search_rag(keyword: str) -> str:
    """搜索 RAG 记录（在工具名和输入中搜索）"""
    keyword_lower = keyword.lower()
    matches = []
    
    for cat in RAG_CATEGORIES.keys():
        records = _load_records(cat)
        for rec in records:
            if (keyword_lower in rec.get("tool", "").lower() or
                keyword_lower in json.dumps(rec.get("input", {}), ensure_ascii=False).lower()):
                matches.append({"category": cat, "record": rec})
    
    if not matches:
        return f"🔍 未找到与 '{keyword}' 相关的记录"
    
    result = [f"🔍 找到 {len(matches)} 条相关记录:\n"]
    for m in matches[:10]:
        rec = m["record"]
        status = "✅" if rec.get("success") else "❌"
        result.append(f"### [{m['category']}] {status} {rec.get('tool')}")
        result.append(f"   时间: {rec.get('time', '')[:16]}")
        result.append(f"   输入: {json.dumps(rec.get('input', {}), ensure_ascii=False)[:150]}")
        result.append("")
    
    return "\n".join(result)

def classify_treatment(
    error_type: str,
    error_message: str,
    tool_name: str = None
) -> str:
    """
    根据错误信息，建议 RAG 分类
    
    这个工具会：
    1. 列出当前 RAG 已有的分类
    2. 根据错误信息匹配最合适的分类
    3. 如果没有匹配，建议创建新分类
    
    Args:
        error_type: 错误类型
        error_message: 错误消息
        tool_name: 出错的工具名称
    
    Returns:
        建议的分类名称 + 已有的分类列表
    """
    from .rag_manager import RAG_CATEGORIES, list_rag_categories
    
    # 获取所有已有分类
    categories_info = list_rag_categories()
    
    # 基于关键词匹配建议分类
    suggested = "general"
    keyword_map = {
        "api": "api_key_issues",
        "key": "api_key_issues",
        "认证": "api_key_issues",
        "auth": "api_key_issues",
        "timeout": "network_timeout",
        "超时": "network_timeout",
        "tool": "tool_not_found",
        "not found": "tool_not_found",
        "不存在": "tool_not_found",
        "permission": "permission_denied",
        "权限": "permission_denied",
        "tool_generation": "tool_generation",
        "生成工具": "tool_generation",
        "mcp": "mcp_config",
        "config": "mcp_config",
        "配置": "mcp_config",
    }
    
    combined = f"{error_type} {error_message} {tool_name or ''}".lower()
    for keyword, category in keyword_map.items():
        if keyword in combined:
            suggested = category
            break
    
    # 检查建议的分类是否已存在
    existing_categories = list(RAG_CATEGORIES.keys()) if hasattr(RAG_CATEGORIES, 'keys') else []
    if suggested in existing_categories:
        suggestion_note = f"建议使用已有分类: **{suggested}**"
    else:
        suggestion_note = f"建议创建新分类: **{suggested}**（当前不存在）"
    
    return f"""
## RAG 分类建议

### 已有分类
{self._format_categories(existing_categories) if existing_categories else "暂无分类"}

### 分类建议
{suggestion_note}

### 决策指引
- 如果建议的分类存在，请使用该分类
- 如果建议的分类不存在，请使用 `create_rag_category` 创建新分类
- 创建新分类时，名称使用英文小写 + 下划线（如 `api_key_issues`）

### 完整流程
1. 查看已有分类
2. 决定使用已有分类或创建新分类
3. 调用 `add_rag_record` 时传入正确的分类名称
"""


def _format_categories(categories: list) -> str:
    lines = []
    for cat in categories:
        lines.append(f"- `{cat}`")
    return "\n".join(lines)


# 工具定义
ADD_RAG_RECORD_TOOL = {
    "name": "add_rag_record",
    "description": "添加 RAG 记录。每次工具调用完成后自动调用。",
    "func": add_rag_record,
    "parameters": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "功能分类"},
            "record": {"type": "object", "description": "记录内容"}
        },
        "required": ["category", "record"]
    }
}

LIST_RAG_CATEGORIES_TOOL = {
    "name": "list_rag_categories",
    "description": "列出 RAG 分类及统计。",
    "func": list_rag_categories,
    "parameters": {"type": "object", "properties": {}, "required": []}
}

VIEW_RAG_RECORDS_TOOL = {
    "name": "view_rag_records",
    "description": "查看 RAG 记录。",
    "func": view_rag_records,
    "parameters": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "分类"},
            "limit": {"type": "integer", "description": "显示条数", "default": 10}
        },
        "required": []
    }
}

CLEAR_RAG_CATEGORY_TOOL = {
    "name": "clear_rag_category",
    "description": "清空指定分类的 RAG 记录。",
    "func": clear_rag_category,
    "parameters": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "分类"},
            "confirm": {"type": "boolean", "description": "确认", "default": False}
        },
        "required": ["category"]
    }
}

SEARCH_RAG_TOOL = {
    "name": "search_rag",
    "description": "搜索 RAG 记录。",
    "func": search_rag,
    "parameters": {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "关键词"}
        },
        "required": ["keyword"]
    }
}

