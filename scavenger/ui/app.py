"""scavenger NiceGUI UI - 整合 API（同进程，共享 scavenger 实例）"""

import os
import sys
import threading
import uvicorn
import time
import socket
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from nicegui import ui
import asyncio
from typing import Optional, Dict, Any, List

# 直接导入scavenger
from scavenger.agent import get_scavenger

# 导入组件（复用 conductor 的 avatar 组件）
from conductor.ui.components.avatar import get_avatar_html, DEFAULT_EMOTION, EMOTION_MAPPING
from scavenger.ui.components.task_list import create_task_list
from scavenger.ui.components.task_detail import create_task_detail
from scavenger.ui.components.memory_view import render_memory_view


# ========== 获取scavenger实例 ==========

scavenger = get_scavenger()
USER_ID = "末"
REFRESH_INTERVAL = 3

import logging
logging.getLogger("nicegui").setLevel(logging.ERROR)
class IgnoreNiceGUIErrorFilter(logging.Filter):
    """过滤掉特定的 NiceGUI 错误信息"""
    def filter(self, record):
        msg = record.getMessage()
        # 忽略包含特定错误文本的日志
        if "The parent slot of the element has been deleted." in msg:
            return False
        # 可以继续添加更多需要忽略的文本
        return True

# 将过滤器应用到 root logger，这样所有 logger 都会生效
logging.getLogger().addFilter(IgnoreNiceGUIErrorFilter())
# ========== 注入 scavenger 实例到 API 模块 ==========
import scavenger.api as api_module
api_module._scavenger = scavenger  # 直接注入，避免重复初始化


# ========== 状态管理 ==========

class UIState:
    def __init__(self):
        # 页面状态
        self.current_page: str = "chat"  # chat | memory
        self.current_task_id: Optional[str] = None
        self.current_view: str = "chat"
        
        # 数据
        self.tasks: List[Dict[str, Any]] = []
        self.messages: List[Dict[str, str]] = []
        self.emotion: str = DEFAULT_EMOTION
        self.is_loading: bool = False
        self.error: Optional[str] = None
        
        # 通知去重
        self._notified_completed: set = set()
        self._notified_failed: set = set()

    def set_task_detail(self, task_id: str):
        self.current_task_id = task_id
        self.current_view = "detail"

    def go_back(self):
        self.current_view = "chat"
        self.current_task_id = None
    
    def switch_page(self, page: str):
        """切换页面"""
        self.current_page = page
        self.current_view = "chat"
        self.current_task_id = None

state = UIState()


# ========== scavenger 回调注册 ==========

def on_process_message(content: str, emoji: str = "🤔"):
    """接收过程消息并添加到UI"""
    state.messages.append({"role": "process", "content": f"─── {emoji} {content} ───"})
    refresh_main_content()

scavenger.set_process_callback(on_process_message)


# ========== 直接调用scavenger ==========

def send_message(message: str) -> Optional[str]:
    """发送消息到scavenger（直接调用）"""
    if not message.strip() or state.is_loading:
        return None

    state.is_loading = True
    state.error = None

    try:
        task_id = scavenger.submit_task(USER_ID, message)
        state.messages.append({"role": "user", "content": message})
        state.messages.append({
            "role": "assistant",
            "content": f"✅ 任务已创建: {task_id}\n\n⏳ 正在后台处理，请查看侧边栏任务状态..."
        })
        state.emotion = "working"
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
        tasks = scavenger.get_all_tasks()
        return [t.to_dict() for t in tasks]
    except Exception as e:
        print(f"获取任务列表失败: {e}")
        return []


def fetch_task_detail(task_id: str) -> Optional[Dict[str, Any]]:
    """获取任务详情"""
    try:
        return scavenger.get_task_summary(task_id)
    except Exception as e:
        print(f"获取任务详情失败: {e}")
        return {"error": str(e)}


def cancel_task(task_id: str) -> bool:
    """取消任务"""
    try:
        success = scavenger.cancel_task(task_id)
        if success:
            ui.notify(f"✅ 任务 {task_id} 已取消", type="positive")
            return True
        else:
            ui.notify("取消失败", type="negative")
            return False
    except Exception as e:
        ui.notify(f"❌ 取消失败: {e}", type="negative")
        return False


# ========== 记忆操作 ==========

def fetch_long_term_memories(limit: int = 50) -> List[Dict]:
    try:
        return scavenger.memory.get_long_term_all(limit)
    except Exception as e:
        print(f"获取长期记忆失败: {e}")
        return []


def delete_memory(memory_id: int) -> bool:
    try:
        return scavenger.delete_memory(memory_id)
    except Exception as e:
        print(f"删除记忆失败: {e}")
        return False


def fetch_rag_documents() -> List[Dict]:
    try:
        return scavenger.knowledge_base.get_all_documents()
    except Exception as e:
        print(f"获取RAG文档失败: {e}")
        return []


def delete_rag_document(filename: str) -> bool:
    try:
        return scavenger.knowledge_base.delete_document(filename)
    except Exception as e:
        print(f"删除RAG文档失败: {e}")
        return False


# ========== 全局容器 ==========

task_list_container = None
main_container = None
_refresh_lock = False


def refresh_tasks():
    """刷新任务列表 - 防重入"""
    global _refresh_lock
    
    if _refresh_lock:
        return
    
    _refresh_lock = True
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

        # 通知去重
        for t in state.tasks:
            task_id = t.get("task_id")
            status = t.get("status")
            
            if status == "completed":
                if task_id not in state._notified_completed:
                    state._notified_completed.add(task_id)
                    ui.notify(f"✅ 任务 {task_id} 已完成", type="positive", position="top-right")
            elif status == "failed":
                if task_id not in state._notified_failed:
                    state._notified_failed.add(task_id)
                    error = t.get("error", "未知错误")
                    ui.notify(f"❌ 任务 {task_id} 失败: {error[:50]}", type="negative", position="top-right")
            elif status in ["running", "waiting"]:
                if task_id in state._notified_completed:
                    state._notified_completed.discard(task_id)
                if task_id in state._notified_failed:
                    state._notified_failed.discard(task_id)
                    
    except Exception as e:
        print(f"刷新任务列表异常: {e}")
    finally:
        _refresh_lock = False


def show_task_detail(task_id: str):
    state.set_task_detail(task_id)
    refresh_main_content()


def refresh_main_content():
    """刷新主内容区"""
    if main_container:
        main_container.clear()
        with main_container:
            if state.current_page == "chat":
                render_chat_page()
            elif state.current_page == "memory":
                render_memory_page()
            else:
                render_chat_page()


# ========== 页面渲染函数 ==========

def render_chat_page():
    """渲染对话页面"""
    # 如果正在查看任务详情，显示详情
    if state.current_view == "detail" and state.current_task_id:
        task_data = fetch_task_detail(state.current_task_id)
        
        if task_data is None:
            ui.label("任务数据为空").classes("text-gray-500 text-center w-full py-8")
            ui.button("返回", on_click=state.go_back).props("flat size=sm")
        elif "error" in task_data and task_data["error"] is not None:
            ui.label(f"任务不存在或已被删除: {task_data.get('error', '')}").classes("text-gray-500 text-center w-full py-8")
            ui.button("返回", on_click=state.go_back).props("flat size=sm")
        elif "task_id" not in task_data:
            ui.label("任务数据格式错误").classes("text-gray-500 text-center w-full py-8")
            ui.button("返回", on_click=state.go_back).props("flat size=sm")
        else:
            create_task_detail(
                task_data=task_data,
                on_back=state.go_back,
                on_cancel=cancel_task
            )
        return
    
    # 否则显示聊天界面
    create_chat_interface()


def create_chat_interface():
    """创建聊天界面 - 输入框固定在底部"""
    with ui.column().classes("w-full h-full gap-0 justify-between"):
        # 消息列表
        with ui.scroll_area().classes("w-full flex-1") as scroll:
            with ui.column().classes("w-full gap-2 p-4"):
                if not state.messages:
                    ui.label("👋 你好！我是 scavenger Agent，有什么可以帮你的？").classes(
                        "text-gray-400 text-center w-full py-8"
                    )
                for msg in state.messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    
                    if role == "user":
                        ui.chat_message(text=content, sent=True)
                    elif role == "process":
                        ui.label(content).classes(
                            "text-xs text-gray-400 font-mono w-full text-center py-0.5"
                        )
                    else:
                        ui.chat_message(
                            text=content,
                            sent=False,
                            avatar=get_avatar_html(state.emotion, 40)
                        )
        
        # 输入框固定底部
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
                    task_id = send_message(msg)
                    if task_id:
                        await asyncio.sleep(0.1)
                        refresh_tasks()
                        await asyncio.sleep(0.3)
                        refresh_main_content()
                        try:
                            scroll.scroll_to(percent=100)
                        except (RuntimeError, AttributeError):
                            pass
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
        memory=scavenger.memory,
        knowledge_base=scavenger.knowledge_base,
        fetch_long_term=fetch_long_term_memories,
        delete_memory_fn=delete_memory,
        fetch_rag=fetch_rag_documents,
        delete_rag_fn=delete_rag_document,
        on_back=lambda: (state.switch_page("chat"), refresh_main_content())
    )


# ========== 检查端口是否被占用 ==========

def is_port_in_use(port: int) -> bool:
    """检查端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('0.0.0.0', port))
            return False
        except OSError:
            return True


# ========== 启动 FastAPI（同进程） ==========

def start_api():
    """在后台线程启动 FastAPI（使用注入的 scavenger 实例）"""
    # 检查端口是否被占用
    if is_port_in_use(7861):
        print(f"⚠️ 端口 7861 已被占用，跳过 API 启动")
        return
    
    import uvicorn
    from scavenger.api import app
    
    # 确保 API 使用注入的 scavenger 实例
    # 注意：已经在模块顶部注入了 scavenger
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=7861,
        log_level="warning",
        reload=False  # 禁用 reload，避免重复加载
    )


# ========== 主页面 ==========

@ui.page("/")
def main_page():
    global task_list_container, main_container

    # 动态背景（复用conductor的backgrounds）
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
        # ===== 标题栏 =====
        with ui.row().classes("w-full justify-between items-center p-2 border-b border-gray-200"):
            with ui.row().classes("items-center gap-4"):
                ui.html(get_avatar_html(state.emotion, 50))
                ui.label("✨ SOLAR_MA scavenger").classes("text-2xl font-bold")
                ui.label("v2.0").classes("text-sm text-gray-400")

            with ui.row().classes("items-center gap-2"):
                ui.label(f"用户: {USER_ID}").classes("text-sm text-gray-500")
                ui.button("🔄", on_click=refresh_tasks).props("flat dense size=sm")

        # ===== 页面切换顶部按钮 =====
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
                )
                btn.props("size=sm")
                if not is_active:
                    btn.props("flat")

        # ===== 主体：侧边栏 + 主内容 =====
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

        # ===== 状态栏 =====
        with ui.row().classes("w-full justify-between items-center p-2 border-t border-gray-200 text-xs text-gray-400"):
            ui.label(f"任务数: {len(state.tasks)}")
            ui.label(f"页面: {state.current_page}")
            ui.label(f"情绪: {EMOTION_MAPPING.get(state.emotion, {}).get('name', '未知')}")
            if state.is_loading:
                ui.label("⏳ 处理中...").classes("text-orange-500")
            elif state.error:
                ui.label(f"❌ {state.error[:30]}").classes("text-red-500")
            else:
                ui.label("🟢 就绪").classes("text-green-500")
            ui.label("scavenger v2.0 | NiceGUI")

    # ===== 定时刷新 =====
    ui.timer(REFRESH_INTERVAL, refresh_tasks)


# ========== 启动 ==========

if __name__ in {"__main__", "__mp_main__"}:
    print("=" * 50)
    print("✨ SOLAR_MA scavenger (API + UI 同进程)")
    print("=" * 50)
    print("📡 API: http://localhost:7861  (供 Conductor 调用)")
    print("🖥️  UI:  http://localhost:7961  (用户界面)")
    print("=" * 50)
    print("💡 按 Ctrl+C 停止")
    print("=" * 50)

    # ========== 在后台线程启动 FastAPI ==========
    api_thread = threading.Thread(target=start_api, daemon=True)
    api_thread.start()
    
    # 等待一下让 API 启动
    time.sleep(1)
    
    if not is_port_in_use(7861):
        print("✅ FastAPI 已在后台启动 (端口 7861)")
    else:
        print("⚠️ FastAPI 启动失败，端口 7861 已被占用")

    # ========== 启动 NiceGUI UI（主线程） ==========
    ui.run(
        host="0.0.0.0",
        port=7961,
        title="SOLAR_MA scavenger",
        favicon="✨",
        dark=False,
        show=False
    )