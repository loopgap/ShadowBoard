"""
ShadowBoard UI Package
"""

from __future__ import annotations

import socket
from src.ui.state import ensure_dirs, load_metadata, CUSTOM_CSS
from src.ui.app import build_ui

def _pick_available_port(start: int = 7860, end: int = 7875) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"{start} 到 {end} 端口均被占用 请先关闭占用进程")

def main() -> None:
    import gradio as gr
    ensure_dirs()
    # 确保元数据已加载，以便 build_ui 能正确渲染
    load_metadata()
    
    app = build_ui()
    app.queue(default_concurrency_limit=1)
    port = _pick_available_port(7860, 7875)
    
    app.launch(
        server_name="127.0.0.1", 
        server_port=port, 
        inbrowser=True, 
        theme=gr.themes.Soft(), 
        css=CUSTOM_CSS
    )
