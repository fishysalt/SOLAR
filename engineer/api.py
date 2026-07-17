"""engineer Agent HTTP API - 供 Conductor 调用"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from engineer.agent import get_engineer
from engineer.models import CancelRequest


# ========== 数据模型 ==========

class TaskRequest(BaseModel):
    """原有任务请求（保持兼容）"""
    instruction: str
    input_files: Optional[List[str]] = []
    context: Optional[Dict[str, Any]] = {}


class TaskRequestV2(TaskRequest):
    """
    扩展的任务请求 - 支持 task_id 和 callback_url
    """
    task_id: Optional[str] = None
    subtask_id: Optional[str] = ""
    callback_url: Optional[str] = None
    user_id: Optional[str] = "default"


class TaskCancelRequest(BaseModel):
    """取消任务请求"""
    task_id: str
    reason: Optional[str] = "user_cancelled"


class KnowledgeSearchRequest(BaseModel):
    query: str


class KnowledgeAddRequest(BaseModel):
    content: str
    filename: Optional[str] = None


# ========== 创建 FastAPI 应用 ==========

app = FastAPI(title="Engineer Agent API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engineer = get_engineer()


# ========== 基础 API ==========

@app.get("/api/status")
async def get_status():
    """获取 Agent 状态"""
    try:
        return engineer.get_status()
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/task")
async def handle_task(request: TaskRequestV2):
    """
    处理任务 - 支持 task_id 和 callback_url

    兼容旧版本：不带 task_id 的调用仍然工作
    """
    try:
        result = await engineer.handle_task(
            instruction=request.instruction,
            input_files=request.input_files,
            task_id=request.task_id,
            subtask_id=request.subtask_id or "",
            callback_url=request.callback_url,
            user_id=request.user_id or "default"
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
    return {"status": "ok", "agent": "engineer"}


# ========== 任务取消 API ==========

@app.post("/api/task/cancel")
async def cancel_task(request: TaskCancelRequest):
    """
    取消任务

    Conductor 调用此端点通知 engineer 取消正在执行的任务
    """
    try:
        success = engineer.cancel_task(request.task_id)
        return {
            "status": "success" if success else "error",
            "task_id": request.task_id,
            "message": f"任务 {request.task_id} 已标记取消" if success else f"取消失败"
        }
    except Exception as e:
        return {
            "status": "error",
            "task_id": request.task_id,
            "error": str(e)
        }


# ========== 长期记忆 API ==========

@app.get("/api/memory/list")
async def list_memories(limit: int = 50):
    try:
        memories = engineer.memory.get_long_term_all(limit)
        return {"status": "success", "memories": memories}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: int):
    try:
        success = engineer.delete_memory(memory_id)
        return {"status": "success", "deleted": success}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.delete("/api/memory/category/{category}")
async def clear_memory_by_category(category: str):
    try:
        count = engineer.clear_memory_by_category(category)
        return {"status": "success", "deleted_count": count}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.delete("/api/memory/all")
async def clear_all_memory():
    try:
        count = engineer.clear_all_memory()
        return {"status": "success", "deleted_count": count}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ========== RAG 知识库 API ==========

@app.get("/api/knowledge/stats")
async def get_knowledge_stats():
    try:
        stats = engineer.get_knowledge_stats()
        return {"status": "success", "stats": stats}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/knowledge/list")
async def list_knowledge_documents():
    try:
        documents = engineer.get_all_knowledge_documents()
        return {"status": "success", "documents": documents}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/knowledge/search")
async def search_knowledge(request: KnowledgeSearchRequest):
    try:
        results = engineer.search_knowledge(request.query)
        return {"status": "success", "results": results}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/knowledge/add")
async def add_knowledge(request: KnowledgeAddRequest):
    try:
        filename = engineer.add_knowledge_document(request.content, request.filename)
        return {"status": "success", "filename": filename}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/knowledge/{filename}")
async def get_knowledge_document(filename: str):
    try:
        content = engineer.get_knowledge_document_content(filename)
        if content:
            return {"status": "success", "content": content}
        return {"status": "error", "error": "文档不存在"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.delete("/api/knowledge/{filename}")
async def delete_knowledge_document(filename: str):
    try:
        success = engineer.delete_knowledge_document(filename)
        return {"status": "success", "deleted": success}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/knowledge/reload")
async def reload_knowledge():
    try:
        engineer.reload_knowledge()
        return {"status": "success", "message": "知识库已重新加载"}
    except Exception as e:
        return {"status": "error", "error": str(e)}