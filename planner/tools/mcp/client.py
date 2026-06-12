"""MCP 协议客户端 - 实现 JSON-RPC 通信"""

import json
import subprocess
import threading
import queue
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import sys


@dataclass
class MCPTool:
    """MCP 工具信息"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str


class MCPClient:
    """
    MCP 协议客户端
    负责与单个 MCP Server 的通信
    """
    
    def __init__(self, server_name: str, command: str, args: List[str] = None, env: Dict[str, str] = None):
        """
        初始化 MCP 客户端
        
        Args:
            server_name: Server 名称（如 "seadance"）
            command: 启动命令（如 "npx"）
            args: 命令参数（如 ["-y", "seadance-mcp"]）
            env: 环境变量（如 {"API_KEY": "xxx"}）
        """
        self.server_name = server_name
        self.command = command
        self.args = args or []
        self.env = env or {}
        
        self._process: Optional[subprocess.Popen] = None
        self._read_thread: Optional[threading.Thread] = None
        self._write_queue: queue.Queue = queue.Queue()
        self._pending_requests: Dict[str, queue.Queue] = {}
        self._request_counter = 0
        self._running = False
        self._initialized = False
        
        self.tools: List[MCPTool] = []
    
    def start(self) -> bool:
        """启动 MCP Server 子进程"""
        try:
            # 合并环境变量
            env = {**subprocess.os.environ, **self.env}
            
            # 启动子进程
            self._process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1
            )
            
            self._running = True
            
            # 启动读取线程
            self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._read_thread.start()
            
            # 初始化连接
            if not self._initialize():
                return False
            
            # 发现工具
            self._discover_tools()
            
            print(f"   ✅ MCP Client 已连接: {self.server_name} ({len(self.tools)} 个工具)")
            
            return True
            
        except Exception as e:
            print(f"   ❌ MCP Client 启动失败 ({self.server_name}): {e}")
            return False
    
    def _initialize(self) -> bool:
        """发送初始化请求"""
        result = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "creator-mcp-client",
                "version": "1.0.0"
            }
        })
        
        if result and "protocolVersion" in result:
            self._initialized = True
            # 发送 initialized 通知
            self._send_notification("notifications/initialized", {})
            return True
        
        return False
    
    def _discover_tools(self):
        """发现 Server 提供的工具"""
        result = self._send_request("tools/list", {})
        
        if result and "tools" in result:
            for tool_info in result["tools"]:
                tool = MCPTool(
                    name=tool_info["name"],
                    description=tool_info.get("description", ""),
                    input_schema=tool_info.get("inputSchema", {"type": "object", "properties": {}}),
                    server_name=self.server_name
                )
                self.tools.append(tool)
    
    def _send_request(self, method: str, params: Dict) -> Optional[Dict]:
        """发送 JSON-RPC 请求并等待响应"""
        self._request_counter += 1
        request_id = f"{self.server_name}_{self._request_counter}"
        
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }
        
        # 创建响应队列
        response_queue = queue.Queue()
        self._pending_requests[request_id] = response_queue
        
        # 发送请求
        self._send_raw(request)
        
        # 等待响应（超时 30 秒）
        try:
            response = response_queue.get(timeout=30)
            self._pending_requests.pop(request_id, None)
            
            if "error" in response:
                print(f"   ⚠️ MCP 请求错误 ({method}): {response['error']}")
                return None
            
            return response.get("result")
            
        except queue.Empty:
            self._pending_requests.pop(request_id, None)
            print(f"   ⚠️ MCP 请求超时 ({method})")
            return None
    
    def _send_notification(self, method: str, params: Dict):
        """发送 JSON-RPC 通知（无响应）"""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        self._send_raw(notification)
    
    def _send_raw(self, message: Dict):
        """发送原始消息"""
        if not self._process or not self._process.stdin:
            return
        
        try:
            line = json.dumps(message) + "\n"
            self._process.stdin.write(line)
            self._process.stdin.flush()
        except Exception as e:
            print(f"   ⚠️ MCP 发送失败: {e}")
    
    def _read_loop(self):
        """读取循环"""
        if not self._process or not self._process.stdout:
            return
        
        while self._running:
            try:
                line = self._process.stdout.readline()
                if not line:
                    break
                
                line = line.strip()
                if not line:
                    continue
                
                response = json.loads(line)
                
                # 处理响应
                if "id" in response and response["id"] in self._pending_requests:
                    self._pending_requests[response["id"]].put(response)
                    
            except json.JSONDecodeError:
                continue
            except Exception as e:
                if self._running:
                    print(f"   ⚠️ MCP 读取错误: {e}")
                break
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """调用工具"""
        result = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        
        if result and "content" in result:
            # 提取文本内容
            content_parts = []
            for content in result["content"]:
                if content.get("type") == "text":
                    content_parts.append(content.get("text", ""))
            return "\n".join(content_parts) if content_parts else "工具执行完成（无文本输出）"
        
        return "工具执行失败：无响应"
    
    def stop(self):
        """停止客户端"""
        self._running = False
        
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except:
                self._process.kill()
            self._process = None
        
        if self._read_thread:
            self._read_thread.join(timeout=2)
    
    def is_running(self) -> bool:
        return self._running and self._process and self._process.poll() is None