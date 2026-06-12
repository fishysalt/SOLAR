#!/usr/bin/env python
"""统一启动脚本"""

import sys
import subprocess
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def start_all():
    print("🚀 启动所有 Agent...")
    print("=" * 50)
    
    processes = []
    
    print("📡 启动 Creator Agent...")
    creator_proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "creator" / "ui.py")],
        cwd=str(PROJECT_ROOT),
        env={**subprocess.os.environ, "AGENT_PORT": "7861"}
    )
    processes.append(("Creator", creator_proc))
    
    import time
    time.sleep(2)
    print("📡 启动 Scavenger Agent...")
    scavenger_proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "scavenger" / "ui.py")],
        cwd=str(PROJECT_ROOT),
        env={**subprocess.os.environ, "AGENT_PORT": "7862"}
    )
    processes.append(("Scavenger", scavenger_proc))

    time.sleep(2)


    print("🎵 启动 Conductor 主控...")
    conductor_proc = subprocess.Popen(
        [sys.executable, str(PROJECT_ROOT / "conductor" / "ui.py")],
        cwd=str(PROJECT_ROOT)
    )
    processes.append(("Conductor", conductor_proc))
    
    print("\n" + "=" * 50)
    print("✅ 所有 Agent 已启动:")
    print("   🎵 Conductor UI: http://localhost:7860")
    print("   ✨ Creator UI: http://localhost:7961")
    print("   ✨ Creator API: http://localhost:7861")
    print("   🔍 Scavenger UI: http://localhost:7962")
    print("   🔍 Scavenger API: http://localhost:7862")
    print("=" * 50)
    print("\n按 Ctrl+C 停止...")
    
    try:
        for name, proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        print("\n🛑 正在停止...")
        for name, proc in processes:
            proc.terminate()
        print("✅ 已停止")


def start_conductor_only():
    print("🎵 启动 Conductor 主控...")
    subprocess.run([sys.executable, str(PROJECT_ROOT / "conductor" / "ui.py")])


def start_agent_only(agent_name: str):
    print(f"✨ 启动 {agent_name}...")
    subprocess.run([sys.executable, str(PROJECT_ROOT / agent_name / "ui.py")])


def list_agents():
    print("📋 可用的 Agent:")
    for d in PROJECT_ROOT.iterdir():
        if d.is_dir() and (d / "ui.py").exists():
            print(f"   ✅ {d.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="启动所有 Agent")
    parser.add_argument("--conductor", action="store_true", help="仅启动 Conductor")
    parser.add_argument("--agent", type=str, help="仅启动指定 Agent")
    parser.add_argument("--list", action="store_true", help="列出所有 Agent")
    
    args = parser.parse_args()
    
    if args.list:
        list_agents()
    elif args.all:
        start_all()
    elif args.conductor:
        start_conductor_only()
    elif args.agent:
        start_agent_only(args.agent)
    else:
        start_conductor_only()