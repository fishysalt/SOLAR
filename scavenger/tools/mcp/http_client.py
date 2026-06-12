"""MCP HTTP 客户端 - 支持 streamableHttp 协议的 MCP Server"""

import httpx
import json
import uuid
import base64
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass


@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str


class HTTPMCPClient:
    """
    MCP HTTP 客户端
    通过 streamableHttp 协议连接 MCP Server
    """
    
    def __init__(self, server_name: str, base_url: str, headers: Dict[str, str]):
        self.server_name = server_name
        self.base_url = base_url.rstrip('/')
        self.headers = headers
        self._client: Optional[httpx.Client] = None
        self._initialized = False
        self.tools: List[MCPTool] = []
    
    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=120.0)  # 视频生成需要更长时间
        return self._client
    
    def _convert_image_paths_to_base64(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        递归查找参数中的本地图片路径，转换为 Base64 格式
        """
        if not isinstance(arguments, dict):
            return arguments
        
        converted = {}
        for key, value in arguments.items():
            # 检查是否是图片路径参数（支持多种命名）
            is_image_param = key.lower() in [
                'img_url', 'image', 'reference_image', 
                'image_path', 'image_url', 'img',
                'source_image', 'input_image', 'first_frame'
            ]
            
            if is_image_param and isinstance(value, str):
                # 检查是否是本地文件路径
                path = Path(value)
                if path.exists() and path.is_file():
                    # 根据扩展名确定 MIME 类型
                    ext = path.suffix.lower()
                    if ext in ['.jpg', '.jpeg']:
                        mime_type = "image/jpeg"
                    elif ext == '.png':
                        mime_type = "image/png"
                    elif ext == '.webp':
                        mime_type = "image/webp"
                    else:
                        mime_type = "image/png"
                    
                    try:
                        with open(path, 'rb') as f:
                            img_data = base64.b64encode(f.read()).decode('utf-8')
                        base64_str = f"data:{mime_type};base64,{img_data}"
                        converted[key] = base64_str
                        print(f"   🔄 [MCP] 已转换本地图片: {path.name} ({len(img_data)} bytes) -> Base64")
                    except Exception as e:
                        print(f"   ⚠️ [MCP] 转换图片失败: {path.name} -> {e}")
                        converted[key] = value
                else:
                    converted[key] = value
            elif isinstance(value, dict):
                converted[key] = self._convert_image_paths_to_base64(value)
            elif isinstance(value, list):
                converted[key] = [
                    self._convert_image_paths_to_base64(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                converted[key] = value
        
        return converted
    
    def _send_request(self, method: str, params: Dict) -> Optional[Dict]:
        """发送 JSON-RPC 请求"""
        client = self._get_client()
        request_id = str(uuid.uuid4())
        
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params
        }
        
        try:
            response = client.post(
                self.base_url,
                headers=self.headers,
                json=request
            )
            response.raise_for_status()
            result = response.json()
            
            if "error" in result:
                print(f"   ⚠️ MCP HTTP 错误 ({self.server_name}): {result['error']}")
                return None
            
            return result.get("result")
            
        except httpx.HTTPStatusError as e:
            print(f"   ⚠️ MCP HTTP 状态错误 ({self.server_name}): {e.response.status_code}")
            return None
        except Exception as e:
            print(f"   ⚠️ MCP HTTP 请求失败 ({self.server_name}): {e}")
            return None
    
    def initialize(self) -> bool:
        """初始化连接"""
        result = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "scavenger-mcp-client",
                "version": "1.0.0"
            }
        })
        
        if result and "protocolVersion" in result:
            self._initialized = True
            # 发送 initialized 通知（不需要响应）
            try:
                self._get_client().post(
                    self.base_url,
                    headers=self.headers,
                    json={
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                        "params": {}
                    }
                )
            except:
                pass
            self._discover_tools()
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
            
            print(f"   ✅ MCP HTTP 发现 {len(self.tools)} 个工具")
            for t in self.tools:
                print(f"      - {t.name}")
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        print(f"   🔍 [MCP] 原始参数: {arguments}")
    
        # 转换参数中的本地图片路径
        converted_args = self._convert_image_paths_to_base64(arguments)
    
        print(f"   🔍 [MCP] 转换后参数: {converted_args}")
        result = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": converted_args
        })
        
        if result and "content" in result:
            content_parts = []
            for content in result["content"]:
                if content.get("type") == "text":
                    content_parts.append(content.get("text", ""))
                elif content.get("type") == "image":
                    content_parts.append(f"[图片: {content.get('data', '')[:50]}...]")
            return "\n".join(content_parts) if content_parts else "工具执行完成"
        
        return "工具执行失败：无响应"
    
    def close(self):
        if self._client:
            self._client.close()
            self._client = None
    
    def is_running(self) -> bool:
        return self._initialized