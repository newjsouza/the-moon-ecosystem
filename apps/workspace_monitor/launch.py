"""Launch WorkspaceMonitor v2. Usage: python3 apps/workspace_monitor/launch.py [--port 3000] [--open]"""
import argparse, sys, webbrowser
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="The Moon Workspace Monitor v2")
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--open", action="store_true", help="Open browser automatically")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    args = parser.parse_args()
    try:
        import uvicorn
    except ImportError:
        print("uvicorn not installed. Run: pip install uvicorn fastapi")
        sys.exit(1)
    if args.open: webbrowser.open(f"http://localhost:{args.port}")
    print(f"\n🌙 The Moon — Workspace Monitor v2\n   Dashboard: http://localhost:{args.port}\n   API Docs:  http://localhost:{args.port}/docs\n")
    import uvicorn
    uvicorn.run("apps.workspace_monitor.backend.server:app", host="0.0.0.0", port=args.port, reload=args.reload, log_level="info")

if __name__ == "__main__": main()
