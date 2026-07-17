"""Conductor HTTP API - 供UI和子Agent调用"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from conductor.agent import get_conductor


# ========== 数据模型 ==========

class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    task_id: str
    status: str = "created"
    message: str


class CallbackRequest(BaseModel):
    task_id: str
    subtask_id: str = ""
    status: str
    result: Optional[str] = None
    error: Optional[str] = None
    output_files: List[str] = []


class CancelRequest(BaseModel):
    task_id: str
    reason: str = "user_cancelled"


# ========== 创建应用 ==========

app = FastAPI(title="Conductor API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

conductor = get_conductor()


# ========== 用户端 API ==========

@app.post("/api/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    """用户发送消息 - 立即返回 task_id"""
    task_id = await conductor.submit_task(
        user_id=request.user_id,
        instruction=request.message
    )
    return ChatResponse(
        task_id=task_id,
        status="created",
        message=f"任务已创建: {task_id}"
    )


@app.get("/api/task/{task_id}")
async def get_task(task_id: str):
    """获取任务状态"""
    summary = conductor.get_task_summary(task_id)
    if summary.get("error"):
        return {"status": "error", "error": summary["error"]}
    return summary


@app.get("/api/tasks/{user_id}")
async def get_user_tasks(user_id: str):
    """获取用户的所有任务（UI轮询用）"""
    tasks = conductor.get_user_tasks(user_id)
    return {"tasks": [t.to_dict() for t in tasks]}


@app.post("/api/task/cancel")
async def cancel_task(request: CancelRequest):
    """取消任务"""
    success = await conductor.cancel_task(request.task_id)
    return {
        "success": success,
        "task_id": request.task_id,
        "message": f"任务 {request.task_id} 已取消" if success else "取消失败"
    }


# ========== 子Agent回调 API ==========

@app.post("/api/callback")
async def receive_callback(request: CallbackRequest):
    """接收子Agent的任务完成回调"""
    print(f"📥 [API] 收到回调: task_id={request.task_id}, status={request.status}")
    
    success = await conductor.handle_callback(
        task_id=request.task_id,
        subtask_id=request.subtask_id,
        status=request.status,
        result=request.result,
        error=request.error,
        output_files=request.output_files
    )
    
    if success:
        return {"status": "ok", "message": f"回调处理成功: {request.task_id}"}
    else:
        return {"status": "error", "message": f"回调处理失败: 任务 {request.task_id} 不存在"}


# ========== 健康检查 ==========

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "agent": "conductor"}


@app.get("/api/ready")
async def readiness_check():
    return {"status": "ready"}


# ========== 启动入口 ==========

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=7860)