"""Gradio UI - 多 Agent 系统启动入口"""

import asyncio
import threading
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

import gradio as gr
from conductor.agent import get_conductor
from conductor.core.message_bus import get_message_bus
from conductor.core.file_transfer import get_file_transfer
from creator.agent import get_creator


# 全局 Agent 实例
conductor = None
creator = None
sub_agents = {}
agent_loop = None


def get_or_create_event_loop():
    """获取或创建事件循环"""
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def init_agents(enable_creator: bool = True):
    """初始化所有 Agent"""
    global conductor, creator, sub_agents
    
    # 重置共享文件夹
    get_file_transfer().reset()
    
    # 初始化主 Agent
    conductor = get_conductor()
    
    # 初始化子 Agent
    if enable_creator:
        creator = get_creator()
        sub_agents["creator"] = creator
        
        # 订阅消息总线
        bus = get_message_bus()
        bus.subscribe("creator", creator.on_message)
        
        # 通知主 Agent 子 Agent 已启动
        conductor._active_sub_agents["creator"] = {
            "status": "active",
            "display_name": "✨ Creator"
        }
    
    return conductor, sub_agents


def run_async(coro):
    """同步运行异步函数"""
    loop = get_or_create_event_loop()
    return loop.run_until_complete(coro)


def chat_with_conductor(message, history):
    """与 Conductor 对话"""
    if not message:
        return ""
    
    result = run_async(conductor.chat(message))
    return result


def get_agent_status():
    """获取所有 Agent 状态"""
    if not conductor:
        return "❌ 系统未初始化"
    
    status = conductor.get_sub_agents_status()
    lines = ["## 🤖 Agent 状态\n"]
    
    # Conductor 自身
    lines.append(f"### 🎵 Conductor (主控)")
    lines.append(f"- 状态: ✅ 运行中")
    lines.append(f"- 已注册工具: {len(conductor.tools.list_tools())}")
    lines.append("")
    
    # 子 Agent
    lines.append(f"### 📦 子 Agent")
    for name, info in status.items():
        lines.append(f"- **{info.get('display_name', name)}**")
        lines.append(f"  - 状态: ✅ {info.get('status', 'active')}")
    
    if not status:
        lines.append("- 暂无已启动的子 Agent")
    
    return "\n".join(lines)


def get_memory_stats():
    """获取记忆统计"""
    if not conductor:
        return "❌ 系统未初始化"
    
    stats = conductor.memory.get_stats()
    
    lines = ["## 🧠 记忆系统统计\n"]
    lines.append(f"### 短期记忆")
    lines.append(f"- 消息条数: {stats['short_term_count']}")
    lines.append(f"- 已生成摘要: {'是' if stats['short_term_has_summary'] else '否'}")
    lines.append("")
    
    lines.append(f"### 长期记忆")
    lines.append(f"- 总条数: {stats['long_term']['total']}")
    lines.append(f"- 分类统计:")
    for cat, count in stats['long_term']['by_category'].items():
        lines.append(f"  - {cat}: {count}")
    
    return "\n".join(lines)


def view_long_term_memory(limit=20):
    """查看长期记忆"""
    if not conductor:
        return "❌ 系统未初始化"
    
    memories = conductor.memory.get_long_term_all(limit)
    
    if not memories:
        return "📭 暂无长期记忆"
    
    lines = ["## 📋 长期记忆列表\n"]
    for mem in memories:
        lines.append(f"**ID: {mem['id']}**")
        lines.append(f"- 分类: {mem['category']}")
        lines.append(f"- 重要性: {mem['importance']}")
        lines.append(f"- 内容: {mem['content'][:200]}")
        lines.append(f"- 时间: {mem['created_at']}")
        lines.append("")
    
    return "\n".join(lines)


def clear_long_term_memory():
    """清空长期记忆"""
    if not conductor:
        return "❌ 系统未初始化"
    
    count = conductor.memory.clear_long_term()
    return f"🗑️ 已清空 {count} 条长期记忆"


# 创建 Gradio 界面
with gr.Blocks(title="SOLAR_MA - 多 Agent 系统", theme=gr.themes.Soft()) as demo:
    gr.Markdown("# 🎵 SOLAR_MA 多 Agent 协作系统")
    gr.Markdown("Conductor 主控 Agent 与 Creator 子 Agent 已启动")
    
    with gr.Tabs():
        # 对话标签页
        with gr.TabItem("💬 对话"):
            chatbot = gr.Chatbot(label="Conductor", height=500)
            msg = gr.Textbox(label="输入消息", placeholder="说点什么...", lines=2)
            clear_btn = gr.Button("清空对话")
            
            def respond(message, chat_history):
                response = chat_with_conductor(message, chat_history)
                chat_history.append((message, response))
                return "", chat_history
            
            msg.submit(respond, [msg, chatbot], [msg, chatbot])
            clear_btn.click(lambda: [], None, chatbot)
        
        # 状态标签页
        with gr.TabItem("📊 Agent 状态"):
            status_refresh_btn = gr.Button("刷新状态")
            status_output = gr.Markdown(get_agent_status())
            status_refresh_btn.click(lambda: get_agent_status(), None, status_output)
        
        # 记忆标签页
        with gr.TabItem("🧠 记忆管理"):
            gr.Markdown("### 长期记忆管理")
            
            with gr.Row():
                view_memory_btn = gr.Button("查看长期记忆")
                memory_limit = gr.Slider(5, 50, value=20, step=5, label="显示条数")
                clear_memory_btn = gr.Button("清空长期记忆", variant="stop")
            
            memory_output = gr.Markdown("点击按钮查看")
            stats_output = gr.Markdown(get_memory_stats())
            
            view_memory_btn.click(
                lambda l: view_long_term_memory(l), 
                [memory_limit], 
                [memory_output]
            )
            clear_memory_btn.click(
                clear_long_term_memory, 
                None, 
                [memory_output, stats_output]
            )
            
            gr.Markdown("### 记忆统计")
            stats_refresh = gr.Button("刷新统计")
            stats_refresh.click(lambda: get_memory_stats(), None, stats_output)
    
    # 初始化 Agent
    init_agents(enable_creator=True)


def main():
    """启动 UI"""
    print("=" * 50)
    print("🎵 SOLAR_MA 多 Agent 系统启动")
    print("=" * 50)
    print("📡 消息总线已初始化")
    print("🗂️ 文件通道已重置")
    print("🧠 记忆系统已就绪")
    print("=" * 50)
    
    demo.launch(server_name="127.0.0.1", server_port=7860, share=False)


if __name__ == "__main__":
    main()