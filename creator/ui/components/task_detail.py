"""任务详情组件"""

from nicegui import ui
from typing import Dict, Any, Optional, Callable


def create_task_detail(
    task_data: Dict[str, Any],
    on_back: Callable,
    on_cancel: Optional[Callable] = None
):
    """创建任务详情视图"""
    # 调试日志
    print(f"📋 create_task_detail 收到: {task_data}")
    
    # 安全获取字段
    task_id = task_data.get("task_id") or task_data.get("id") or "unknown"
    status = task_data.get("status", "unknown")
    instruction = task_data.get("instruction", "")
    final_result = task_data.get("final_result")
    error = task_data.get("error")
    progress = task_data.get("progress", 0)
    created_at = task_data.get("created_at", "")
    completed_at = task_data.get("completed_at")
    subtasks = task_data.get("subtasks", [])
    
    print(f"📋 解析后: task_id={task_id}, status={status}, subtasks={len(subtasks)}")
    
    status_config = {
        "created": {"icon": "📋", "color": "blue", "label": "已创建"},
        "running": {"icon": "🔄", "color": "orange", "label": "执行中"},
        "waiting": {"icon": "⏳", "color": "orange", "label": "等待中"},
        "completed": {"icon": "✅", "color": "green", "label": "已完成"},
        "failed": {"icon": "❌", "color": "red", "label": "失败"},
        "cancelled": {"icon": "⏹️", "color": "gray", "label": "已取消"},
    }
    config = status_config.get(status, {"icon": "❓", "color": "gray", "label": "未知"})
    
    with ui.column().classes("w-full gap-4 p-4"):
        # 顶部：返回按钮 + 标题
        with ui.row().classes("w-full justify-between items-center"):
            ui.button("← 返回", on_click=on_back).props("flat size=sm")
            with ui.row().classes("items-center gap-2"):
                ui.label(config["icon"]).classes("text-2xl")
                ui.label(task_id).classes("font-mono text-lg font-bold")
                ui.badge(config["label"], color=config["color"])
        
        # 进度
        ui.label(f"进度: {progress}%").classes("text-sm")
        ui.linear_progress(value=progress / 100, show_value=False)
        
        # 基本信息
        with ui.card().classes("w-full"):
            ui.label("📝 任务指令").classes("font-bold text-sm text-gray-600")
            ui.label(instruction).classes("text-base")
            
            with ui.row().classes("w-full gap-4 text-sm text-gray-500 mt-2"):
                ui.label(f"创建: {created_at[:16] if created_at else '未知'}")
                if completed_at:
                    ui.label(f"完成: {completed_at[:16]}")
        
        # 子任务列表
        if subtasks:
            with ui.card().classes("w-full"):
                ui.label("📋 子任务").classes("font-bold text-sm text-gray-600")
                for st in subtasks:
                    status_icon = {
                        "pending": "⏳",
                        "running": "🔄",
                        "waiting": "⏳",
                        "completed": "✅",
                        "failed": "❌",
                        "cancelled": "⏹️"
                    }.get(st.get("status", ""), "❓")
                    
                    with ui.row().classes("w-full justify-between items-center border-b border-gray-100 py-1"):
                        with ui.row().classes("items-center gap-2"):
                            ui.label(status_icon).classes("text-sm")
                            ui.label(st.get("agent_name", "unknown")).classes("font-mono text-sm")
                            ui.label(st.get("instruction", "")[:40]).classes("text-sm text-gray-600")
                        ui.label(st.get("status", "")).classes("text-xs text-gray-400")
        else:
            with ui.card().classes("w-full bg-gray-50"):
                ui.label("暂无子任务").classes("text-sm text-gray-400")
        
        # 结果
        if final_result:
            with ui.card().classes("w-full bg-green-50 border border-green-200"):
                ui.label("✅ 结果").classes("font-bold text-sm text-green-700")
                ui.label(final_result).classes("text-base")
        
        # 错误
        if error:
            with ui.card().classes("w-full bg-red-50 border border-red-200"):
                ui.label("❌ 错误").classes("font-bold text-sm text-red-700")
                ui.label(error).classes("text-base text-red-600")
        
        # 取消按钮
        if on_cancel and status in ["created", "running", "waiting"]:
            ui.button("取消任务", on_click=lambda: on_cancel(task_id), color="red").classes("w-full")