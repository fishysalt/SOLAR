"""工具类别定义 - 可单独修改"""

from enum import Enum
from typing import List, Dict


class ToolCategory(Enum):
    """工具类别枚举"""
    VIDEO = "video"
    MODEL_3D = "model_3d"
    SEARCH = "search"
    IMAGE = "image"
    AUDIO = "audio"
    DATA = "data"
    CODE = "code"
    FILE = "file"
    WEB = "web"
    TEXT = "text"
    OTHER = "other"


# 类别描述（供 LLM 理解）
CATEGORY_DESCRIPTIONS: Dict[ToolCategory, str] = {
    ToolCategory.VIDEO: "视频生成、编辑、处理相关工具",
    ToolCategory.MODEL_3D: "3D模型生成、转换、处理相关工具",
    ToolCategory.SEARCH: "信息搜索、查询相关工具",
    ToolCategory.IMAGE: "图像生成、编辑、识别相关工具",
    ToolCategory.AUDIO: "音频生成、处理相关工具",
    ToolCategory.DATA: "数据分析、处理、可视化相关工具",
    ToolCategory.CODE: "代码生成、执行、分析相关工具",
    ToolCategory.FILE: "文件读写、管理相关工具",
    ToolCategory.WEB: "网页抓取、HTTP请求相关工具",
    ToolCategory.TEXT: "文本处理、转换相关工具",
    ToolCategory.OTHER: "其他类型工具",
}


# 类别与工具名的映射（仅用于初始注册时的自动分类，不用于运行时判断）
# 注意：这只是方便注册的辅助映射，最终分类由 LLM 根据 description 决定
NAME_TO_CATEGORY: Dict[str, ToolCategory] = {
    # 视频类
    "video": ToolCategory.VIDEO,
    "generate_video": ToolCategory.VIDEO,
    "video_gen": ToolCategory.VIDEO,
    
    # 3D模型类
    "model": ToolCategory.MODEL_3D,
    "generate_3d": ToolCategory.MODEL_3D,
    "model_gen": ToolCategory.MODEL_3D,
    "glb": ToolCategory.MODEL_3D,
    
    # 搜索类
    "search": ToolCategory.SEARCH,
    "web_search": ToolCategory.SEARCH,
    "query": ToolCategory.SEARCH,
    
    # 图像类
    "image": ToolCategory.IMAGE,
    "generate_image": ToolCategory.IMAGE,
    
    # 音频类
    "audio": ToolCategory.AUDIO,
    "tts": ToolCategory.AUDIO,
    
    # 数据类
    "data": ToolCategory.DATA,
    "analyze": ToolCategory.DATA,
    "pca": ToolCategory.DATA,
    
    # 代码类
    "code": ToolCategory.CODE,
    "execute": ToolCategory.CODE,
    
    # 文件类
    "file": ToolCategory.FILE,
    "read": ToolCategory.FILE,
    "write": ToolCategory.FILE,
    
    # 网页类
    "web": ToolCategory.WEB,
    "http": ToolCategory.WEB,
    
    # 文本类
    "text": ToolCategory.TEXT,
    "parse": ToolCategory.TEXT,
}


def infer_category_from_name(tool_name: str) -> ToolCategory:
    """
    根据工具名称推断类别（仅用于注册时的初始分类）
    
    注意：这只是辅助功能，真正的工具选择由 LLM 根据 description 决定
    """
    name_lower = tool_name.lower()
    
    for key, category in NAME_TO_CATEGORY.items():
        if key in name_lower:
            return category
    
    return ToolCategory.OTHER


def get_category_description(category: ToolCategory) -> str:
    """获取类别描述"""
    return CATEGORY_DESCRIPTIONS.get(category, "未分类")