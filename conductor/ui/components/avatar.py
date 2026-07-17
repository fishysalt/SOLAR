"""头像组件 - 复用 conductor/portraits/ 中的图片"""

import base64
from pathlib import Path
from typing import Optional

# 头像目录
PORTRAITS_DIR = Path(__file__).parent.parent.parent.parent / "conductor" / "portraits"

# 情绪映射（与 Gradio 版本一致）
EMOTION_MAPPING = {
    "motivated": {"name": "干劲十足", "file": "干劲十足.jpg"},
    "happy": {"name": "高兴", "file": "高兴.png"},
    "surprised": {"name": "惊讶", "file": "惊讶.png"},
    "tired": {"name": "疲劳", "file": "疲劳.jpg"},
    "success": {"name": "任务成功", "file": "任务成功.jpg"},
    "working": {"name": "任务进行", "file": "任务进行.jpg"},
    "failed": {"name": "任务失败", "file": "任务失败.webp"},
    "sad": {"name": "伤心", "file": "伤心.jpg"},
    "angry": {"name": "生气", "file": "生气.jpg"},
    "sleeping": {"name": "睡大觉", "file": "睡大觉.jpg"},
    "praising": {"name": "赞赏", "file": "赞赏.jpg"},
}

DEFAULT_EMOTION = "motivated"


def get_avatar_base64(emotion_tag: str = DEFAULT_EMOTION) -> Optional[str]:
    """获取头像的 base64 编码"""
    if emotion_tag not in EMOTION_MAPPING:
        emotion_tag = DEFAULT_EMOTION
    
    filename = EMOTION_MAPPING[emotion_tag]["file"]
    img_path = PORTRAITS_DIR / filename
    
    if not img_path.exists():
        # fallback: 使用第一个存在的图片
        for f in PORTRAITS_DIR.iterdir():
            if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']:
                img_path = f
                break
        else:
            return None
    
    try:
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
    except Exception:
        return None


def get_avatar_html(emotion_tag: str = DEFAULT_EMOTION, size: int = 80) -> str:
    """生成头像 HTML"""
    img_data = get_avatar_base64(emotion_tag)
    if not img_data:
        return ""
    
    name = EMOTION_MAPPING.get(emotion_tag, {}).get("name", "")
    
    return f"""
    <div style="text-align: center; display: inline-block;">
        <img src="{img_data}" 
             style="width: {size}px; height: {size}px; border-radius: 50%; 
                    object-fit: cover; border: 3px solid #4CAF50;">
        <div style="margin-top: 4px; font-size: 12px; color: #888;">
            {name}
        </div>
    </div>
    """


def get_emotion_list() -> str:
    """获取情绪标签列表（供UI选择）"""
    return "\n".join([f"- `{tag}`: {info['name']}" for tag, info in EMOTION_MAPPING.items()])