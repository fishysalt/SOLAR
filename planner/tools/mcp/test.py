import httpx
import json

# 你的 API Key（请使用最新的 Key）
API_KEY = "sk-3748f5a12be9474db8cd9e0ab2ba5287"

# Wan26Media MCP 服务地址
url = "https://dashscope.aliyuncs.com/api/v1/mcps/Wan26Media/mcp"

# 测试初始化请求
body = {
    "jsonrpc": "2.0",
    "id": "test_1",
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {
            "name": "test_client",
            "version": "1.0.0"
        }
    }
}

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}

print("正在测试 Wan26Media MCP 连接...")
print(f"URL: {url}")
print(f"API Key 前10位: {API_KEY[:10]}...")

try:
    response = httpx.post(url, json=body, headers=headers, timeout=30)
    print(f"\n状态码: {response.status_code}")
    print(f"响应头: {dict(response.headers)}")
    print(f"\n响应内容:")
    print(response.text)
    
    if response.status_code == 200:
        print("\n✅ MCP 服务连接成功！")
        # 尝试获取工具列表
        tools_body = {
            "jsonrpc": "2.0",
            "id": "test_2",
            "method": "tools/list",
            "params": {}
        }
        tools_response = httpx.post(url, json=tools_body, headers=headers, timeout=30)
        if tools_response.status_code == 200:
            result = tools_response.json()
            tools = result.get("result", {}).get("tools", [])
            print(f"\n📦 可用工具数量: {len(tools)}")
            for tool in tools:
                print(f"  - {tool.get('name')}: {tool.get('description', '')[:50]}")
    else:
        print(f"\n❌ 连接失败，状态码 {response.status_code}")
        print("可能原因：")
        print("1. API Key 没有 Wan26Media 服务权限")
        print("2. 服务尚未开通或处于开通中状态")
        print("3. 需要等待几分钟再试")
        
except httpx.TimeoutException:
    print("\n❌ 请求超时")
except Exception as e:
    print(f"\n❌ 错误: {e}")