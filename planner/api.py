"""Creator Agent HTTP API - 供主 Agent 调用"""

import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from creator.agent import get_creator


# 数据模型
class TaskRequest(BaseModel):
    instruction: str
    input_files: Optional[List[str]] = []
    context: Optional[Dict[str, Any]] = {}


class TaskResponse(BaseModel):
    status: str
    message: str
    output_files: Optional[List[str]] = []
    error: Optional[str] = None


class KnowledgeSearchRequest(BaseModel):
    query: str


class KnowledgeAddRequest(BaseModel):
    content: str
    filename: Optional[str] = None


# 创建 FastAPI 应用
app = FastAPI(title="Creator Agent API", version="1.0.0")

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 获取 Agent 实例
creator = get_creator()


# ========== 基础 API ==========

@app.get("/api/status")
async def get_status():
    """获取 Agent 状态"""
    try:
        return creator.get_status()
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/task")
async def handle_task(request: TaskRequest):
    """处理任务"""
    try:
        result = creator.handle_task(
            instruction=request.instruction,
            input_files=request.input_files
        )
        return result
    except Exception as e:
        return {
            "status": "error",
            "message": "任务处理失败",
            "error": str(e)
        }


@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {"status": "ok", "agent": "creator"}


# ========== 长期记忆 API ==========

@app.get("/api/memory/list")
async def list_memories(limit: int = 50):
    """获取长期记忆列表"""
    try:
        memories = creator.memory.get_long_term_all(limit)
        return {"status": "success", "memories": memories}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: int):
    """删除单条记忆"""
    try:
        success = creator.delete_memory(memory_id)
        return {"status": "success", "deleted": success}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.delete("/api/memory/category/{category}")
async def clear_memory_by_category(category: str):
    """按分类清空记忆"""
    try:
        count = creator.clear_memory_by_category(category)
        return {"status": "success", "deleted_count": count}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.delete("/api/memory/all")
async def clear_all_memory():
    """清空所有记忆"""
    try:
        count = creator.clear_all_memory()
        return {"status": "success", "deleted_count": count}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ========== RAG 知识库 API ==========

@app.get("/api/knowledge/stats")
async def get_knowledge_stats():
    """获取知识库统计"""
    try:
        stats = creator.get_knowledge_stats()
        return {"status": "success", "stats": stats}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/knowledge/list")
async def list_knowledge_documents():
    """列出所有知识文档"""
    try:
        documents = creator.get_all_knowledge_documents()
        return {"status": "success", "documents": documents}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/knowledge/search")
async def search_knowledge(request: KnowledgeSearchRequest):
    """搜索知识库"""
    try:
        results = creator.search_knowledge(request.query)
        return {"status": "success", "results": results}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/knowledge/add")
async def add_knowledge(request: KnowledgeAddRequest):
    """添加知识文档"""
    try:
        filename = creator.add_knowledge_document(request.content, request.filename)
        return {"status": "success", "filename": filename}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/knowledge/{filename}")
async def get_knowledge_document(filename: str):
    """获取知识文档内容"""
    try:
        content = creator.get_knowledge_document_content(filename)
        if content:
            return {"status": "success", "content": content}
        return {"status": "error", "error": "文档不存在"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.delete("/api/knowledge/{filename}")
async def delete_knowledge_document(filename: str):
    """删除知识文档"""
    try:
        success = creator.delete_knowledge_document(filename)
        return {"status": "success", "deleted": success}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/knowledge/reload")
async def reload_knowledge():
    """重新加载知识库"""
    try:
        creator.reload_knowledge()
        return {"status": "success", "message": "知识库已重新加载"}
    except Exception as e:
        return {"status": "error", "error": str(e)}