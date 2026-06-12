"""文件处理工具 - 简单直接，不限制路径"""

import os
import shutil
import subprocess
import platform
from pathlib import Path


def list_directory(dir_path: str = ".", show_hidden: bool = False) -> str:
    """列出目录内容"""
    try:
        path = Path(dir_path)
        if not path.exists():
            return f"❌ 目录不存在: {dir_path}"
        
        if not path.is_dir():
            return f"❌ 不是目录: {dir_path}"
        
        items = []
        for item in path.iterdir():
            if not show_hidden and item.name.startswith('.'):
                continue
            if item.is_dir():
                items.append(f"📁 {item.name}/")
            else:
                size = item.stat().st_size
                if size < 1024:
                    size_str = f"{size}B"
                elif size < 1024 * 1024:
                    size_str = f"{size/1024:.1f}KB"
                else:
                    size_str = f"{size/(1024*1024):.1f}MB"
                items.append(f"📄 {item.name} ({size_str})")
        
        if not items:
            return "📭 目录为空"
        
        result = f"📂 目录: {path.absolute()}\n\n"
        result += "\n".join(sorted(items))
        return result
        
    except Exception as e:
        return f"❌ 列出失败: {str(e)}"


def read_text_file(file_path: str, max_lines: int = 1000) -> str:
    """读取文本文件内容"""
    try:
        path = Path(file_path)
        if not path.exists():
            return f"❌ 文件不存在: {file_path}"
        
        if path.is_dir():
            return f"❌ 这是一个目录: {file_path}"
        
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        total_lines = len(lines)
        display_lines = lines[:max_lines]
        
        result = f"📄 文件: {path.absolute()}\n总行数: {total_lines}\n\n"
        result += "".join(display_lines)
        
        if total_lines > max_lines:
            result += f"\n... (还有 {total_lines - max_lines} 行)"
        
        return result
        
    except UnicodeDecodeError:
        return f"❌ 不是文本文件: {file_path}"
    except Exception as e:
        return f"❌ 读取失败: {str(e)}"

def view_image(file_path: str) -> str:
    """使用系统默认图片查看器打开图片"""
    import subprocess
    import platform
    
    try:
        path = Path(file_path)
        if not path.exists():
            return f"❌ 文件不存在: {file_path}"
        
        if path.is_dir():
            return f"❌ 这是一个目录: {file_path}"
        
        ext = path.suffix.lower()
        if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
            return f"❌ 不支持的文件格式: {ext}"
        
        size_kb = path.stat().st_size / 1024
        system = platform.system()
        
        if system == "Windows":
            os.startfile(str(path))
        elif system == "Darwin":
            subprocess.run(["open", str(path)])
        else:
            subprocess.run(["xdg-open", str(path)])
        
        return f"✅ 已打开图片\n\n📄 {path.name} ({size_kb:.0f}KB)\n📁 {path.absolute()}"
    
    except Exception as e:
        return f"❌ 打开失败: {str(e)}"


def open_with_player(file_path: str) -> str:
    """使用系统播放器打开视频/音频"""
    try:
        path = Path(file_path)
        if not path.exists():
            return f"❌ 文件不存在: {file_path}"
        
        ext = path.suffix.lower()
        video_exts = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm']
        audio_exts = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a']
        
        if ext not in video_exts + audio_exts:
            return f"❌ 不支持的文件格式: {ext}"
        
        size_mb = path.stat().st_size / (1024 * 1024)
        file_type = "视频" if ext in video_exts else "音频"
        
        system = platform.system()
        
        if system == "Windows":
            os.startfile(str(path))
        elif system == "Darwin":
            subprocess.run(["open", str(path)])
        else:
            subprocess.run(["xdg-open", str(path)])
        
        return f"✅ 已打开 {file_type}文件\n\n📄 {path.name} ({size_mb:.1f}MB)\n📁 {path.absolute()}"
    
    except Exception as e:
        return f"❌ 打开失败: {str(e)}"


def copy_file(source: str, target: str) -> str:
    """复制文件"""
    try:
        src = Path(source)
        if not src.exists():
            return f"❌ 源文件不存在: {source}"
        
        if src.is_dir():
            return f"❌ 源文件是目录: {source}"
        
        dst = Path(target)
        if dst.is_dir():
            dst = dst / src.name
        
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        
        size_kb = src.stat().st_size / 1024
        return f"✅ 已复制\n📄 {src.name} ({size_kb:.0f}KB)\n📤 {dst.absolute()}"
    
    except Exception as e:
        return f"❌ 复制失败: {str(e)}"


def move_file(source: str, target: str) -> str:
    """移动文件"""
    try:
        src = Path(source)
        if not src.exists():
            return f"❌ 源文件不存在: {source}"
        
        if src.is_dir():
            return f"❌ 源文件是目录: {source}"
        
        dst = Path(target)
        if dst.is_dir():
            dst = dst / src.name
        
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        
        size_kb = src.stat().st_size / 1024
        return f"✅ 已移动\n📄 {src.name} ({size_kb:.0f}KB)\n📤 {dst.absolute()}"
    
    except Exception as e:
        return f"❌ 移动失败: {str(e)}"


def delete_file(file_path: str, confirm: bool = False) -> str:
    """删除文件"""
    try:
        path = Path(file_path)
        if not path.exists():
            return f"❌ 文件不存在: {file_path}"
        
        if path.is_dir():
            return f"❌ 这是目录，请使用 delete_directory"
        
        if not confirm:
            return f"⚠️ 确认删除文件: {path.name}\n\n再次调用并设置 confirm=true 以确认删除"
        
        size_kb = path.stat().st_size / 1024
        path.unlink()
        return f"✅ 已删除\n📄 {path.name} ({size_kb:.0f}KB)"
    
    except Exception as e:
        return f"❌ 删除失败: {str(e)}"


# 工具定义
LIST_DIRECTORY_TOOL = {
    "name": "list_directory",
    "description": "列出目录中的文件和子目录。",
    "func": list_directory,
    "parameters": {
        "type": "object",
        "properties": {
            "dir_path": {"type": "string", "description": "目录路径", "default": "."},
            "show_hidden": {"type": "boolean", "description": "是否显示隐藏文件", "default": False}
        },
        "required": []
    }
}

READ_TEXT_FILE_TOOL = {
    "name": "read_text_file",
    "description": "读取文本文件内容。",
    "func": read_text_file,
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "文件路径"},
            "max_lines": {"type": "integer", "description": "最大读取行数", "default": 1000}
        },
        "required": ["file_path"]
    }
}

VIEW_IMAGE_TOOL = {
    "name": "view_image",
    "description": "使用系统默认图片查看器打开图片。",
    "func": view_image,
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "图片文件路径"}
        },
        "required": ["file_path"]
    }
}

OPEN_WITH_PLAYER_TOOL = {
    "name": "open_with_player",
    "description": "使用系统播放器打开视频或音频文件。",
    "func": open_with_player,
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "文件路径"}
        },
        "required": ["file_path"]
    }
}

COPY_FILE_TOOL = {
    "name": "copy_file",
    "description": "复制文件到目标位置。",
    "func": copy_file,
    "parameters": {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "源文件路径"},
            "target": {"type": "string", "description": "目标路径（文件或目录）"}
        },
        "required": ["source", "target"]
    }
}

MOVE_FILE_TOOL = {
    "name": "move_file",
    "description": "移动文件到目标位置。",
    "func": move_file,
    "parameters": {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "源文件路径"},
            "target": {"type": "string", "description": "目标路径（文件或目录）"}
        },
        "required": ["source", "target"]
    }
}

DELETE_FILE_TOOL = {
    "name": "delete_file",
    "description": "删除文件（需要确认）。",
    "func": delete_file,
    "parameters": {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "文件路径"},
            "confirm": {"type": "boolean", "description": "是否确认", "default": False}
        },
        "required": ["file_path"]
    }
}