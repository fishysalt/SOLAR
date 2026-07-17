"""engineer 辅助函数 - 包含回调发送和取消管理"""

from datetime import datetime
from typing import Optional, Dict, Any, List
import asyncio
import aiohttp
import threading


# ========== 原有函数 ==========

def log_with_timestamp(agent_name: str, level: str, message: str, error: bool = False):
    """带时间戳的日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = "[ERROR] " if error else ""
    print(f"[{timestamp}] [{agent_name}] [{level}] {prefix}{message}")


def log_process(agent_name: str, content: str, emoji: str = "🔧"):
    """过程日志（调试用）"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{agent_name}] [PROCESS] {emoji} {content}")


# ========== 取消管理 ==========

_cancelled_tasks: set = set()
_cancel_lock = threading.Lock()


def mark_task_cancelled(task_id: str):
    """标记任务为已取消"""
    with _cancel_lock:
        _cancelled_tasks.add(task_id)
        log_with_timestamp("utils", "INFO", f"任务已标记取消: {task_id}")


def is_task_cancelled(task_id: str) -> bool:
    """检查任务是否已被取消"""
    if not task_id:
        return False
    with _cancel_lock:
        return task_id in _cancelled_tasks


def clear_cancelled_task(task_id: str):
    """清理取消标记"""
    with _cancel_lock:
        _cancelled_tasks.discard(task_id)


# ========== 回调发送 ==========

async def send_callback(
    callback_url: str,
    task_id: str,
    status: str,
    result: Optional[str] = None,
    error: Optional[str] = None,
    output_files: Optional[List[str]] = None,
    subtask_id: str = ""
) -> bool:
    """
    发送任务完成回调到 Conductor
    """
    if not callback_url:
        log_with_timestamp("utils", "WARNING", "无 callback_url，跳过回调")
        return False

    payload = {
        "task_id": task_id,
        "subtask_id": subtask_id,
        "status": status,
        "result": result,
        "error": error,
        "output_files": output_files or []
    }

    log_with_timestamp("utils", "INFO", f"📤 发送回调到 {callback_url}: task_id={task_id}, status={status}")

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession() as session:
            async with session.post(callback_url, json=payload, timeout=timeout) as resp:
                if resp.status == 200:
                    log_with_timestamp("utils", "INFO", f"✅ 回调成功: {task_id}")
                    return True
                else:
                    text = await resp.text()
                    log_with_timestamp("utils", "WARNING", f"⚠️ 回调返回 {resp.status}: {text[:100]}")
                    return False
    except asyncio.TimeoutError:
        log_with_timestamp("utils", "WARNING", f"⏰ 回调超时: {callback_url}")
        return False
    except aiohttp.ClientConnectorError as e:
        log_with_timestamp("utils", "WARNING", f"🔌 回调连接失败: {e}")
        return False
    except Exception as e:
        log_with_timestamp("utils", "WARNING", f"❌ 回调异常: {e}")
        return False


async def send_progress_callback(
    callback_url: str,
    task_id: str,
    progress: int,
    message: str,
    subtask_id: str = ""
) -> bool:
    """
    发送进度更新回调（可选）
    """
    if not callback_url:
        return False

    payload = {
        "task_id": task_id,
        "subtask_id": subtask_id,
        "status": "progress",
        "progress": progress,
        "message": message
    }

    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession() as session:
            async with session.post(callback_url, json=payload, timeout=timeout) as resp:
                return resp.status == 200
    except:
        return False