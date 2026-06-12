"""从 Agent 启动器 - 管理子进程 + HTTP 状态检测"""

import subprocess
import socket
import time
import sys
from pathlib import Path
from typing import Dict, Optional, Union


class AgentLauncher:
    """从 Agent 启动器"""
    
    PORT_MAP = {
        "creator": 7861,
        "visualization": 7862,
    }
    
    UI_PORT_OFFSET = 100
    
    def __init__(self):
        self._processes: Dict[str, Union[subprocess.Popen, str]] = {}
        self._api_ports: Dict[str, int] = {}
    
    def _find_available_port(self, preferred: int) -> int:
        """查找可用端口"""
        port = preferred
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(('127.0.0.1', port))
                    return port
                except OSError:
                    port += 1
    
    def _check_http_health(self, port: int, timeout: float = 2.0) -> bool:
        """通过 HTTP 健康检查检测 Agent 是否运行"""
        try:
            import requests
            resp = requests.get(f"http://localhost:{port}/api/health", timeout=timeout)
            return resp.status_code == 200
        except:
            return False
    
    def start_agent(self, agent_name: str) -> bool:
        """启动从 Agent"""
        # 检查是否已运行
        if self.get_status(agent_name) == "running":
            print(f"⚠️ {agent_name} 已经在运行")
            return True
        
        base_dir = Path(__file__).parent.parent
        agent_script = base_dir / agent_name / "ui.py"
        
        if not agent_script.exists():
            print(f"❌ 未找到 {agent_name} 的启动脚本: {agent_script}")
            return False
        
        # 分配 API 端口
        preferred_port = self.PORT_MAP.get(agent_name, 7861)
        api_port = self._find_available_port(preferred_port)
        
        print(f"🚀 启动 {agent_name}，API 端口: {api_port}")
        
        env = {
            **subprocess.os.environ,
            "AGENT_NAME": agent_name,
            "AGENT_PORT": str(api_port),
        }
        
        try:
            proc = subprocess.Popen(
                [sys.executable, str(agent_script)],
                env=env,
                cwd=str(base_dir)
            )
            
            self._processes[agent_name] = proc
            self._api_ports[agent_name] = api_port
            
            # 等待服务启动（最多 5 秒，每 0.5 秒检查一次）
            print(f"   ⏳ 等待 {agent_name} API 就绪...")
            for i in range(10):  # 10 * 0.5 = 5 秒
                time.sleep(0.5)
                if self._check_http_health(api_port, timeout=1.0):
                    print(f"   ✅ {agent_name} API 健康检查通过")
                    print(f"✅ {agent_name} 已启动 (API: {api_port})")
                    return True
            
            # 超时失败
            print(f"   ❌ {agent_name} 启动超时（5秒），未收到健康响应")
            print(f"   💡 提示：请检查 {agent_name} 是否正常启动")
            print(f"   💡 或手动运行: python {agent_name}/ui.py")
            return False
            
        except Exception as e:
            print(f"❌ 启动 {agent_name} 失败: {e}")
            return False
    
    def stop_agent(self, agent_name: str) -> bool:
        """停止从 Agent"""
        status = self.get_status(agent_name)
        if status != "running":
            print(f"⚠️ {agent_name} 未运行")
            return False
        
        proc = self._processes.get(agent_name)
        if proc and proc != "external":
            # 是 Conductor 启动的进程，终止它
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        
        # 清理记录
        if agent_name in self._processes:
            del self._processes[agent_name]
        if agent_name in self._api_ports:
            del self._api_ports[agent_name]
        
        print(f"🛑 {agent_name} 已停止")
        return True
    
    def get_status(self, agent_name: str) -> str:
        """
        获取 Agent 状态（完全基于 HTTP 健康检查）
        
        Returns:
            "running" - HTTP 健康检查通过
            "stopped" - 连接失败
        """
        # 获取 API 端口
        port = self._api_ports.get(agent_name)
        if not port:
            # 尝试从配置获取默认端口
            port = self.PORT_MAP.get(agent_name)
            if not port:
                return "stopped"
        
        # 实时 HTTP 健康检查
        if self._check_http_health(port, timeout=2.0):
            return "running"
        else:
            return "stopped"
    
    def get_api_port(self, agent_name: str) -> Optional[int]:
        """获取 Agent 的 API 端口"""
        return self._api_ports.get(agent_name)
    
    def list_agents(self) -> Dict[str, str]:
        """列出所有 Agent 状态"""
        return {name: self.get_status(name) for name in self.PORT_MAP.keys()}
    
    def stop_all(self):
        for name in list(self._processes.keys()):
            self.stop_agent(name)


_launcher = None

def get_agent_launcher() -> AgentLauncher:
    global _launcher
    if _launcher is None:
        _launcher = AgentLauncher()
    return _launcher