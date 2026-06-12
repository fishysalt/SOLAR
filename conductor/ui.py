"""Conductor 主 UI - 管理所有 Agent"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import gradio as gr
import asyncio
from conductor.agent import get_conductor
from conductor.http_client import get_http_client
from conductor.agent_launcher import get_agent_launcher


conductor = None
http_client = None
launcher = None
_loop = None


def get_or_create_loop():
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop


def init():
    global conductor, http_client, launcher
    conductor = get_conductor()
    http_client = get_http_client()
    launcher = get_agent_launcher()
    print("✅ Conductor UI 初始化完成")


def run_async(coro):
    loop = get_or_create_loop()
    return loop.run_until_complete(coro)


def chat_with_conductor(message: str, history: list):
    if not message:
        return "", history
    
    async def _chat():
        return await conductor.chat(message)
    
    result = run_async(_chat())
    
    history = history or []
    history.append({
        "role": "user",
        "content": [{"type": "text", "text": message}]
    })
    history.append({
        "role": "assistant",
        "content": [{"type": "text", "text": result}]
    })
    
    return "", history


def start_agent(agent_name: str):
    success = launcher.start_agent(agent_name)
    if success:
        return f"✅ {agent_name} 启动成功"
    return f"❌ {agent_name} 启动失败"


def stop_agent(agent_name: str):
    success = launcher.stop_agent(agent_name)
    if success:
        return f"🛑 {agent_name} 已停止"
    return f"❌ {agent_name} 停止失败"


def get_all_agent_status():
    status = launcher.list_agents()
    
    lines = ["## 🤖 Agent 状态\n"]
    lines.append("| Agent | 状态 |")
    lines.append("|-------|------|")
    
    for name, state in status.items():
        status_icon = "🟢 运行中" if state == "running" else "⚫ 已停止"
        lines.append(f"| {name} | {status_icon} |")
    
    return "\n".join(lines)


def send_task_to_agent(agent_name: str, instruction: str):
    if not instruction:
        return "请输入任务描述"
    
    async def _send():
        return await http_client.send_task(agent_name, instruction)
    
    result = run_async(_send())
    
    if result.get("status") == "success":
        return f"✅ 任务完成\n\n{result.get('message', '')}"
    else:
        return f"❌ 任务失败\n\n{result.get('error', '未知错误')}"


with gr.Blocks(title="SOLAR_MA - 主控面板") as demo:
    gr.Markdown("# 🎵 SOLAR_MA 多 Agent 系统")
    
    init()
    
    with gr.Tabs():
        with gr.TabItem("💬 对话"):
            chatbot = gr.Chatbot(label="Conductor", height=500)
            msg = gr.Textbox(label="输入消息", lines=2)
            clear_btn = gr.Button("清空对话")
            
            msg.submit(chat_with_conductor, [msg, chatbot], [msg, chatbot])
            clear_btn.click(lambda: [], None, chatbot)
        
        with gr.TabItem("📦 Agent 管理"):
            status_output = gr.Markdown(get_all_agent_status())
            refresh_btn = gr.Button("刷新状态")
            refresh_btn.click(get_all_agent_status, None, status_output)
            
            gr.Markdown("### 启动/停止 Agent")
            
            with gr.Row():
                creator_start = gr.Button("启动 Creator", variant="primary")
                creator_stop = gr.Button("停止 Creator", variant="stop")
            
            creator_status = gr.Markdown("")
            creator_start.click(lambda: start_agent("creator"), None, creator_status)
            creator_stop.click(lambda: stop_agent("creator"), None, creator_status)
        
        with gr.TabItem("🎯 任务调度"):
            agent_select = gr.Dropdown(choices=["creator"], label="选择 Agent")
            task_input = gr.Textbox(label="任务描述", lines=3)
            submit_btn = gr.Button("提交任务")
            task_result = gr.Markdown("")
            
            submit_btn.click(send_task_to_agent, [agent_select, task_input], task_result)


def main():
    print("=" * 50)
    print("🎵 SOLAR_MA Conductor 主控启动")
    print("=" * 50)
    print("📡 主控 UI: http://localhost:7860")
    print("=" * 50)
    
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False
    )


if __name__ == "__main__":
    main()