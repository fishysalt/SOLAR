"""统一工具注册器 - 支持 MCP Server 配置与工具分离，并规范化 MCP schema"""

import json
import time
import threading
import pymysql
import importlib
import inspect
import asyncio
import os
import re
from typing import Optional, Dict, Any, List, Callable, Tuple
from .models import ToolInfo, ToolType


class ToolRegistry:
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

        self._tools: Dict[str, ToolInfo] = {}
        self._agent_tools: Dict[str, List[str]] = {}
        self._lock = threading.Lock()
        self._mysql_config = None
        self._mcp_clients: Dict[str, Any] = {}

        print("🔧 统一工具注册器已初始化（配置-工具分离版）")

    def init_mysql(self, mysql_config: Dict):
        self._mysql_config = mysql_config
        self._ensure_tables()

    def _get_mysql_connection(self):
        if not self._mysql_config:
            raise Exception("MySQL配置未初始化")
        return pymysql.connect(
            host=self._mysql_config.get("host", "localhost"),
            port=self._mysql_config.get("port", 3306),
            user=self._mysql_config.get("user", "solar_ma"),
            password=self._mysql_config.get("password", ""),
            database=self._mysql_config.get("database", "solar_ma"),
            charset='utf8mb4',
            autocommit=True
        )

    def _ensure_tables(self):
        try:
            conn = self._get_mysql_connection()
            cursor = conn.cursor()

            # builtin_agent_tools
            cursor.execute("SHOW TABLES LIKE 'builtin_agent_tools'")
            if not cursor.fetchone():
                cursor.execute("""... (建表语句略，保持原样) ...""")

            # mcp_server_configs
            cursor.execute("SHOW TABLES LIKE 'mcp_server_configs'")
            if not cursor.fetchone():
                cursor.execute("""... (建表语句略，保持原样) ...""")

            # mcp_agent_tools
            cursor.execute("SHOW TABLES LIKE 'mcp_agent_tools'")
            if not cursor.fetchone():
                cursor.execute("""... (建表语句略，保持原样) ...""")

            cursor.close()
            conn.close()
            print("✅ 工具表已就绪")
        except Exception as e:
            print(f"⚠️ 表检查失败: {e}")

    # ========== 规范化 schema ==========

    def _normalize_schema(self, schema: Dict) -> Dict:
        """
        递归规范化 JSON Schema，移除 anyOf/oneOf/allOf 等复杂关键字，
        将非标准类型转换为标准类型，确保每个字段有 type 且为基本类型。
        """
        if not isinstance(schema, dict):
            return {"type": "object", "properties": {}}

        # 处理 anyOf/oneOf/allOf：取第一个有效的 schema
        for key in ["anyOf", "oneOf", "allOf"]:
            if key in schema and isinstance(schema[key], list) and len(schema[key]) > 0:
                first = schema[key][0]
                if isinstance(first, dict):
                    return self._normalize_schema(first)
                else:
                    return {"type": "object", "properties": {}}

        # 复制一份，避免修改原数据
        new_schema = schema.copy()

        # 处理 type 字段
        if "type" in new_schema:
            t = new_schema["type"]
            # 如果 type 是列表，取第一个非 null 类型
            if isinstance(t, list):
                types = [x for x in t if x != "null"]
                if types:
                    new_schema["type"] = types[0]
                else:
                    new_schema["type"] = "object"
            # 如果 type 是字符串，映射非标准类型
            elif isinstance(t, str):
                if t.lower() == "bool":
                    new_schema["type"] = "boolean"
                # 可扩展其他映射
        else:
            # 如果没有 type，推断为 object
            new_schema["type"] = "object"

        # 递归处理 properties
        if "properties" in new_schema and isinstance(new_schema["properties"], dict):
            for prop_name, prop_schema in new_schema["properties"].items():
                if isinstance(prop_schema, dict):
                    new_schema["properties"][prop_name] = self._normalize_schema(prop_schema)
                elif isinstance(prop_schema, bool):
                    # 如果 prop_schema 是 bool，转换为 object
                    new_schema["properties"][prop_name] = {"type": "object", "properties": {}}
                else:
                    new_schema["properties"][prop_name] = {"type": "object", "properties": {}}

        # 处理 items（数组类型）
        if new_schema.get("type") == "array" and "items" in new_schema:
            if isinstance(new_schema["items"], dict):
                new_schema["items"] = self._normalize_schema(new_schema["items"])
            elif isinstance(new_schema["items"], bool):
                new_schema["items"] = {"type": "object", "properties": {}}
            else:
                new_schema["items"] = {"type": "object", "properties": {}}

        # 移除复杂关键字
        for key in ["anyOf", "oneOf", "allOf", "not", "if", "then", "else"]:
            new_schema.pop(key, None)

        # 如果是 object，确保有 properties
        if new_schema.get("type") == "object" and "properties" not in new_schema:
            new_schema["properties"] = {}

        # 如果是基本类型，移除 properties（如果有）
        if new_schema.get("type") in ["string", "number", "integer", "boolean", "array"]:
            new_schema.pop("properties", None)

        return new_schema
    # ========== 核心加载方法 ==========

    def load_tools_for_agent(self, agent_name: str) -> int:
        count = self._load_builtin_tools(agent_name) + self._load_mcp_tools(agent_name)
        print(f"📋 Agent '{agent_name}' 加载了 {count} 个工具")
        return count

    def _load_builtin_tools(self, agent_name: str) -> int:
        try:
            conn = self._get_mysql_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute("""
                SELECT * FROM builtin_agent_tools
                WHERE agent_name = %s AND is_available = TRUE
            """, (agent_name,))
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"⚠️ 加载内置工具失败: {e}")
            return 0

        count = 0
        for row in rows:
            try:
                module = importlib.import_module(row['module_name'])
                tool_dict = getattr(module, row['object_name'], None)
                if not tool_dict or not isinstance(tool_dict, dict):
                    print(f"⚠️ 无法加载工具 {row['tool_name']}: 对象不存在或非字典")
                    continue

                tool_info = ToolInfo(
                    name=row['tool_name'],
                    description=row['description'] or tool_dict.get('description', ''),
                    func=tool_dict['func'],
                    parameters=row['parameters'] or tool_dict.get('parameters', {}),
                    tool_type=ToolType.BUILTIN,
                    estimated_wait_time=row.get('estimated_wait_time', 0.0),
                    is_async=inspect.iscoroutinefunction(tool_dict['func']),
                    last_execution_time=0.0,
                    execution_count=row.get('execution_count', 0),
                    success_count=row.get('success_count', 0),
                    success_rate=row.get('success_rate', 0.0),
                    is_available=row.get('is_available', True),
                    timeout=row.get('timeout', 240),
                    last_error=row.get('last_error'),
                    extra_metadata=row.get('extra_metadata', {})
                )
                with self._lock:
                    self._tools[tool_info.name] = tool_info
                    if agent_name not in self._agent_tools:
                        self._agent_tools[agent_name] = []
                    if tool_info.name not in self._agent_tools[agent_name]:
                        self._agent_tools[agent_name].append(tool_info.name)
                count += 1
                print(f"   🔧 内置: {tool_info.name}")
            except Exception as e:
                print(f"⚠️ 注册内置工具 {row['tool_name']} 失败: {e}")
        return count

    def _load_mcp_tools(self, agent_name: str) -> int:
        # 1. 查询已有工具
        try:
            conn = self._get_mysql_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute("""
                SELECT * FROM mcp_agent_tools
                WHERE agent_name = %s AND is_available = TRUE
            """, (agent_name,))
            existing_tools = cursor.fetchall()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"⚠️ 查询 MCP 工具失败: {e}")
            return 0

        if existing_tools:
            return self._register_mcp_tools_from_rows(agent_name, existing_tools)

        # 2. 查询 Server 配置
        try:
            conn = self._get_mysql_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute("""
                SELECT * FROM mcp_server_configs
                WHERE agent_name = %s AND is_enabled = TRUE
            """, (agent_name,))
            configs = cursor.fetchall()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"⚠️ 查询 MCP Server 配置失败: {e}")
            return 0

        if not configs:
            print(f"   ℹ️ Agent '{agent_name}' 没有配置 MCP Server")
            return 0

        # 3. 发现并写入工具
        total_discovered = 0
        for config in configs:
            try:
                if config.get('args') and isinstance(config['args'], str):
                    config['args'] = json.loads(config['args'])
                if config.get('headers') and isinstance(config['headers'], str):
                    config['headers'] = json.loads(config['headers'])
                if config.get('env') and isinstance(config['env'], str):
                    config['env'] = json.loads(config['env'])
                if config.get('extra_metadata') and isinstance(config['extra_metadata'], str):
                    config['extra_metadata'] = json.loads(config['extra_metadata'])

                tools = self._discover_mcp_tools(config)
                if not tools:
                    print(f"   ⚠️ 未发现工具: {config['server_name']}")
                    continue

                self._save_discovered_mcp_tools(agent_name, config, tools)
                total_discovered += len(tools)
                print(f"   ✅ 发现并写入 {len(tools)} 个工具 (server: {config['server_name']})")

            except Exception as e:
                print(f"⚠️ 处理 MCP Server {config.get('server_name')} 失败: {e}")

        if total_discovered == 0:
            return 0

        # 4. 重新加载
        try:
            conn = self._get_mysql_connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            cursor.execute("""
                SELECT * FROM mcp_agent_tools
                WHERE agent_name = %s AND is_available = TRUE
            """, (agent_name,))
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            return self._register_mcp_tools_from_rows(agent_name, rows)
        except Exception as e:
            print(f"⚠️ 重新加载 MCP 工具失败: {e}")
            return 0

    def _discover_mcp_tools(self, config: Dict) -> List:
        server_type = config.get('server_type')
        server_name = config['server_name']

        if server_type == 'http':
            from shared.tools.mcp.http_client import HTTPMCPClient
            headers = config.get('headers', {})
            def replace_env(match):
                return os.environ.get(match.group(1), '')
            for key, value in headers.items():
                if isinstance(value, str) and '${' in value:
                    headers[key] = re.sub(r'\${([^}]+)}', replace_env, value)

            client = HTTPMCPClient(
                server_name=server_name,
                base_url=config['base_url'],
                headers=headers
            )
            success = client.initialize()
            if success:
                self._mcp_clients[server_name] = client
                return client.tools
            else:
                print(f"   ⚠️ HTTP MCP Server 连接失败: {server_name}")
                return []

        elif server_type == 'stdio':
            from shared.tools.mcp.client import MCPClient
            env = config.get('env', {})
            merged_env = {**os.environ, **env}
            client = MCPClient(
                server_name=server_name,
                command=config['command'],
                args=config.get('args', []),
                env=merged_env
            )
            success = client.start()
            if success:
                self._mcp_clients[server_name] = client
                return client.tools
            else:
                print(f"   ⚠️ stdio MCP Server 启动失败: {server_name}")
                return []
        else:
            return []

    def _save_discovered_mcp_tools(self, agent_name: str, server_config: Dict, tools: List):
        conn = self._get_mysql_connection()
        cursor = conn.cursor()

        for tool in tools:
            cursor.execute(
                "SELECT id FROM mcp_agent_tools WHERE agent_name = %s AND tool_name = %s",
                (agent_name, tool.name)
            )
            if cursor.fetchone():
                continue

            # 规范化 schema
            normalized_schema = self._normalize_schema(tool.input_schema)

            cursor.execute("""
                INSERT INTO mcp_agent_tools
                (agent_name, server_name, tool_name, description, parameters, timeout)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                agent_name,
                server_config['server_name'],
                tool.name,
                tool.description,
                json.dumps(normalized_schema),
                server_config.get('timeout', 240)
            ))

        conn.commit()
        cursor.close()
        conn.close()

    def _register_mcp_tools_from_rows(self, agent_name: str, rows: List[Dict]) -> int:
        count = 0
        for row in rows:
            try:
                if row.get('parameters') and isinstance(row['parameters'], str):
                    row['parameters'] = json.loads(row['parameters'])
                if row.get('extra_metadata') and isinstance(row['extra_metadata'], str):
                    row['extra_metadata'] = json.loads(row['extra_metadata'])

                # 再次规范化（数据库存储时已规范化，但以防万一）
                params = self._normalize_schema(row.get('parameters', {}))

                wrapper = self._create_mcp_call_wrapper(row)
                tool_info = ToolInfo(
                    name=row['tool_name'],
                    description=row.get('description', ''),
                    func=wrapper,
                    parameters=params,
                    tool_type=ToolType.MCP,
                    estimated_wait_time=row.get('estimated_wait_time', 0.0),
                    is_async=True,
                    last_execution_time=0.0,
                    execution_count=row.get('execution_count', 0),
                    success_count=row.get('success_count', 0),
                    success_rate=row.get('success_rate', 0.0),
                    is_available=row.get('is_available', True),
                    timeout=row.get('timeout', 240),
                    last_error=row.get('last_error'),
                    extra_metadata=row.get('extra_metadata', {})
                )
                with self._lock:
                    self._tools[tool_info.name] = tool_info
                    if agent_name not in self._agent_tools:
                        self._agent_tools[agent_name] = []
                    if tool_info.name not in self._agent_tools[agent_name]:
                        self._agent_tools[agent_name].append(tool_info.name)
                count += 1
                print(f"   🔌 MCP: {tool_info.name} (server: {row['server_name']})")
            except Exception as e:
                print(f"⚠️ 注册 MCP 工具 {row.get('tool_name')} 失败: {e}")
        return count

    def _create_mcp_call_wrapper(self, row: Dict) -> Callable:
        server_name = row['server_name']
        tool_name = row['tool_name']

        async def wrapper(**kwargs):
            client = self._mcp_clients.get(server_name)
            if client is None:
                try:
                    conn = self._get_mysql_connection()
                    cursor = conn.cursor(pymysql.cursors.DictCursor)
                    cursor.execute("""
                        SELECT * FROM mcp_server_configs
                        WHERE server_name = %s AND is_enabled = TRUE
                    """, (server_name,))
                    config = cursor.fetchone()
                    cursor.close()
                    conn.close()
                    if not config:
                        return f"❌ Server 配置不存在: {server_name}"
                    if config.get('args') and isinstance(config['args'], str):
                        config['args'] = json.loads(config['args'])
                    if config.get('headers') and isinstance(config['headers'], str):
                        config['headers'] = json.loads(config['headers'])
                    if config.get('env') and isinstance(config['env'], str):
                        config['env'] = json.loads(config['env'])

                    tools = self._discover_mcp_tools(config)
                    if not tools:
                        return f"❌ 无法连接 MCP Server: {server_name}"
                    client = self._mcp_clients.get(server_name)
                    if client is None:
                        return f"❌ MCP Server 不可用: {server_name}"
                except Exception as e:
                    return f"❌ 重连 MCP Server 失败: {str(e)}"

            try:
                return client.call_tool(tool_name, kwargs)
            except Exception as e:
                return f"❌ MCP 工具调用失败: {str(e)}"

        return wrapper

    # ========== 执行工具等（以下保持不变） ==========

    async def execute(self, name: str, **kwargs) -> Tuple[Any, float]:
        tool = self.get_tool(name)
        if not tool:
            return f"❌ 工具不存在: {name}", 0.0

        start_time = time.time()
        success = False
        error_msg = None
        result = None
        try:
            if tool.is_async:
                result = await tool.func(**kwargs)
            else:
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, tool.func, **kwargs)
            success = True
        except Exception as e:
            error_msg = str(e)
            result = f"❌ 工具执行失败: {error_msg}"
        finally:
            elapsed = time.time() - start_time
            asyncio.create_task(self._update_tool_after_execution(name, elapsed, success, error_msg))
        return result, elapsed

    async def _update_tool_after_execution(self, tool_name: str, elapsed: float, success: bool, error_msg: str = None):
        with self._lock:
            tool = self._tools.get(tool_name)
            if not tool:
                return
            tool.execution_count += 1
            if success:
                tool.success_count += 1
            tool.success_rate = tool.success_count / tool.execution_count if tool.execution_count > 0 else 0.0
            if tool.execution_count == 1:
                tool.estimated_wait_time = elapsed
            else:
                tool.estimated_wait_time = tool.estimated_wait_time * 0.9 + elapsed * 0.1
            tool.last_execution_time = elapsed
            tool.last_error = error_msg if error_msg else None
        await asyncio.to_thread(self._update_db_stats, tool_name, tool.estimated_wait_time,
                                tool.execution_count, tool.success_count, tool.success_rate, error_msg)

    def _update_db_stats(self, tool_name: str, estimated_wait: float, exec_count: int,
                         success_count: int, success_rate: float, error_msg: str):
        try:
            conn = self._get_mysql_connection()
            cursor = conn.cursor()
            agent_names = []
            with self._lock:
                for ag, tools in self._agent_tools.items():
                    if tool_name in tools:
                        agent_names.append(ag)
            if not agent_names:
                return
            agent_name = agent_names[0]

            cursor.execute("""
                UPDATE builtin_agent_tools 
                SET estimated_wait_time = %s, execution_count = %s, success_count = %s, 
                    success_rate = %s, last_error = %s, updated_at = NOW()
                WHERE agent_name = %s AND tool_name = %s
            """, (estimated_wait, exec_count, success_count, success_rate, error_msg, agent_name, tool_name))
            if cursor.rowcount == 0:
                cursor.execute("""
                    UPDATE mcp_agent_tools 
                    SET estimated_wait_time = %s, execution_count = %s, success_count = %s, 
                        success_rate = %s, last_error = %s, updated_at = NOW()
                    WHERE agent_name = %s AND tool_name = %s
                """, (estimated_wait, exec_count, success_count, success_rate, error_msg, agent_name, tool_name))
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"⚠️ 更新工具统计失败: {e}")

    def get_tool(self, name: str) -> Optional[ToolInfo]:
        with self._lock:
            return self._tools.get(name)

    def get_agent_tools(self, agent_name: str) -> List[ToolInfo]:
        with self._lock:
            tool_names = self._agent_tools.get(agent_name, [])
            return [self._tools[name] for name in tool_names if name in self._tools]

    def get_schemas(self, agent_name: str = None) -> List[dict]:
        with self._lock:
            if agent_name:
                tool_names = self._agent_tools.get(agent_name, [])
                tools = [self._tools[name] for name in tool_names if name in self._tools]
            else:
                tools = list(self._tools.values())
            return [t.to_schema() for t in tools if t.is_available]

    def list_tools(self, agent_name: str = None) -> List[str]:
        with self._lock:
            if agent_name:
                return self._agent_tools.get(agent_name, []).copy()
            return list(self._tools.keys())

    def get_wait_time(self, tool_name: str) -> float:
        tool = self.get_tool(tool_name)
        return tool.estimated_wait_time if tool else 0.0

    def is_long_tool(self, tool_name: str, threshold: float = 2.0) -> bool:
        tool = self.get_tool(tool_name)
        return tool.estimated_wait_time > threshold if tool else False

    def get_tool_metrics(self, tool_name: str) -> Dict:
        tool = self.get_tool(tool_name)
        if not tool:
            return {}
        return {
            "estimated_wait_time": tool.estimated_wait_time,
            "last_execution_time": tool.last_execution_time,
            "execution_count": tool.execution_count,
            "success_count": tool.success_count,
            "success_rate": tool.success_rate,
            "is_async": tool.is_async,
            "last_error": tool.last_error
        }


_registry = None

def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry