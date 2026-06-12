"""Scavenger Agent 文件传输 - 连接主文件通道"""

import sys
from pathlib import Path

# 从主文件通道导入
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from conductor.core.file_transfer import get_file_transfer, FileTransfer

# 重导�?
__all__ = ["get_file_transfer", "FileTransfer"]