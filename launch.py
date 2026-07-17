#!/usr/bin/env python
"""SOLAR_MA 统一启动脚本 - 支持主Agent和子Agent的双进程启动"""

import sys
import subprocess
import argparse
import time
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


# ========== 端口配置 ==========

# 主Agent
CONDUCTOR_API_PORT = 7860
CONDUCTOR_UI_PORT = 7960

# 子Agent
AGENT_PORTS = {
    "creator": {"api": 7861, "ui": 7961},
    "scavenger": {"api": 7862, "ui": 7962},
    "engineer": {"api": 7863, "ui": 7963},
}


# ========== 启动函数 ==========

def start_agent(agent_name: str, start_api: bool = True, start_ui: bool = True):
    """启动单个Agent的两个服务"""
    if agent_name not in AGENT_PORTS:
        print(f"❌ 未知Agent: {agent_name}")
        return []

    ports = AGENT_PORTS[agent_name]
    processes = []

    # 启动 FastAPI
    if start_api:
        print(f"📡 启动 {agent_name} FastAPI (端口 {ports['api']})...")
        api_proc = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                f"{agent_name}.api:app",
                "--host", "0.0.0.0",
                "--port", str(ports["api"]),
                "--reload"
            ],
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "AGENT_NAME": agent_name}
        )
        processes.append((f"{agent_name}-api", api_proc))
        time.sleep(1.5)

    # 启动 NiceGUI UI
    if start_ui:
        print(f"🖥️ 启动 {agent_name} UI (端口 {ports['ui']})...")
        ui_proc = subprocess.Popen(
            [
                sys.executable, "-m", f"{agent_name}.ui.app"
            ],
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "AGENT_NAME": agent_name}
        )
        processes.append((f"{agent_name}-ui", ui_proc))
        time.sleep(1.0)

    return processes


def start_conductor(start_api: bool = True, start_ui: bool = True):
    """启动主Agent Conductor"""
    processes = []

    # 启动 FastAPI
    if start_api:
        print(f"📡 启动 Conductor FastAPI (端口 {CONDUCTOR_API_PORT})...")
        api_proc = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "conductor.api:app",
                "--host", "0.0.0.0",
                "--port", str(CONDUCTOR_API_PORT),
                "--reload"
            ],
            cwd=str(PROJECT_ROOT)
        )
        processes.append(("conductor-api", api_proc))
        time.sleep(2)

    # 启动 NiceGUI UI
    if start_ui:
        print(f"🖥️ 启动 Conductor UI (端口 {CONDUCTOR_UI_PORT})...")
        ui_proc = subprocess.Popen(
            [
                sys.executable, "-m", "conductor.ui.app"
            ],
            cwd=str(PROJECT_ROOT)
        )
        processes.append(("conductor-ui", ui_proc))
        time.sleep(1.5)

    return processes


def stop_processes(processes):
    """停止所有进程"""
    print("\n🛑 正在停止所有服务...")
    for name, proc in processes:
        try:
            proc.terminate()
            print(f"   ⏹️ 停止 {name}")
        except:
            pass
    time.sleep(1)
    for name, proc in processes:
        try:
            proc.kill()
        except:
            pass
    print("✅ 已停止")


def print_summary(processes):
    """打印启动摘要"""
    print("\n" + "=" * 60)
    print("✅ 服务启动完成")
    print("=" * 60)
    print("📡 Conductor API:  http://localhost:7860")
    print("🖥️  Conductor UI:   http://localhost:7960")
    print("")
    print("📡 Creator API:    http://localhost:7861")
    print("🖥️  Creator UI:     http://localhost:7961")
    print("")
    print("📡 Scavenger API:  http://localhost:7862")
    print("🖥️  Scavenger UI:   http://localhost:7962")
    print("")
    print("📡 Engineer API:   http://localhost:7863")
    print("🖥️  Engineer UI:    http://localhost:7963")
    print("=" * 60)
    print("💡 按 Ctrl+C 停止所有服务")
    print("=" * 60)


# ========== 主逻辑 ==========

def main():
    parser = argparse.ArgumentParser(description="SOLAR_MA 启动脚本")
    parser.add_argument("--all", action="store_true", help="启动所有Agent（Conductor + Creator + Scavenger + Engineer）")
    parser.add_argument("--conductor", action="store_true", help="仅启动 Conductor")
    parser.add_argument("--creator", action="store_true", help="仅启动 Creator")
    parser.add_argument("--scavenger", action="store_true", help="仅启动 Scavenger")
    parser.add_argument("--engineer", action="store_true", help="仅启动 Engineer")
    parser.add_argument("--api-only", action="store_true", help="只启动 FastAPI，不启动 UI")
    parser.add_argument("--ui-only", action="store_true", help="只启动 UI，不启动 FastAPI")
    parser.add_argument("--list", action="store_true", help="列出所有服务")

    args = parser.parse_args()

    if args.list:
        print("📋 可用服务:")
        print("   🎵 conductor  - 主控Agent (API: 7860, UI: 7960)")
        print("   ✨ creator    - 内容生成 (API: 7861, UI: 7961)")
        print("   🔍 scavenger  - 信息收集 (API: 7862, UI: 7962)")
        print("   🔧 engineer   - 自进化引擎 (API: 7863, UI: 7963)")
        return

    # 确定启动哪些Agent
    agents_to_start = []
    start_api = not args.ui_only
    start_ui = not args.api_only

    if args.all:
        agents_to_start = ["conductor", "creator", "scavenger", "engineer"]
    elif args.conductor:
        agents_to_start = ["conductor"]
    elif args.creator:
        agents_to_start = ["creator"]
    elif args.scavenger:
        agents_to_start = ["scavenger"]
    elif args.engineer:
        agents_to_start = ["engineer"]
    else:
        # 默认只启动 Conductor
        agents_to_start = ["conductor"]

    all_processes = []

    print("=" * 60)
    print("🚀 SOLAR_MA 启动器")
    print("=" * 60)

    try:
        # 启动 Conductor
        if "conductor" in agents_to_start:
            procs = start_conductor(start_api=start_api, start_ui=start_ui)
            all_processes.extend(procs)

        # 启动子Agent
        for agent in agents_to_start:
            if agent != "conductor":
                procs = start_agent(agent, start_api=start_api, start_ui=start_ui)
                all_processes.extend(procs)

        if not all_processes:
            print("⚠️ 没有启动任何服务")
            return

        print_summary(all_processes)

        # 等待所有进程
        for name, proc in all_processes:
            try:
                proc.wait()
            except:
                pass

    except KeyboardInterrupt:
        stop_processes(all_processes)
    except Exception as e:
        print(f"❌ 启动失败: {e}")
        stop_processes(all_processes)


if __name__ == "__main__":
    main()