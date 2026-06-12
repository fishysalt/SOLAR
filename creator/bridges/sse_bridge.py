#!/usr/bin/env python
"""通用 SSE → stdio 桥接器

用法:
    python sse_bridge.py --url <SSE_URL> [--name <NAME>] [--header <HEADER>]

示例:
    python sse_bridge.py --url https://dashscope.aliyuncs.com/api/v1/mcps/QuickChart/sse --name QuickChart
"""

import subprocess
import argparse
import os
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="通用 SSE → stdio 桥接器")
    parser.add_argument("--url", required=True, help="SSE 服务 URL")
    parser.add_argument("--name", default="sse-service", help="服务名称（用于日志）")
    parser.add_argument("--header", action="append", help="自定义请求头（格式: Key: Value）")
    
    args = parser.parse_args()
    
    # 构建基础命令
    cmd = ["mcp-stdio-bridge", "--sse-url", args.url]
    
    # 添加自定义请求头
    if args.header:
        for h in args.header:
            cmd.extend(["--header", h])
    
    # 如果没有自定义认证头，尝试从环境变量添加
    has_auth = any(h.startswith("Authorization:") for h in (args.header or []))
    if not has_auth:
        api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        if api_key:
            cmd.extend(["--header", f"Authorization: Bearer {api_key}"])
            print(f"🔑 [{args.name}] 已添加 Authorization 头")
    
    print(f"🔌 [{args.name}] 启动 SSE 桥接")
    print(f"   URL: {args.url}")
    print(f"   命令: {' '.join(cmd[:3])}...")
    
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print(f"\n🛑 [{args.name}] 桥接已停止")
    except Exception as e:
        print(f"❌ [{args.name}] 桥接失败: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())