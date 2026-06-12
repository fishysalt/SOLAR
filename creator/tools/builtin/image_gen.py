"""千问图片生成工具 - 支持文生图和参考图生成，返回绝对路径"""

import os
import base64
import httpx
import time
from pathlib import Path
from typing import Optional
from datetime import datetime

from conductor.utils import log_with_timestamp


def _get_api_key() -> str:
    """从 creator/.env 读取 API Key"""
    env_file = Path(__file__).parent.parent.parent / ".env"
    
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('DASHSCOPE_API_KEY='):
                    key = line.split('=', 1)[1].strip()
                    if key.startswith('"') and key.endswith('"'):
                        key = key[1:-1]
                    if key.startswith("'") and key.endswith("'"):
                        key = key[1:-1]
                    return key
    
    return os.environ.get("DASHSCOPE_API_KEY", "")


def _get_output_dir() -> Path:
    """获取输出目录"""
    current_dir = Path(__file__).parent
    creator_root = current_dir.parent.parent
    output_dir = creator_root / "data" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _download_image(url: str, filename: str = None) -> Path:
    """下载图片到本地，返回本地路径"""
    output_dir = _get_output_dir()
    
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"image_{timestamp}_{int(time.time()*1000) % 10000}.png"
    
    local_path = output_dir / filename
    
    with httpx.Client(timeout=60.0) as client:
        response = client.get(url)
        response.raise_for_status()
        with open(local_path, 'wb') as f:
            f.write(response.content)
    
    log_with_timestamp("image_gen", "INFO", f"图片已保存: {local_path}")
    return local_path


QWEN_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
QWEN_MODEL = "wan2.7-image-pro"


def generate_image(
    prompt: str,
    size: str = "2K",
    n: int = 1,
    watermark: bool = False,
    seed: Optional[int] = None,
    aspect_ratio: Optional[str] = None
) -> str:
    """
    文生图：根据文字描述生成图片，返回本地绝对路径
    """
    api_key = _get_api_key()
    if not api_key:
        return "ERROR: 未配置 DASHSCOPE_API_KEY"
    
    content = [{"text": prompt}]
    if aspect_ratio:
        content.append({"text": f"宽高比 {aspect_ratio}"})
    
    request_body = {
        "model": QWEN_MODEL,
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": {"size": size, "n": n, "watermark": watermark}
    }
    if seed is not None:
        request_body["parameters"]["seed"] = seed
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    log_with_timestamp("image_gen", "INFO", f"文生图: {prompt[:50]}...")
    
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(QWEN_API_URL, json=request_body, headers=headers)
            response.raise_for_status()
            result = response.json()
            
            if "code" in result:
                return f"ERROR: {result.get('code')} - {result.get('message', '未知错误')}"
            
            image_urls = []
            for choice in result.get("output", {}).get("choices", []):
                for item in choice.get("message", {}).get("content", []):
                    if item.get("type") == "image":
                        image_urls.append(item.get("image"))
            
            if not image_urls:
                return "ERROR: 未生成图片"
            
            local_path = _download_image(image_urls[0])
            return str(local_path.absolute())
            
    except Exception as e:
        return f"ERROR: {str(e)}"


def generate_image_with_reference(
    prompt: str,
    reference_image: str,
    size: str = "2K",
    n: int = 1,
    watermark: bool = False,
    seed: Optional[int] = None
) -> str:
    """
    参考图生成图片（图像编辑/风格迁移），返回本地绝对路径
    
    Args:
        prompt: 图片描述提示词
        reference_image: 参考图（支持 URL、本地路径、Base64）
        size: 分辨率（1K 或 2K，不支持4K）
        n: 生成数量（1-4）
        watermark: 是否添加水印
        seed: 随机种子
    """
    api_key = _get_api_key()
    if not api_key:
        return "ERROR: 未配置 DASHSCOPE_API_KEY"
    
    # 构建 content：先放参考图，再放文字
    content = []
    
    # 处理参考图
    if reference_image.startswith(('http://', 'https://')):
        # URL 格式
        content.append({"image": reference_image})
    elif reference_image.startswith('data:'):
        # Base64 格式
        content.append({"image": reference_image})
    else:
        # 本地文件路径，转换为 Base64
        ref_path = Path(reference_image)
        if not ref_path.exists():
            return f"ERROR: 参考图不存在: {reference_image}"
        
        try:
            with open(ref_path, 'rb') as f:
                img_data = base64.b64encode(f.read()).decode('utf-8')
                suffix = ref_path.suffix.lower()
                if suffix in ['.jpg', '.jpeg']:
                    mime_type = "image/jpeg"
                elif suffix == '.png':
                    mime_type = "image/png"
                elif suffix == '.webp':
                    mime_type = "image/webp"
                else:
                    mime_type = "image/png"
                content.append({"image": f"data:{mime_type};base64,{img_data}"})
        except Exception as e:
            return f"ERROR: 读取参考图失败: {str(e)}"
    
    # 添加文字提示
    content.append({"text": prompt})
    
    request_body = {
        "model": QWEN_MODEL,
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": {"size": size, "n": n, "watermark": watermark}
    }
    if seed is not None:
        request_body["parameters"]["seed"] = seed
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    log_with_timestamp("image_gen", "INFO", f"参考图生图: {prompt[:50]}...")
    
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(QWEN_API_URL, json=request_body, headers=headers)
            response.raise_for_status()
            result = response.json()
            
            if "code" in result:
                return f"ERROR: {result.get('code')} - {result.get('message', '未知错误')}"
            
            image_urls = []
            for choice in result.get("output", {}).get("choices", []):
                for item in choice.get("message", {}).get("content", []):
                    if item.get("type") == "image":
                        image_urls.append(item.get("image"))
            
            if not image_urls:
                return "ERROR: 未生成图片"
            
            local_path = _download_image(image_urls[0])
            return str(local_path.absolute())
            
    except Exception as e:
        return f"ERROR: {str(e)}"


# 工具定义
GENERATE_IMAGE_TOOL = {
    "name": "generate_image",
    "description": "根据文字描述生成图片，返回本地绝对路径。",
    "func": generate_image,
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "图片描述"},
            "size": {"type": "string", "description": "分辨率", "enum": ["1K", "2K", "4K"], "default": "2K"},
            "n": {"type": "integer", "description": "生成数量", "default": 1},
            "watermark": {"type": "boolean", "description": "水印", "default": False},
            "aspect_ratio": {"type": "string", "description": "宽高比"}
        },
        "required": ["prompt"]
    }
}

GENERATE_IMAGE_WITH_REFERENCE_TOOL = {
    "name": "generate_image_with_reference",
    "description": "根据参考图和文字描述生成图片（风格迁移/图像编辑），返回本地绝对路径。",
    "func": generate_image_with_reference,
    "parameters": {
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "图片描述"},
            "reference_image": {"type": "string", "description": "参考图（URL或本地路径）"},
            "size": {"type": "string", "description": "分辨率", "enum": ["1K", "2K"], "default": "2K"},
            "n": {"type": "integer", "description": "生成数量", "default": 1},
            "watermark": {"type": "boolean", "description": "水印", "default": False}
        },
        "required": ["prompt", "reference_image"]
    }
}