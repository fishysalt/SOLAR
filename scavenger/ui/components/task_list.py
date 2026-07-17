"""任务列表组件"""

from nicegui import ui
from typing import List, Dict, Any, Callable, Optional


def create_task_card(
    task_data: Dict[str, Any],
    on_click: Callable,
    on_cancel: Optional[Callable] = None
):
    """创建单个任务卡片"""
    task_id = task_data.get("task_id", "unknown")
    status = task_data.get("status", "unknown")
    instruction = task_data.get("instruction", "")
    progress = task_data.get("progress", 0)
    created_at = task_data.get("created_at", "")

    status_config = {
        "received": {"icon": "📥", "color": "blue"},
        "running": {"icon": "🔄", "color": "orange"},
        "completed": {"icon": "✅", "color": "green"},
        "failed": {"icon": "❌", "color": "red"},
        "cancelled": {"icon": "⏹️", "color": "gray"},
        "timeout": {"icon": "⏰", "color": "orange"},
    }
    config = status_config.get(status, {"icon": "❓", "color": "gray"})

    with ui.card().classes("w-full cursor-pointer hover:shadow-lg transition-shadow") as card:
        card.on("click", lambda: on_click(task_id))

        with ui.row().classes("w-full justify-between items-center"):
            with ui.row().classes("items-center gap-2"):
                ui.label(config["icon"]).classes("text-xl")
                ui.label(task_id).classes("font-mono text-sm")
                ui.badge(status, color=config["color"]).classes("text-xs")

            if on_cancel and status in ["received", "running"]:
                ui.button(
                    "取消",
                    on_click=lambda e: (e.stop_propagation(), on_cancel(task_id)),
                    color="red"
                ).props("flat dense size=sm")

        ui.label(instruction[:50] + ("..." if len(instruction) > 50 else "")).classes("text-sm text-gray-600")

        with ui.row().classes("w-full items-center gap-2"):
            ui.linear_progress(value=progress / 100, show_value=False).classes("w-full")
            ui.label(f"{progress}%").classes("text-xs text-gray-500")

        ui.label(f"创建: {created_at[:16] if created_at else '未知'}").classes("text-xs text-gray-400")


def create_task_list(
    tasks: List[Dict[str, Any]],
    on_task_click: Callable,
    on_task_cancel: Optional[Callable] = None,
    empty_message: str = "暂无任务"
):
    """创建任务列表"""
    with ui.column().classes("w-full gap-2"):
        if not tasks:
            ui.label(empty_message).classes("text-gray-400 text-center w-full py-8")
            return

        for task in tasks:
            create_task_card(task, on_task_click, on_task_cancel)