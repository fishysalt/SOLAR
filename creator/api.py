# creator/api.py

"""Creator Agent HTTP API - 供 Conductor 调用"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any


# ========== 数据模型 ==========

class TaskRequest(BaseModel):
    instruction: str
    input_files: Optional[List[str]] = []
    context: Optional[Dict[str, Any]] = {}


class TaskRequestV2(TaskRequest):
    task_id: Optional[str] = None
    subtask_id: Optional[str] = ""
    callback_url: Optional[str] = None
    user_id: Optional[str] = "default"


class TaskCancelRequest(BaseModel):
    task_id: str
    reason: Optional[str] = "user_cancelled"


class KnowledgeSearchRequest(BaseModel):
    query: str


class KnowledgeAddRequest(BaseModel):
    content: str
    filename: Optional[str] = None


# ========== 创建 FastAPI 应用 ==========

app = FastAPI(title="Creator Agent API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== 延迟初始化 Creator ==========
# 由 UI 注入，避免重复初始化
_creator = None


def get_creator_instance():
    """获取 Creator 实例（由 UI 注入）"""
    global _creator
    if _creator is None:
        # 如果还没有注入，从 agent 获取（fallback）
        from creator.agent import get_creator
        _creator = get_creator()
    return _creator


# ========== 基础 API ==========

@app.get("/api/status")
async def get_status():
    try:
        creator = get_creator_instance()
        return creator.get_status()
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/task")
async def handle_task(request: TaskRequestV2):
    try:
        creator = get_creator_instance()
        result = await creator.handle_task(
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
    return {"status": "ok", "agent": "creator"}


@app.post("/api/task/cancel")
async def cancel_task(request: TaskCancelRequest):
    try:
        creator = get_creator_instance()
        success = creator.cancel_task(request.task_id)
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
        creator = get_creator_instance()
        memories = creator.memory.get_long_term_all(limit)
        return {"status": "success", "memories": memories}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: int):
    try:
        creator = get_creator_instance()
        success = creator.delete_memory(memory_id)
        return {"status": "success", "deleted": success}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.delete("/api/memory/category/{category}")
async def clear_memory_by_category(category: str):
    try:
        creator = get_creator_instance()
        count = creator.clear_memory_by_category(category)
        return {"status": "success", "deleted_count": count}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.delete("/api/memory/all")
async def clear_all_memory():
    try:
        creator = get_creator_instance()
        count = creator.clear_all_memory()
        return {"status": "success", "deleted_count": count}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ========== RAG 知识库 API ==========

@app.get("/api/knowledge/stats")
async def get_knowledge_stats():
    try:
        creator = get_creator_instance()
        stats = creator.get_knowledge_stats()
        return {"status": "success", "stats": stats}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/knowledge/list")
async def list_knowledge_documents():
    try:
        creator = get_creator_instance()
        documents = creator.get_all_knowledge_documents()
        return {"status": "success", "documents": documents}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/knowledge/search")
async def search_knowledge(request: KnowledgeSearchRequest):
    try:
        creator = get_creator_instance()
        results = creator.search_knowledge(request.query)
        return {"status": "success", "results": results}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/knowledge/add")
async def add_knowledge(request: KnowledgeAddRequest):
    try:
        creator = get_creator_instance()
        filename = creator.add_knowledge_document(request.content, request.filename)
        return {"status": "success", "filename": filename}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get("/api/knowledge/{filename}")
async def get_knowledge_document(filename: str):
    try:
        creator = get_creator_instance()
        content = creator.get_knowledge_document_content(filename)
        if content:
            return {"status": "success", "content": content}
        return {"status": "error", "error": "文档不存在"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.delete("/api/knowledge/{filename}")
async def delete_knowledge_document(filename: str):
    try:
        creator = get_creator_instance()
        success = creator.delete_knowledge_document(filename)
        return {"status": "success", "deleted": success}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/api/knowledge/reload")
async def reload_knowledge():
    try:
        creator = get_creator_instance()
        creator.reload_knowledge()
        return {"status": "success", "message": "知识库已重新加载"}
    except Exception as e:
        return {"status": "error", "error": str(e)}