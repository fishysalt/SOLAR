"""Engineer NiceGUI UI - 独立调试界面"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from nicegui import ui
import asyncio
from typing import Optional, Dict, Any, List

from engineer.agent import get_engineer
from engineer.ui.components.task_list import create_task_list
from engineer.ui.components.task_detail import create_task_detail
from engineer.ui.components.memory_view import render_memory_view


# ========== 获取Engineer实例 ==========

engineer = get_engineer()
REFRESH_INTERVAL = 3


# ========== 状态管理 ==========

class UIState:
    def __init__(self):
        self.current_page: str = "chat"  # chat | memory
        self.current_task_id: Optional[str] = None
        self.current_view: str = "chat"
        self.tasks: List[Dict[str, Any]] = []
        self.messages: List[Dict[str, str]] = []
        self.is_loading: bool = False
        self.error: Optional[str] = None
        self._notified_completed: set = set()
        self._notified_failed: set = set()

    def set_task_detail(self, task_id: str):
        self.current_task_id = task_id
        self.current_view = "detail"

    def go_back(self):
        self.current_view = "chat"
        self.current_task_id = None

    def switch_page(self, page: str):
        self.current_page = page
        self.current_view = "chat"
        self.current_task_id = None

state = UIState()


# ========== 过程消息回调 ==========

def on_process_message(content: str, emoji: str = "🔧"):
    """接收过程消息并添加到UI"""
    state.messages.append({"role": "process", "content": f"─── {emoji} {content} ───"})
    refresh_main_content()

engineer.set_process_callback(on_process_message)


# ========== 核心操作 ==========

def send_message(message: str) -> Optional[str]:
    """发送任务到Engineer（同步调用，与Conductor UI一致）"""
    if not message.strip() or state.is_loading:
        return None

    state.is_loading = True
    state.error = None

    try:
        # ========== 调用同步方法 submit_task ==========
        task_id = engineer.submit_task("debug", message)
        state.messages.append({"role": "user", "content": message})
        state.messages.append({
            "role": "assistant",
            "content": f"✅ 任务已创建: {task_id}\n\n⏳ 正在后台处理，请查看侧边栏任务状态..."
        })
        return task_id
    except Exception as e:
        error_msg = f"❌ 发送失败: {str(e)}"
        state.error = error_msg
        state.messages.append({"role": "user", "content": message})
        state.messages.append({"role": "assistant", "content": error_msg})
        ui.notify(error_msg, type="negative")
        return None
    finally:
        state.is_loading = False


def fetch_tasks() -> List[Dict[str, Any]]:
    """获取任务列表"""
    try:
        tasks = []
        with engineer._task_lock:
            for task in engineer._tasks.values():
                tasks.append(task.to_dict())
        return tasks
    except Exception as e:
        print(f"获取任务列表失败: {e}")
        return []


def fetch_task_detail(task_id: str) -> Optional[Dict[str, Any]]:
    """获取任务详情"""
    try:
        task = engineer._get_task(task_id)
        if task:
            return task.to_dict()
        return {"error": f"任务 {task_id} 不存在"}
    except Exception as e:
        return {"error": str(e)}


def cancel_task(task_id: str) -> bool:
    """取消任务"""
    try:
        success = engineer.cancel_task(task_id)
        if success:
            ui.notify(f"✅ 任务 {task_id} 已取消", type="positive")
            return True
        else:
            ui.notify("取消失败", type="negative")
            return False
    except Exception as e:
        ui.notify(f"❌ 取消失败: {e}", type="negative")
        return False


def fetch_long_term_memories(limit: int = 50) -> List[Dict]:
    try:
        return engineer.memory.get_long_term_all(limit)
    except Exception as e:
        print(f"获取长期记忆失败: {e}")
        return []


def delete_memory(memory_id: int) -> bool:
    try:
        return engineer.delete_memory(memory_id)
    except Exception as e:
        print(f"删除记忆失败: {e}")
        return False


def fetch_rag_documents() -> List[Dict]:
    try:
        return engineer.get_all_knowledge_documents()
    except Exception as e:
        print(f"获取RAG文档失败: {e}")
        return []


def delete_rag_document(filename: str) -> bool:
    try:
        return engineer.delete_knowledge_document(filename)
    except Exception as e:
        print(f"删除RAG文档失败: {e}")
        return False


# ========== 全局容器 ==========

task_list_container = None
main_container = None


def refresh_tasks():
    """刷新任务列表"""
    try:
        state.tasks = fetch_tasks()
        if task_list_container:
            task_list_container.clear()
            with task_list_container:
                create_task_list(
                    tasks=state.tasks,
                    on_task_click=show_task_detail,
                    on_task_cancel=cancel_task,
                    empty_message="暂无任务，发送消息开始吧"
                )

        for t in state.tasks:
            task_id = t.get("task_id")
            status = t.get("status")
            if status == "completed" and task_id not in state._notified_completed:
                state._notified_completed.add(task_id)
                ui.notify(f"✅ 任务 {task_id} 已完成", type="positive", position="top-right")
            elif status == "failed" and task_id not in state._notified_failed:
                state._notified_failed.add(task_id)
                error = t.get("error", "未知错误")
                ui.notify(f"❌ 任务 {task_id} 失败: {error[:50]}", type="negative", position="top-right")
            elif status in ["running", "waiting"]:
                state._notified_completed.discard(task_id)
                state._notified_failed.discard(task_id)
    except Exception as e:
        print(f"刷新任务列表异常: {e}")


def show_task_detail(task_id: str):
    state.set_task_detail(task_id)
    refresh_main_content()


def refresh_main_content():
    if main_container:
        main_container.clear()
        with main_container:
            if state.current_page == "chat":
                render_chat_page()
            elif state.current_page == "memory":
                render_memory_page()
            else:
                render_chat_page()


# ========== 页面渲染 ==========

def render_chat_page():
    """渲染对话页面"""
    if state.current_view == "detail" and state.current_task_id:
        task_data = fetch_task_detail(state.current_task_id)
        if task_data and "error" not in task_data:
            create_task_detail(
                task_data=task_data,
                on_back=state.go_back,
                on_cancel=cancel_task
            )
        else:
            ui.label("任务不存在或已被删除").classes("text-gray-500 text-center w-full py-8")
            ui.button("返回", on_click=state.go_back).props("flat size=sm")
        return

    create_chat_interface()


def create_chat_interface():
    """创建聊天界面"""
    with ui.column().classes("w-full h-full gap-0 justify-between"):
        with ui.scroll_area().classes("w-full flex-1") as scroll:
            with ui.column().classes("w-full gap-2 p-4"):
                if not state.messages:
                    ui.label("👋 你好！我是 Engineer Agent，有什么可以帮你的？").classes(
                        "text-gray-400 text-center w-full py-8"
                    )
                for msg in state.messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if role == "user":
                        ui.chat_message(text=content, sent=True)
                    elif role == "process":
                        ui.label(content).classes("text-xs text-gray-400 font-mono w-full text-center py-0.5")
                    else:
                        ui.chat_message(text=content, sent=False)

        with ui.row().classes("w-full items-end gap-2 p-2 border-t border-gray-200 bg-white"):
            input_field = ui.input(placeholder="输入任务...").classes("flex-1")

            async def do_send_message():
                if state.is_loading:
                    return
                msg = input_field.value
                if not msg:
                    return
                input_field.value = ""
                input_field.props('disable')
                send_btn.disable()

                try:
                    task_id = send_message(msg)  # ← 同步调用
                    if task_id:
                        refresh_tasks()
                        await asyncio.sleep(0.5)
                        refresh_main_content()
                        scroll.scroll_to(percent=100)
                finally:
                    input_field.props('enable')
                    send_btn.enable()

            input_field.on('keydown.enter', do_send_message)
            send_btn = ui.button("发送", on_click=do_send_message, color="primary")

            def update_ui_state():
                if state.is_loading:
                    input_field.props('disable')
                    send_btn.disable()
                    input_field.props("placeholder='⏳ 处理中...'")
                else:
                    input_field.props('enable')
                    send_btn.enable()
                    input_field.props("placeholder='输入任务...'")

            ui.timer(0.5, update_ui_state)


def render_memory_page():
    """渲染记忆管理页面"""
    render_memory_view(
        memory=engineer.memory,
        fetch_long_term=fetch_long_term_memories,
        delete_memory_fn=delete_memory,
        fetch_rag=fetch_rag_documents,
        delete_rag_fn=delete_rag_document,
        on_back=lambda: (state.switch_page("chat"), refresh_main_content())
    )


# ========== 主页面 ==========

@ui.page("/")
def main_page():
    global task_list_container, main_container

    # 动态背景（复用conductor的backgrounds，如果没有就忽略）
    bg_path = Path(__file__).parent.parent.parent / "conductor" / "backgrounds" / "background.gif"
    if bg_path.exists():
        ui.add_body_html(f"""
        <style>
            body {{
                background-image: url('file:///{bg_path}');
                background-size: cover;
                background-position: center;
                background-attachment: fixed;
            }}
            .nicegui-content {{
                background: rgba(255, 255, 255, 0.92);
                border-radius: 16px;
                margin: 20px;
                padding: 20px;
                min-height: calc(100vh - 40px);
                backdrop-filter: blur(8px);
            }}
        </style>
        """)

    with ui.column().classes("nicegui-content w-full"):
        # 标题栏（无头像）
        with ui.row().classes("w-full justify-between items-center p-2 border-b border-gray-200"):
            with ui.row().classes("items-center gap-4"):
                ui.label("🔧 SOLAR_MA Engineer").classes("text-2xl font-bold")
                ui.label("v2.0").classes("text-sm text-gray-400")

            with ui.row().classes("items-center gap-2"):
                ui.button("🔄", on_click=refresh_tasks).props("flat dense size=sm")

        # 页面切换按钮
        with ui.row().classes("w-full gap-2 p-2 border-b border-gray-200 bg-gray-50/50"):
            page_config = [
                {"id": "chat", "icon": "💬", "label": "对话"},
                {"id": "memory", "icon": "📝", "label": "记忆"},
            ]
            current_page = state.current_page
            for p in page_config:
                is_active = p["id"] == current_page
                btn = ui.button(
                    f"{p['icon']} {p['label']}",
                    on_click=lambda pid=p["id"]: (state.switch_page(pid), refresh_main_content()),
                    color="primary" if is_active else "grey",
                ).props("size=sm")
                if not is_active:
                    btn.props("flat")

        # 主体
        with ui.row().classes("w-full gap-4 mt-4 h-[calc(100vh-220px)]"):
            # 左侧：任务列表
            with ui.column().classes("w-80 h-full border-r border-gray-200 pr-4"):
                ui.label("📋 任务列表").classes("font-bold text-lg")
                task_list_container = ui.column().classes("w-full flex-1 overflow-y-auto gap-2")
                state.tasks = fetch_tasks()
                with task_list_container:
                    create_task_list(
                        tasks=state.tasks,
                        on_task_click=show_task_detail,
                        on_task_cancel=cancel_task,
                        empty_message="暂无任务，发送消息开始吧"
                    )

            # 右侧：主内容
            with ui.column().classes("flex-1 h-full overflow-hidden"):
                main_container = ui.column().classes("w-full h-full overflow-y-auto")
                refresh_main_content()

        # 状态栏
        with ui.row().classes("w-full justify-between items-center p-2 border-t border-gray-200 text-xs text-gray-400"):
            ui.label(f"任务数: {len(state.tasks)}")
            ui.label(f"页面: {state.current_page}")
            if state.is_loading:
                ui.label("⏳ 处理中...").classes("text-orange-500")
            elif state.error:
                ui.label(f"❌ {state.error[:30]}").classes("text-red-500")
            else:
                ui.label("🟢 就绪").classes("text-green-500")
            ui.label("Engineer v2.0 | NiceGUI")

    ui.timer(REFRESH_INTERVAL, refresh_tasks)


# ========== 启动 ==========

if __name__ in {"__main__", "__mp_main__"}:
    print("=" * 50)
    print("🔧 SOLAR_MA Engineer UI (NiceGUI)")
    print("=" * 50)
    print("🖥️  UI 地址: http://localhost:7863")
    print("=" * 50)

    ui.run(
        host="0.0.0.0",
        port=7863,
        title="SOLAR_MA Engineer",
        favicon="🔧",
        dark=False,
        show=False
    )