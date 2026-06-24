"""MCP 协议客户端 - 实现 JSON-RPC 通信"""

import json
import subprocess
import threading
import queue
import time
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from dotenv import load_dotenv
from .mcp_logger import get_mcp_logger

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
        
        # ========== 标记是否为 claudecode ==========
        self._is_claude_code = self.server_name in ["claude-code", "ClaudeCode"]
        # ==========================================
    
    def _load_env_file(self):
        """加载 .env 文件"""
        current_dir = Path(__file__).parent
        agent_root = current_dir.parent.parent
        env_path = agent_root / ".env"
        
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
            print(f"   📝 [MCPClient] 已加载环境变量: {env_path}")
    
    def start(self) -> bool:
        """启动 MCP Server 子进程"""
        try:
            self._load_env_file()
            env = {**os.environ, **self.env}
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            
            print(f"   🚀 启动 {self.server_name}: {self.command} {' '.join(self.args)}")
            
            self._process = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,
                encoding='utf-8',
                errors='replace'
            )
            
            self._running = True
            
            # ========== 普通读取模式 ==========
            self._read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._read_thread.start()
            # ==================================
            
            if not self._initialize():
                return False
            
            self._discover_tools()
            print(f"   ✅ MCP Client 已连接: {self.server_name} ({len(self.tools)} 个工具)")
            return True
            
        except Exception as e:
            print(f"   ❌ MCP Client 启动失败 ({self.server_name}): {e}")
            return False
    
    def _initialize(self) -> bool:
        """发送初始化请求"""
        result = self._send_request("initialize", {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {
                "name": "agent-mcp-client",
                "version": "1.0.0"
            }
        })
        
        if result and "protocolVersion" in result:
            self._initialized = True
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
        """发送 JSON-RPC 请求并等待响应（带日志记录）"""
        import time
        
        logger = get_mcp_logger()
        
        self._request_counter += 1
        request_id = f"{self.server_name}_{self._request_counter}"
        
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }
        
        # ========== 记录调用开始 ==========
        if method == "tools/call":
            tool_name = params.get("name", "unknown")
            tool_args = params.get("arguments", {})
            call_id = logger.log_call(
                server_name=self.server_name,
                tool_name=tool_name,
                arguments=tool_args,
                request_id=request_id,
                raw_request=json.dumps(request, ensure_ascii=False)
            )
        else:
            call_id = None
        # ===================================
        
        start_time = time.time()
        
        response_queue = queue.Queue()
        self._pending_requests[request_id] = response_queue
        
        self._send_raw(request)
        
        try:
            response = response_queue.get(timeout=120)
            self._pending_requests.pop(request_id, None)
            
            duration = time.time() - start_time
            
            # ========== 记录调用完成 ==========
            if call_id:
                logger.log_response(
                    call_id=call_id,
                    response=response.get("result") if response else None,
                    raw_response=json.dumps(response, ensure_ascii=False) if response else None,
                    error=response.get("error") if response else None,
                    duration=duration
                )
            # ===================================
            
            if "error" in response:
                print(f"   ⚠️ MCP 请求错误 ({method}): {response['error']}")
                return None
            
            return response.get("result")
            
        except queue.Empty:
            duration = time.time() - start_time
            
            # ========== 记录超时 ==========
            if call_id:
                logger.log_timeout(call_id=call_id, timeout=duration)
            # ===================================
            
            self._pending_requests.pop(request_id, None)
            print(f"   ⚠️ MCP 请求超时 ({method}, {duration:.2f}s)")
            return None
    def _send_notification(self, method: str, params: Dict):
        """发送 JSON-RPC 通知"""
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
            line = json.dumps(message, ensure_ascii=False) + "\n"
            self._process.stdin.write(line)
            self._process.stdin.flush()
        except Exception as e:
            print(f"   ⚠️ MCP 发送失败: {e}")
    
    def _read_loop(self):
        """普通读取循环"""
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
                
                try:
                    response = json.loads(line)
                    if "id" in response and response["id"] in self._pending_requests:
                        self._pending_requests[response["id"]].put(response)
                except json.JSONDecodeError:
                    if line.startswith('{'):
                        continue
                    print(f"   [MCP:{self.server_name}] {line[:200]}")
                    
            except Exception as e:
                if self._running:
                    print(f"   ⚠️ MCP 读取错误: {e}")
                break
    
    # ========== claudecode 专用：持续读取 + 每次重启 ==========
    def _call_claude_code_once(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        每次调用 claudecode 都启动新进程，同时持续读取 stdout
        避免长连接死锁 + 缓冲区满问题
        """
        import subprocess
        import json
        import uuid
        import threading
        
        print(f"   🔄 [ClaudeCode] 启动一次性调用: {tool_name}")
        
        # 构建请求
        request_id = str(uuid.uuid4())
        
        init_request = {
            "jsonrpc": "2.0",
            "id": f"init_{request_id}",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agent", "version": "1.0"}
            }
        }
        
        tool_request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        input_data = json.dumps(init_request) + "\n" + json.dumps(tool_request) + "\n"
        
        # 环境变量
        env = {**os.environ, **self.env}
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["NO_COLOR"] = "1"
        env["RUST_LOG"] = "warn"
        
        start_time = time.time()
        output_buffer = []
        process_done = threading.Event()
        
        try:
            proc = subprocess.Popen(
                [self.command] + self.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                encoding='utf-8',
                errors='replace'
            )
            
            # ========== 启动持续读取线程 ==========
            def read_continuously():
                while process_done.is_set() == False:
                    try:
                        line = proc.stdout.readline()
                        if not line:
                            break
                        output_buffer.append(line)
                    except:
                        break
            
            reader = threading.Thread(target=read_continuously, daemon=True)
            reader.start()
            # =====================================
            
            # 发送请求
            proc.stdin.write(input_data)
            proc.stdin.flush()
            proc.stdin.close()
            
            # 等待进程结束（超时 60 秒）
            try:
                proc.wait(timeout=60)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            
            process_done.set()
            reader.join(timeout=2)
            
            elapsed = time.time() - start_time
            output = "".join(output_buffer)
            
            print(f"   ✅ [ClaudeCode] 一次性调用完成 ({elapsed:.2f}s, {len(output)} bytes)")
            
            # 解析响应
            for line in output.split('\n'):
                line = line.strip()
                if not line:
                    continue
                try:
                    response = json.loads(line)
                    if response.get("id") == request_id:
                        result = response.get("result", {})
                        content = result.get("content", [])
                        if content and len(content) > 0:
                            return content[0].get("text", "工具执行完成")
                        return "工具执行完成"
                except:
                    continue
            
            return "工具执行失败：无响应"
            
        except Exception as e:
            print(f"   ❌ [ClaudeCode] 失败: {e}")
            return f"工具执行失败: {str(e)}"
    # ===========================================================
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        调用工具
        如果是 claudecode，使用持续读取 + 每次重启模式
        """
        # ========== claudecode 特殊处理 ==========
        if self._is_claude_code:
            return self._call_claude_code_once(tool_name, arguments)
        # =========================================
        
        # 普通模式
        result = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
        
        if result and "content" in result:
            content_parts = []
            for content in result["content"]:
                if content.get("type") == "text":
                    content_parts.append(content.get("text", ""))
            return "\n".join(content_parts) if content_parts else "工具执行完成"
        
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