"""MCP 调用日志记录器 - 记录所有调用的输入和原始输出"""

import json
import os
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List  # ← 添加 List
import threading


class MCPLogger:
    """
    MCP 调用日志记录器（单例）
    记录每次 MCP 调用的完整信息，供后续分析和自进化使用
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        # 日志目录
        self.log_dir = Path(__file__).parent / "logs" / "mcp_calls"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 当前会话 ID
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 调用计数器
        self.call_counter = 0
        self._lock = threading.Lock()
        
        print(f"📝 MCP 日志记录器已初始化")
        print(f"   📁 日志目录: {self.log_dir}")
        print(f"   🆔 会话 ID: {self.session_id}")
    
    def log_call(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        request_id: str,
        raw_request: str = None
    ) -> str:
        """
        记录工具调用开始
        
        Returns:
            call_id: 调用 ID
        """
        with self._lock:
            self.call_counter += 1
            call_id = f"{self.session_id}_{self.call_counter:04d}"
        
        timestamp = datetime.now().isoformat()
        
        # 构建日志条目
        entry = {
            "call_id": call_id,
            "session_id": self.session_id,
            "timestamp": timestamp,
            "server_name": server_name,
            "tool_name": tool_name,
            "arguments": arguments,
            "request_id": request_id,
            "raw_request": raw_request,
            "status": "started",
            "response": None,
            "raw_response": None,
            "error": None,
            "duration": None
        }
        
        # 保存到文件
        self._save_entry(call_id, entry)
        
        return call_id
    
    def log_response(
        self,
        call_id: str,
        response: Any,
        raw_response: str = None,
        error: str = None,
        duration: float = None
    ):
        """
        记录工具调用完成
        """
        entry = self._load_entry(call_id)
        if not entry:
            return
        
        entry["status"] = "completed" if not error else "error"
        entry["response"] = response
        entry["raw_response"] = raw_response
        entry["error"] = error
        entry["duration"] = duration
        
        self._save_entry(call_id, entry)
    
    def log_timeout(self, call_id: str, timeout: float):
        """
        记录工具调用超时
        """
        entry = self._load_entry(call_id)
        if not entry:
            return
        
        entry["status"] = "timeout"
        entry["error"] = f"超时 ({timeout}秒)"
        entry["duration"] = timeout
        
        self._save_entry(call_id, entry)
    
    def _save_entry(self, call_id: str, entry: Dict):
        """保存日志条目到文件"""
        file_path = self.log_dir / f"{call_id}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
    
    def _load_entry(self, call_id: str) -> Optional[Dict]:
        """加载日志条目"""
        file_path = self.log_dir / f"{call_id}.json"
        if not file_path.exists():
            return None
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_session_logs(self) -> List[str]:
        """获取当前会话的所有日志文件"""
        return [f.name for f in self.log_dir.glob(f"{self.session_id}_*.json")]
    
    def get_call(self, call_id: str) -> Optional[Dict]:
        """获取指定调用的完整日志"""
        return self._load_entry(call_id)
    
    def export_session(self) -> str:
        """导出当前会话的所有日志"""
        entries = []
        for f in sorted(self.log_dir.glob(f"{self.session_id}_*.json")):
            with open(f, 'r', encoding='utf-8') as fp:
                entries.append(json.load(fp))
        
        export_file = self.log_dir / f"{self.session_id}_session.json"
        with open(export_file, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        
        return str(export_file)
    
    def get_error_summary(self) -> str:
        """获取当前会话的错误摘要"""
        entries = []
        for f in sorted(self.log_dir.glob(f"{self.session_id}_*.json")):
            with open(f, 'r', encoding='utf-8') as fp:
                entry = json.load(fp)
                if entry.get("status") in ["error", "timeout"]:
                    entries.append(entry)
        
        if not entries:
            return "✅ 当前会话无错误"
        
        result = ["📊 错误摘要:\n"]
        for e in entries[:20]:
            result.append(f"  - {e['call_id']}: {e['tool_name']} -> {e['status']}")
            if e.get('error'):
                result.append(f"    错误: {e['error'][:200]}")
            result.append("")
        
        if len(entries) > 20:
            result.append(f"  ... 还有 {len(entries) - 20} 个错误")
        
        return "\n".join(result)


# 全局单例
_logger = None

def get_mcp_logger() -> MCPLogger:
    global _logger
    if _logger is None:
        _logger = MCPLogger()
    return _logger