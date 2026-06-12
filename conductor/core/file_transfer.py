"""文件通道 - 共享文件夹传输"""

import shutil
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
import hashlib


class FileTransfer:
    """文件传输管理器（单例）- 双通道文件传输"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.base_dir = Path("shared/temp")
        self._file_metadata = {}  # 记录文件元数据
        self.reset()
    
    def reset(self):
        """重置共享文件夹（每次启动时调用）"""
        if self.base_dir.exists():
            shutil.rmtree(self.base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        self.input_dir = self.base_dir / "input"
        self.output_dir = self.base_dir / "output"
        self.input_dir.mkdir(exist_ok=True)
        self.output_dir.mkdir(exist_ok=True)
        
        self._file_metadata.clear()
        print("🗂️ 文件通道已重置")
    
    def _get_file_hash(self, file_path: Path) -> str:
        """计算文件哈希（用于去重）"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()[:16]
        except:
            return ""
    
    def _record_metadata(self, file_path: Path, direction: str, agent: str):
        """记录文件元数据"""
        self._file_metadata[file_path.name] = {
            "original_path": str(file_path),
            "direction": direction,
            "agent": agent,
            "timestamp": datetime.now().isoformat(),
            "size": file_path.stat().st_size,
            "hash": self._get_file_hash(file_path)
        }
    
    # ========== 发送文件（主→从）==========
    
    def send_file(self, source_path: Path, target_agent: str) -> Optional[str]:
        """
        发送文件到目标 Agent
        返回目标路径（移动后）
        """
        if not source_path.exists():
            print(f"❌ 文件不存在: {source_path}")
            return None
        
        target_dir = self.input_dir / target_agent
        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / source_path.name
        
        try:
            # 记录元数据（移动前）
            self._record_metadata(source_path, "send", target_agent)
            shutil.move(str(source_path), str(dest))
            print(f"📤 发送文件: {source_path.name} → {target_agent}")
            return str(dest)
        except Exception as e:
            print(f"❌ 发送文件失败: {e}")
            return None
    
    def send_files(self, source_paths: List[Path], target_agent: str) -> List[str]:
        """批量发送文件"""
        results = []
        for p in source_paths:
            dest = self.send_file(p, target_agent)
            if dest:
                results.append(dest)
        return results
    
    # ========== 接收文件（从→主）==========
    
    def receive_file(self, source_agent: str, filename: str, target_dir: Path) -> Optional[Path]:
        """
        从源 Agent 接收文件到目标目录
        返回目标路径（移动后）
        """
        source_dir = self.output_dir / source_agent
        source_path = source_dir / filename
        
        if not source_path.exists():
            print(f"❌ 文件不存在: {source_path}")
            return None
        
        dest = target_dir / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            self._record_metadata(source_path, "receive", source_agent)
            shutil.move(str(source_path), str(dest))
            print(f"📥 接收文件: {filename} ← {source_agent}")
            return dest
        except Exception as e:
            print(f"❌ 接收文件失败: {e}")
            return None
    
    def receive_files(self, source_agent: str, filenames: List[str], target_dir: Path) -> List[Path]:
        """批量接收文件"""
        results = []
        for name in filenames:
            dest = self.receive_file(source_agent, name, target_dir)
            if dest:
                results.append(dest)
        return results
    
    # ========== 目录管理 ==========
    
    def get_input_dir(self, target_agent: str) -> Path:
        """获取发送到指定 Agent 的输入目录"""
        target_dir = self.input_dir / target_agent
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir
    
    def get_output_dir(self, source_agent: str) -> Path:
        """获取从指定 Agent 接收的输出目录"""
        target_dir = self.output_dir / source_agent
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir
    
    def list_input_files(self, agent_name: str) -> List[Path]:
        """列出指定 Agent 的待处理输入文件"""
        input_dir = self.get_input_dir(agent_name)
        return list(input_dir.iterdir())
    
    def list_output_files(self, agent_name: str) -> List[Path]:
        """列出指定 Agent 已生成的输出文件"""
        output_dir = self.get_output_dir(agent_name)
        return list(output_dir.iterdir())
    
    # ========== 文件信息查询 ==========
    
    def get_file_metadata(self, filename: str) -> Optional[dict]:
        """获取文件元数据"""
        return self._file_metadata.get(filename)
    
    def get_file_hash(self, file_path: Path) -> str:
        """获取文件哈希"""
        return self._get_file_hash(file_path)
    
    def is_duplicate(self, file_path: Path) -> bool:
        """检查是否为重复文件"""
        file_hash = self._get_file_hash(file_path)
        for metadata in self._file_metadata.values():
            if metadata.get("hash") == file_hash:
                return True
        return False
    
    # ========== 清理 ==========
    
    def cleanup_input(self, agent_name: str, filename: str = None):
        """清理输入目录中的文件"""
        input_dir = self.get_input_dir(agent_name)
        if filename:
            (input_dir / filename).unlink(missing_ok=True)
        else:
            for f in input_dir.iterdir():
                f.unlink()
    
    def cleanup_output(self, agent_name: str, filename: str = None):
        """清理输出目录中的文件"""
        output_dir = self.get_output_dir(agent_name)
        if filename:
            (output_dir / filename).unlink(missing_ok=True)
        else:
            for f in output_dir.iterdir():
                f.unlink()
    
    def cleanup_all(self):
        """清空所有临时文件"""
        for f in self.input_dir.rglob("*"):
            if f.is_file():
                f.unlink()
        for f in self.output_dir.rglob("*"):
            if f.is_file():
                f.unlink()
        self._file_metadata.clear()
        print("🗑️ 所有临时文件已清空")
    
    def cleanup_old_files(self, hours: int = 24):
        """清理过期文件（基于修改时间）"""
        cutoff = datetime.now().timestamp() - hours * 3600
        count = 0
        for f in self.base_dir.rglob("*"):
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
                count += 1
        if count > 0:
            print(f"🗑️ 清理了 {count} 个过期文件")
    
    # ========== 状态查询 ==========
    
    def get_stats(self) -> dict:
        """获取文件通道统计信息"""
        input_count = sum(1 for _ in self.input_dir.rglob("*") if _.is_file())
        output_count = sum(1 for _ in self.output_dir.rglob("*") if _.is_file())
        
        return {
            "input_files": input_count,
            "output_files": output_count,
            "total_transferred": len(self._file_metadata),
            "temp_dir": str(self.base_dir)
        }


# 全局单例
_file_transfer = None

def get_file_transfer() -> FileTransfer:
    global _file_transfer
    if _file_transfer is None:
        _file_transfer = FileTransfer()
    return _file_transfer