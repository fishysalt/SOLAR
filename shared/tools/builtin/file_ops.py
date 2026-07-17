"""文件操作内置工具"""

from ..models import ToolInfo, ToolType


def list_directory_sync(dir_path: str = ".") -> str:
    try:
        from pathlib import Path
        path = Path(dir_path)
        if not path.exists():
            return f"❌ 目录不存在: {dir_path}"
        items = "\n".join([f"📁 {p.name}" if p.is_dir() else f"📄 {p.name}" for p in path.iterdir()])
        return f"📂 {dir_path}\n{items}"
    except Exception as e:
        return f"❌ 列出失败: {str(e)}"


def read_text_file_sync(file_path: str) -> str:
    try:
        from pathlib import Path
        path = Path(file_path)
        if not path.exists():
            return f"❌ 文件不存在: {file_path}"
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        return f"📄 {file_path}\n\n{content[:1000]}"
    except Exception as e:
        return f"❌ 读取失败: {str(e)}"


LIST_DIRECTORY_TOOL = ToolInfo(
    name="list_directory",
    description="列出目录内容",
    parameters={
        "type": "object",
        "properties": {
            "dir_path": {"type": "string", "description": "目录路径", "default": "."}
        },
        "required": []
    },
    tool_type=ToolType.BUILTIN,
    estimated_wait_time=0.05,
    func=list_directory_sync,
    is_async=False
)

READ_TEXT_FILE_TOOL = ToolInfo(
    name="read_text_file",
    description="读取文本文件",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "文件路径"}
        },
        "required": ["file_path"]
    },
    tool_type=ToolType.BUILTIN,
    estimated_wait_time=0.05,
    func=read_text_file_sync,
    is_async=False
)