"""启明星 -猫群里最大的那只猫"""

import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import gradio as gr
import asyncio
import re
import base64
from conductor.agent import get_conductor
from conductor.http_client import get_http_client
from conductor.agent_launcher import get_agent_launcher

# ========== 头像配置 ==========
PORTRAITS_DIR = Path(__file__).parent / "portraits"

EMOTION_MAPPING = {
    "motivated": {"name": "干劲十足", "file": "干劲十足.jpg", "desc": "充满干劲、积极"},
    "happy": {"name": "高兴", "file": "高兴.png", "desc": "开心、愉快"},
    "surprised": {"name": "惊讶", "file": "惊讶.png", "desc": "惊讶、意外"},
    "tired": {"name": "疲劳", "file": "疲劳.jpg", "desc": "疲劳、累了"},
    "success": {"name": "任务成功", "file": "任务成功.jpg", "desc": "任务成功、成就感"},
    "working": {"name": "任务进行", "file": "任务进行.jpg", "desc": "正在执行任务"},
    "failed": {"name": "任务失败", "file": "任务失败.webp", "desc": "任务失败"},
    "sad": {"name": "伤心", "file": "伤心.jpg", "desc": "伤心、失望"},
    "angry": {"name": "生气", "file": "生气.jpg", "desc": "生气、不满"},
    "sleeping": {"name": "睡大觉", "file": "睡大觉.jpg", "desc": "空闲、待机"},
    "praising": {"name": "赞赏", "file": "赞赏.jpg", "desc": "赞赏、表扬"},
}

DEFAULT_EMOTION = "motivated"

# 情绪标签列表（供 LLM 选择）
EMOTION_LIST = "\n".join([f"- `{tag}`：{info['desc']}" for tag, info in EMOTION_MAPPING.items()])


def get_avatar_base64(emotion_tag: str) -> str:
    """获取头像的 base64 编码"""
    if emotion_tag not in EMOTION_MAPPING:
        emotion_tag = DEFAULT_EMOTION
    
    filename = EMOTION_MAPPING[emotion_tag]["file"]
    img_path = PORTRAITS_DIR / filename
    
    if not img_path.exists():
        for f in PORTRAITS_DIR.iterdir():
            if f.is_file():
                img_path = f
                break
        else:
            return ""
    
    with open(img_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode()
    
    ext = img_path.suffix.lower()
    mime_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp"
    }.get(ext, "image/png")
    
    return f"data:{mime_type};base64,{img_data}"


def get_avatar_html(emotion_tag: str) -> str:
    """生成头像 HTML"""
    img_data = get_avatar_base64(emotion_tag)
    if not img_data:
        return ""
    
    return f"""
    <div style="text-align: center;">
        <img src="{img_data}" style="width: 100px; height: 100px; border-radius: 50%; object-fit: cover; border: 2px solid #ddd;">
        <div style="margin-top: 5px; font-size: 12px; color: #666;">{EMOTION_MAPPING.get(emotion_tag, {}).get('name', '')}</div>
    </div>
    """


def extract_emotion_and_reply(response: str) -> tuple:
    """从 LLM 响应中提取情绪标签和纯文本回复"""
    pattern = r'<emotion>(\w+)</emotion>'
    match = re.search(pattern, response)
    
    if match:
        emotion = match.group(1)
        reply = re.sub(pattern, '', response).strip()
    else:
        emotion = DEFAULT_EMOTION
        reply = response.strip()
    
    if emotion not in EMOTION_MAPPING:
        emotion = DEFAULT_EMOTION
    
    return reply, emotion


# ========== 原有 UI 逻辑 ==========

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
    """与 Conductor 对话，返回 (新消息, 历史, 情绪标签)"""
    if not message:
        return "", history, DEFAULT_EMOTION
    
    async def _chat():
        return await conductor.chat(message)
    
    result = run_async(_chat())
    reply, emotion = extract_emotion_and_reply(result)
    
    history = history or []
    history.append({
        "role": "user",
        "content": [{"type": "text", "text": message}]
    })
    history.append({
        "role": "assistant",
        "content": [{"type": "text", "text": reply}]
    })
    
    return "", history, emotion


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
    """获取所有 Agent 状态（同步 HTTP 检测）"""
    import requests
    from conductor.agent import get_conductor
    
    conductor = get_conductor()
    
    lines = ["## 🤖 Agent 状态\n"]
    lines.append("| Agent | 状态 | API 地址 | UI 地址 |")
    lines.append("|-------|------|----------|---------|")
    
    port_map = {"creator": 7961, "scavenger": 7962}
    
    for name, config in conductor.registry._config.items():
        api_port = config.get('api_port')
        api_url = f"http://localhost:{api_port}"
        
        try:
            resp = requests.get(f"{api_url}/api/health", timeout=3)
            if resp.status_code == 200:
                status_icon = "🟢 运行中"
                ui_url = f"http://localhost:{port_map.get(name, 7961)}"
                api_display = api_url
            else:
                status_icon = "🔴 异常"
                ui_url = "-"
                api_display = f"{api_url} (HTTP {resp.status_code})"
        except requests.exceptions.ConnectionError:
            status_icon = "⚫ 已停止"
            ui_url = "-"
            api_display = api_url
        except Exception as e:
            status_icon = f"⚠️ 错误"
            ui_url = "-"
            api_display = f"{api_url} ({str(e)[:30]})"
        
        lines.append(f"| {name} | {status_icon} | {api_display} | {ui_url} |")
    
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


# ========== 创建 UI ==========
init()

with gr.Blocks(title="SOLAR_MA - conductor 启明星") as demo:
    gr.Markdown("# 🎵 SOLAR_MA 猫群")
    gr.Markdown("启明星 | 所有小猫的牢大")
    
    with gr.Row():
        with gr.Column(scale=1, min_width=120):
            avatar_display = gr.HTML(value=get_avatar_html(DEFAULT_EMOTION))
            gr.Markdown("### Conductor")
        
        with gr.Column(scale=4):
            chatbot = gr.Chatbot(label="对话", height=500)
            msg = gr.Textbox(label="输入消息", placeholder="说点什么...", lines=2)
            clear_btn = gr.Button("清空对话")
    
    emotion_state = gr.State(value=DEFAULT_EMOTION)
    
    msg.submit(
        chat_with_conductor,
        [msg, chatbot],
        [msg, chatbot, emotion_state]
    ).then(
        lambda e: get_avatar_html(e),
        [emotion_state],
        [avatar_display]
    )
    
    clear_btn.click(lambda: [], None, chatbot)
    clear_btn.click(lambda: DEFAULT_EMOTION, None, emotion_state)
    clear_btn.click(lambda: get_avatar_html(DEFAULT_EMOTION), None, avatar_display)
    
    with gr.Tabs():
        with gr.TabItem("📦 Agent 管理"):
            status_output = gr.Markdown(get_all_agent_status())
            refresh_btn = gr.Button("刷新状态")
            refresh_btn.click(get_all_agent_status, None, status_output)
            
            gr.Markdown("### 启动/停止 Agent")
            with gr.Row():
                creator_start = gr.Button("启动 Creator", variant="primary")
                creator_stop = gr.Button("停止 Creator", variant="stop")
                scavenger_start = gr.Button("启动 Scavenger", variant="primary")
                scavenger_stop = gr.Button("停止 Scavenger", variant="stop")

                creator_status = gr.Markdown("")
            scavenger_status = gr.Markdown("")

            creator_start.click(lambda: start_agent("creator"), None, creator_status)
            creator_stop.click(lambda: stop_agent("creator"), None, creator_status)
            scavenger_start.click(lambda: start_agent("scavenger"), None, scavenger_status)
            scavenger_stop.click(lambda: stop_agent("scavenger"), None, scavenger_status)
        with gr.TabItem("🎯 任务调度"):
            agent_select = gr.Dropdown(choices=["creator", "scavenger"], label="选择 Agent")
            task_input = gr.Textbox(label="任务描述", placeholder="例如：生成一个椅子模型", lines=3)
            submit_btn = gr.Button("提交任务")
            task_result = gr.Markdown("")
            submit_btn.click(send_task_to_agent, [agent_select, task_input], task_result)


def main():
    print("=" * 50)
    print("🎵 SOLAR_MA Conductor 主控启动")
    print("=" * 50)
    print("📡 主控 UI: http://localhost:7860")
    print("💡 提示: 可在 Agent 管理页面启动子 Agent")
    print("=" * 50)
    
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        theme=gr.themes.Soft()
    )


if __name__ == "__main__":
    main()