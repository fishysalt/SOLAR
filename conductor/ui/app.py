"""Conductor NiceGUI UI - 主应用"""

import os
import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from nicegui import ui
import asyncio
from typing import Optional, Dict, Any, List

# 直接导入Conductor
from conductor.agent import get_conductor

# 导入组件
from conductor.ui.components.avatar import get_avatar_html, DEFAULT_EMOTION, EMOTION_MAPPING
from conductor.ui.components.task_list import create_task_list
from conductor.ui.components.task_detail import create_task_detail


# ========== 获取Conductor实例 ==========
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

conductor = get_conductor()
USER_ID = "末"
REFRESH_INTERVAL = 3


# ========== 状态管理 ==========

class UIState:
    def __init__(self):
        # 页面状态
        self.current_page: str = "chat"  # chat | memory | control
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
        
        # 子Agent状态缓存
        self.agent_status: Dict[str, Any] = {}

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


# ========== Conductor 回调注册 ==========

def on_process_message(content: str, emoji: str = "🤔"):
    """接收过程消息并添加到UI"""
    state.messages.append({"role": "process", "content": f"─── {emoji} {content} ───"})
    refresh_main_content()

conductor.set_process_callback(on_process_message)


# ========== 直接调用Conductor ==========

def send_message(message: str) -> Optional[str]:
    """发送消息到Conductor（直接调用）"""
    if not message.strip() or state.is_loading:
        return None

    state.is_loading = True
    state.error = None

    try:
        task_id = conductor.submit_task(USER_ID, message)
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
    """获取用户任务列表"""
    try:
        tasks = conductor.get_user_tasks(USER_ID)
        return [t.to_dict() for t in tasks]
    except Exception as e:
        print(f"获取任务列表失败: {e}")
        return []


def fetch_task_detail(task_id: str) -> Optional[Dict[str, Any]]:
    """获取任务详情"""
    try:
        return conductor.get_task_summary(task_id)
    except Exception as e:
        print(f"获取任务详情失败: {e}")
        return {"error": str(e)}


def cancel_task(task_id: str) -> bool:
    """取消任务"""
    try:
        import asyncio
        result = asyncio.run(conductor.cancel_task(task_id))
        if result:
            ui.notify(f"✅ 任务 {task_id} 已取消", type="positive")
            return True
        else:
            ui.notify("取消失败", type="negative")
            return False
    except Exception as e:
        ui.notify(f"❌ 取消失败: {e}", type="negative")
        return False


# ========== 新增：回复任务 ==========

def reply_to_task(task_id: str, user_input: str) -> str:
    """回复指定任务（从任务详情页调用）"""
    try:
        return conductor.reply_to_task(task_id, user_input)
    except Exception as e:
        return f"❌ 回复失败: {str(e)}"


# ========== 子Agent控制 ==========

def get_agent_status() -> Dict[str, Any]:
    """获取所有子Agent状态"""
    status = {}
    agent_names = ["creator", "scavenger", "engineer"]
    
    import requests
    for name in agent_names:
        config = conductor.registry._config.get(name)
        if not config:
            # 如果配置中没有，尝试从硬编码获取
            port_map = {"creator": 7861, "scavenger": 7862, "engineer": 7863}
            if name in port_map:
                api_url = f"http://localhost:{port_map[name]}"
                status[name] = {"status": "unknown", "api_url": api_url, "error": "未配置"}
            else:
                status[name] = {"status": "unknown", "api_url": "未知", "error": "未配置"}
            continue
        
        api_url = f"http://localhost:{config['api_port']}"
        try:
            resp = requests.get(f"{api_url}/api/health", timeout=2)
            if resp.status_code == 200:
                status[name] = {"status": "running", "api_url": api_url}
            else:
                status[name] = {"status": "error", "api_url": api_url, "code": resp.status_code}
        except requests.exceptions.ConnectionError:
            status[name] = {"status": "stopped", "api_url": api_url}
        except Exception as e:
            status[name] = {"status": "error", "api_url": api_url, "error": str(e)}
    
    return status


def start_agent(agent_name: str) -> bool:
    """启动子Agent"""
    from conductor.agent_launcher import get_agent_launcher
    launcher = get_agent_launcher()
    success = launcher.start_agent(agent_name)
    if success:
        ui.notify(f"✅ {agent_name} 启动成功", type="positive")
    else:
        ui.notify(f"❌ {agent_name} 启动失败", type="negative")
    return success


def stop_agent(agent_name: str) -> bool:
    """停止子Agent"""
    from conductor.agent_launcher import get_agent_launcher
    launcher = get_agent_launcher()
    success = launcher.stop_agent(agent_name)
    if success:
        ui.notify(f"🛑 {agent_name} 已停止", type="positive")
    else:
        ui.notify(f"❌ {agent_name} 停止失败", type="negative")
    return success


# ========== 记忆操作 ==========

def fetch_long_term_memories(limit: int = 50) -> List[Dict]:
    """获取长期记忆"""
    try:
        return conductor.memory.get_long_term_all(limit)
    except Exception as e:
        print(f"获取长期记忆失败: {e}")
        return []


def delete_memory(memory_id: int) -> bool:
    """删除长期记忆"""
    try:
        return conductor.memory.delete_long_term(memory_id)
    except Exception as e:
        print(f"删除记忆失败: {e}")
        return False


def fetch_rag_documents() -> List[Dict]:
    """获取RAG文档列表"""
    try:
        return conductor.memory.knowledge_base.get_all_documents()
    except Exception as e:
        print(f"获取RAG文档失败: {e}")
        return []


def delete_rag_document(filename: str) -> bool:
    """删除RAG文档"""
    try:
        return conductor.memory.knowledge_base.delete_document(filename)
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
            elif state.current_page == "control":
                render_control_page()
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
            # 渲染任务详情 + 回复输入框
            render_task_detail_with_reply(task_data)
        return
    
    # 否则显示聊天界面
    create_chat_interface()


def render_task_detail_with_reply(task_data: Dict[str, Any]):
    """渲染任务详情 + 回复输入框"""
    task_id = task_data.get("task_id")
    status = task_data.get("status")
    
    # 渲染任务详情（复用原有组件）
    create_task_detail(
        task_data=task_data,
        on_back=state.go_back,
        on_cancel=cancel_task
    )
    
    # ========== 任务回复输入框（仅当任务可回复时显示） ==========
    # 可回复状态：awaiting_confirmation（等待确认）和 running（运行中）
    if status in ["awaiting_confirmation", "running"]:
        ui.separator().classes("mt-4")
        
        status_label = "等待确认" if status == "awaiting_confirmation" else "执行中"
        ui.label(f"📝 回复当前任务 ({status_label})").classes("font-bold text-sm text-gray-600")
        
        with ui.row().classes("w-full items-end gap-2 mt-1"):
            reply_input = ui.input(
                placeholder="输入指令... (回复'确认'结束任务，或输入修改要求)",
                value=""
            ).classes("flex-1")
            
            async def do_reply():
                msg = reply_input.value
                if not msg:
                    return
                reply_input.value = ""
                reply_input.props('disable')
                reply_btn.disable()
                
                try:
                    result = reply_to_task(task_id, msg)
                    try:
                        ui.notify(result[:200], type="positive" if "✅" in result else "warning")
                    except RuntimeError:
                        pass  # 忽略元素已删除的错误
                    # 刷新任务列表和详情
                    refresh_tasks()
                    await asyncio.sleep(0.3)
                    # 重新获取任务详情并刷新
                    new_task_data = fetch_task_detail(task_id)
                    if new_task_data and "error" not in new_task_data:
                        # 清除主内容区，重新渲染
                        main_container.clear()
                        with main_container:
                            render_task_detail_with_reply(new_task_data)
                    else:
                        # 如果任务已完成或不存在，返回对话页
                        state.go_back()
                        refresh_main_content()
                finally:
                    reply_input.props('enable')
                    reply_btn.enable()
            
            reply_input.on('keydown.enter', do_reply)
            reply_btn = ui.button("发送", on_click=do_reply, color="primary")
            
            # 根据状态显示提示
            if status == "awaiting_confirmation":
                ui.label("💡 输入 '确认' 结束任务，或输入修改要求继续").classes("text-xs text-gray-400 mt-1")
            else:
                ui.label("💡 输入修改要求，任务将继续处理").classes("text-xs text-gray-400 mt-1")


def create_chat_interface():
    """创建聊天界面 - 输入框固定在底部"""
    with ui.column().classes("w-full h-full gap-0 justify-between"):
        # 消息列表
        with ui.scroll_area().classes("w-full flex-1") as scroll:
            with ui.column().classes("w-full gap-2 p-4"):
                if not state.messages:
                    ui.label("👋 你好！我是 Conductor，有什么可以帮你的？").classes(
                        "text-gray-400 text-center w-full py-8"
                    )
                for msg in state.messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    
                    if role == "user":
                        ui.chat_message(text=content, sent=True)
                    elif role == "process":
                        # 过程消息：灰色小字，居中
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
            input_field = ui.input(placeholder="输入消息...").classes("flex-1")
            
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
                        # 等待任务被存入 _tasks
                        await asyncio.sleep(0.1)
                        refresh_tasks()
                        await asyncio.sleep(0.3)
                        refresh_main_content()
                        # 安全滚动
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
                    input_field.props("placeholder='输入消息...'")
            
            ui.timer(0.5, update_ui_state)


def render_memory_page():
    """渲染记忆管理页面"""
    with ui.column().classes("w-full gap-4 p-4"):
        ui.label("📝 记忆管理").classes("text-2xl font-bold")
        
        # ===== 固定记忆 =====
        with ui.expansion("📌 固定记忆 (permanent.yaml)", icon="pin_drop").classes("w-full"):
            try:
                permanent = conductor.memory.permanent._data
                if permanent:
                    for key, value in permanent.items():
                        ui.label(f"**{key}**").classes("font-bold text-sm")
                        ui.label(str(value)[:500] + ("..." if len(str(value)) > 500 else "")).classes(
                            "text-sm text-gray-600 whitespace-pre-wrap"
                        )
                        ui.separator()
                else:
                    ui.label("固定记忆为空，请配置 conductor/memory/permanent.yaml").classes("text-gray-400")
            except Exception as e:
                ui.label(f"读取固定记忆失败: {e}").classes("text-red-500")
        
        # ===== 长期记忆 =====
        with ui.expansion("💾 长期记忆 (SQLite)", icon="storage").classes("w-full"):
            with ui.row().classes("w-full justify-between items-center"):
                ui.label("所有已保存的长期记忆").classes("text-sm text-gray-500")
                ui.button("刷新", on_click=lambda: render_memory_page()).props("flat size=sm")
            
            memories = fetch_long_term_memories(50)
            if not memories:
                ui.label("暂无长期记忆").classes("text-gray-400 py-4")
            else:
                # 分类筛选
                categories = list(set(m.get("category", "general") for m in memories))
                selected_category = ui.select(
                    categories + ["全部"],
                    value="全部",
                    label="分类筛选"
                ).classes("w-48")
                
                def filter_memories():
                    cat = selected_category.value
                    if cat == "全部":
                        return memories
                    return [m for m in memories if m.get("category", "general") == cat]
                
                # 记忆列表
                memory_container = ui.column().classes("w-full gap-2 mt-2")
                
                def refresh_memory_list():
                    memory_container.clear()
                    with memory_container:
                        filtered = filter_memories()
                        for m in filtered:
                            with ui.row().classes("w-full justify-between items-center border-b border-gray-100 py-2"):
                                with ui.column().classes("flex-1"):
                                    ui.label(m.get("content", "")[:200]).classes("text-sm")
                                    with ui.row().classes("gap-4 text-xs text-gray-400"):
                                        ui.label(f"ID: {m.get('id')}")
                                        ui.label(f"分类: {m.get('category', 'general')}")
                                        ui.label(f"重要性: {m.get('importance', 0.5)}")
                                        ui.label(f"创建: {m.get('created_at', '')[:16]}")
                                ui.button(
                                    "删除",
                                    on_click=lambda mid=m.get('id'): delete_memory_and_refresh(mid),
                                    color="red"
                                ).props("flat dense size=sm")
                
                selected_category.on("change", refresh_memory_list)
                refresh_memory_list()
                
                def delete_memory_and_refresh(memory_id):
                    if delete_memory(memory_id):
                        ui.notify(f"✅ 已删除记忆 ID: {memory_id}", type="positive")
                        refresh_memory_list()
                    else:
                        ui.notify("❌ 删除失败", type="negative")
        
        # ===== RAG知识库 =====
        with ui.expansion("📚 RAG 知识库", icon="book").classes("w-full"):
            with ui.row().classes("w-full justify-between items-center"):
                ui.label("知识文档列表").classes("text-sm text-gray-500")
                ui.button("刷新", on_click=lambda: render_memory_page()).props("flat size=sm")
            
            docs = fetch_rag_documents()
            if not docs:
                ui.label("暂无知识文档").classes("text-gray-400 py-4")
            else:
                for doc in docs:
                    with ui.row().classes("w-full justify-between items-center border-b border-gray-100 py-2"):
                        with ui.column().classes("flex-1"):
                            filename = doc.get("filename", doc.get("source", "未知"))
                            ui.label(filename).classes("text-sm font-mono")
                            preview = doc.get("content_preview", "")
                            if preview:
                                ui.label(preview[:100] + ("..." if len(preview) > 100 else "")).classes(
                                    "text-xs text-gray-400"
                                )
                            ui.label(f"创建: {doc.get('created_at', '未知')}").classes("text-xs text-gray-400")
                        ui.button(
                            "删除",
                            on_click=lambda f=filename: delete_rag_and_refresh(f),
                            color="red"
                        ).props("flat dense size=sm")
        
        ui.button("← 返回对话", on_click=lambda: (state.switch_page("chat"), refresh_main_content())).props("flat size=sm")


def delete_rag_and_refresh(filename: str):
    """删除RAG文档并刷新"""
    if delete_rag_document(filename):
        ui.notify(f"✅ 已删除文档: {filename}", type="positive")
        render_memory_page()
    else:
        ui.notify("❌ 删除失败", type="negative")


def render_control_page():
    """渲染子Agent控制页面"""
    with ui.column().classes("w-full gap-4 p-4"):
        ui.label("🤖 子Agent 控制").classes("text-2xl font-bold")
        ui.label("启动或停止子Agent服务").classes("text-sm text-gray-500")
        
        # 刷新状态
        def refresh_agent_status():
            state.agent_status = get_agent_status()
            render_control_page()
        
        # 初始加载状态
        if not state.agent_status:
            state.agent_status = get_agent_status()
        
        with ui.row().classes("w-full justify-end"):
            ui.button("🔄 刷新状态", on_click=refresh_agent_status).props("flat size=sm")
        
        # Agent列表
        agent_names = ["creator", "scavenger", "engineer"]
        agent_display = {
            "creator": {"icon": "✨", "label": "Creator", "desc": "内容生成"},
            "scavenger": {"icon": "🔍", "label": "Scavenger", "desc": "信息收集"},
            "engineer": {"icon": "🔧", "label": "Engineer", "desc": "自进化引擎"},
        }
        
        for name in agent_names:
            status = state.agent_status.get(name, {"status": "unknown", "api_url": "未知"})
            status_text = status.get("status", "unknown")
            api_url = status.get("api_url", "未知")
            display = agent_display.get(name, {"icon": "❓", "label": name, "desc": ""})
            
            # 状态配置
            status_config = {
                "running": {"icon": "🟢", "color": "green", "label": "运行中"},
                "stopped": {"icon": "⚫", "color": "gray", "label": "已停止"},
                "error": {"icon": "🔴", "color": "red", "label": "异常"},
                "unknown": {"icon": "❓", "color": "gray", "label": "未知"},
            }
            config = status_config.get(status_text, status_config["unknown"])
            
            with ui.card().classes("w-full"):
                with ui.row().classes("w-full justify-between items-center"):
                    with ui.row().classes("items-center gap-4"):
                        ui.label(display["icon"]).classes("text-2xl")
                        ui.label(display["label"]).classes("font-bold text-lg font-mono")
                        ui.badge(config["label"], color=config["color"])
                        ui.label(f"API: {api_url}").classes("text-xs text-gray-400")
                    
                    with ui.row().classes("gap-2"):
                        if status_text == "running":
                            ui.button(
                                "停止",
                                on_click=lambda n=name: (stop_agent(n), refresh_agent_status()),
                                color="red"
                            ).props("size=sm")
                        elif status_text in ["stopped", "unknown"]:
                            ui.button(
                                "启动",
                                on_click=lambda n=name: (start_agent(n), refresh_agent_status()),
                                color="green"
                            ).props("size=sm")
                        else:
                            ui.button(
                                "重启",
                                on_click=lambda n=name: (stop_agent(n), start_agent(n), refresh_agent_status()),
                                color="orange"
                            ).props("size=sm")
                
                # 描述
                ui.label(display["desc"]).classes("text-xs text-gray-400 mt-1")
                
                # 错误信息
                if status_text == "error":
                    error_msg = status.get("error") or status.get("code", "未知错误")
                    ui.label(f"⚠️ 错误: {error_msg}").classes("text-sm text-red-500 mt-2")
                elif status_text == "running":
                    # 显示运行的子Agent信息
                    try:
                        import requests
                        resp = requests.get(f"{api_url}/api/status", timeout=2)
                        if resp.status_code == 200:
                            data = resp.json()
                            caps = data.get("capabilities", [])
                            if caps:
                                ui.label(f"能力: {', '.join(caps)}").classes("text-xs text-gray-400 mt-1")
                    except:
                        pass
        
        # 提示信息
        with ui.card().classes("w-full bg-blue-50 border border-blue-200 mt-4"):
            ui.label("💡 提示").classes("font-bold text-sm text-blue-700")
            ui.label("启动子Agent后，Conductor才能调用它们执行任务。").classes("text-sm text-blue-600")
            ui.label("Engineer 是自进化引擎，建议始终开启。").classes("text-sm text-blue-600")
        
        ui.button("← 返回对话", on_click=lambda: (state.switch_page("chat"), refresh_main_content())).props("flat size=sm")


# ========== 主页面 ==========

@ui.page("/")
def main_page():
    global task_list_container, main_container

    # ========== 动态背景 ==========
    bg_path = Path(__file__).parent.parent / "backgrounds" / "background.gif"
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
                ui.label("🎵 SOLAR_MA Conductor").classes("text-2xl font-bold")
                ui.label("v2.0").classes("text-sm text-gray-400")

            with ui.row().classes("items-center gap-2"):
                ui.label(f"用户: {USER_ID}").classes("text-sm text-gray-500")
                ui.button("🔄", on_click=refresh_tasks).props("flat dense size=sm")

        # ===== 页面切换顶部按钮 =====
        with ui.row().classes("w-full gap-2 p-2 border-b border-gray-200 bg-gray-50/50"):
            page_config = [
                {"id": "chat", "icon": "💬", "label": "对话"},
                {"id": "memory", "icon": "📝", "label": "记忆"},
                {"id": "control", "icon": "🤖", "label": "控制"},
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

            # 显示情绪（如果有）
            emotion_name = EMOTION_MAPPING.get(state.emotion, {}).get('name', '未知')
            ui.label(f"情绪: {emotion_name}").classes("text-xs")

            if state.is_loading:
                ui.label("⏳ 处理中...").classes("text-orange-500")
            elif state.error:
                ui.label(f"❌ {state.error[:30]}").classes("text-red-500")
            else:
                ui.label("🟢 就绪").classes("text-green-500")
            ui.label("Conductor v2.0 | NiceGUI")

    # ===== 定时刷新 =====
    ui.timer(REFRESH_INTERVAL, refresh_tasks)


# ========== 启动 ==========

if __name__ in {"__main__", "__mp_main__"}:
    print("=" * 50)
    print("🎵 SOLAR_MA Conductor UI (NiceGUI)")
    print("=" * 50)
    print("🔄 直接调用 Conductor（同进程）")
    print("🖥️  UI 地址: http://localhost:7960")
    print("=" * 50)

    ui.run(
        host="0.0.0.0",
        port=7960,
        title="SOLAR_MA Conductor",
        favicon="🎵",
        dark=False,
        show=False
    )