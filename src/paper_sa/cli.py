import argparse
import os
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from . import __version__


def main():
    parser = argparse.ArgumentParser(prog="paper-sa", description="Paper SA — 本地医学文献研究工作台")
    parser.add_argument("command", nargs="?", choices=["serve", "install-browser"], default="serve")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args()
    if args.command == "install-browser":
        raise SystemExit(subprocess.call([sys.executable, "-m", "playwright", "install", "chromium"]))
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在 1–65535 范围内")
    if args.data_dir:
        os.environ["PAPER_SA_HOME"] = str(args.data_dir.resolve())
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", args.port))
        except OSError:
            parser.error(f"端口 {args.port} 已被占用，请使用 paper-sa --port {args.port + 1}")
    import uvicorn

    from .app import create_app

    app = create_app(args.data_dir)
    url = f"http://127.0.0.1:{args.port}"
    print(f"\n  Paper SA {__version__}\n  {url}\n  Data: {app.state.config.root}\n  Press Ctrl+C to stop.\n")
    if not args.no_browser:
        timer = threading.Timer(1.2, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
