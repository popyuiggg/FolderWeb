#!/usr/bin/env python3
"""通用文件夹网站服务的图形启动器。"""

import sys
import os
import resource
import ctypes

PREFERRED_PYTHON = "/opt/homebrew/bin/python3"
if sys.version_info < (3, 12) and os.path.isfile(PREFERRED_PYTHON):
    os.execv(PREFERRED_PYTHON, [PREFERRED_PYTHON, *sys.argv])

# 静音 macOS 自带 Tkinter 的废弃警告
os.environ["TK_SILENCE_DEPRECATION"] = "1"

import threading
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox
from functools import partial

from headless_server import (
    SecureStaticRequestHandler,
    SecureThreadingHTTPServer,
    clean_log_value,
)

# macOS 自动释放池周期回收（彻底根除 macOS Tkinter 绘图上下文内存泄漏漏洞）
try:
    _objc = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Foundation.framework/Foundation")
    _objc.objc_getClass.restype = ctypes.c_void_p
    _objc.objc_getClass.argtypes = [ctypes.c_char_p]
    _objc.sel_registerName.restype = ctypes.c_void_p
    _objc.sel_registerName.argtypes = [ctypes.c_char_p]
    _objc.objc_msgSend.restype = ctypes.c_void_p
    _objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _pool_class = _objc.objc_getClass(b"NSAutoreleasePool")
    _alloc_sel = _objc.sel_registerName(b"alloc")
    _init_sel = _objc.sel_registerName(b"init")
    _drain_sel = _objc.sel_registerName(b"drain")

    def drain_autorelease_pool():
        p = _objc.objc_msgSend(_objc.objc_msgSend(_pool_class, _alloc_sel), _init_sel)
        _objc.objc_msgSend(p, _drain_sel)
except Exception:
    def drain_autorelease_pool():
        pass


class GUIRequestHandler(SecureStaticRequestHandler):
    def log_message(self, format, *args):
        if hasattr(self.server, 'app_instance') and self.server.app_instance:
            message = clean_log_value(format % args)
            self.server.app_instance.append_log(
                f"{clean_log_value(self.address_string())} - {message}"
            )


class MinimalServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("文件夹网站服务")
        self.root.geometry("560x540")
        self.root.minsize(500, 500)

        # 默认配置
        default_dir = os.path.dirname(os.path.abspath(__file__))

        self.dir_var = tk.StringVar(value=default_dir)
        self.host_var = tk.StringVar(value="0.0.0.0")
        self.port_var = tk.StringVar(value="9090")
        self.mode_var = tk.StringVar(value="index")

        self.server = None
        self.server_thread = None
        self.is_running = False

        self.setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # 启动实时内存监测与自动内存回收
        self.update_mem_monitor()

        # 由用户确认目录、监听地址和模式后手动启动，避免误共享文件。

    def setup_ui(self):
        # 整体内边距容器
        main_container = tk.Frame(self.root, padx=18, pady=16)
        main_container.pack(fill="both", expand=True)

        # 1. 顶部标题与状态栏
        top_bar = tk.Frame(main_container)
        top_bar.pack(fill="x", pady=(0, 14))

        tk.Label(
            top_bar,
            text="文件夹网站服务",
            font=("Helvetica", 18, "bold"),
            fg="#111827"
        ).pack(side="left")

        # 状态红绿标签
        self.status_badge = tk.Label(
            top_bar,
            text="🔴 未启动",
            font=("Helvetica", 11, "bold"),
            fg="#b91c1c",
            padx=10,
            pady=3
        )
        self.status_badge.pack(side="right")

        # 物理内存实时监测胶囊
        self.mem_badge = tk.Label(
            top_bar,
            text="物理内存: -- MB",
            font=("Helvetica", 11, "bold"),
            fg="#1d4ed8",
            padx=8,
            pady=3
        )
        self.mem_badge.pack(side="right", padx=(0, 8))

        # 2. 参数配置卡片
        card = tk.LabelFrame(
            main_container,
            text=" 服务配置 ",
            font=("Helvetica", 11, "bold"),
            fg="#374151",
            padx=12,
            pady=10
        )
        card.pack(fill="x", pady=(0, 12))

        # 目录设置
        dir_frame = tk.Frame(card)
        dir_frame.pack(fill="x", pady=4)
        tk.Label(
            dir_frame,
            text="文件目录:",
            font=("Helvetica", 11),
            fg="#374151",
            width=8,
            anchor="w"
        ).pack(side="left")

        dir_entry = tk.Entry(
            dir_frame,
            textvariable=self.dir_var,
            font=("Helvetica", 11),
            fg="#1d4ed8"
        )
        dir_entry.pack(side="left", fill="x", expand=True, padx=6, ipady=3)

        tk.Button(
            dir_frame,
            text="选择文件夹...",
            font=("Helvetica", 10),
            command=self.browse_dir
        ).pack(side="right")

        # 监听地址与端口
        address_frame = tk.Frame(card)
        address_frame.pack(fill="x", pady=4)
        tk.Label(
            address_frame,
            text="监听 IP:",
            font=("Helvetica", 11),
            fg="#374151",
            width=8,
            anchor="w"
        ).pack(side="left")

        host_entry = tk.Entry(
            address_frame,
            textvariable=self.host_var,
            font=("Helvetica", 11, "bold"),
            fg="#0f766e",
            width=15
        )
        host_entry.pack(side="left", padx=6, ipady=3)

        tk.Label(
            address_frame,
            text="端口:",
            font=("Helvetica", 11),
            fg="#374151"
        ).pack(side="left", padx=(12, 0))

        port_entry = tk.Entry(
            address_frame,
            textvariable=self.port_var,
            font=("Helvetica", 11, "bold"),
            fg="#0f766e",
            width=8
        )
        port_entry.pack(side="left", padx=6, ipady=3)

        # 展示模式
        mode_frame = tk.Frame(card)
        mode_frame.pack(fill="x", pady=(5, 2))
        tk.Label(
            mode_frame,
            text="展示模式:",
            font=("Helvetica", 11),
            fg="#374151",
            width=8,
            anchor="w"
        ).pack(side="left")
        tk.Radiobutton(
            mode_frame,
            text="index.html 首页",
            variable=self.mode_var,
            value="index",
            font=("Helvetica", 10),
            command=self.apply_mode
        ).pack(side="left", padx=6)
        tk.Radiobutton(
            mode_frame,
            text="文件下载列表",
            variable=self.mode_var,
            value="list",
            font=("Helvetica", 10),
            command=self.apply_mode
        ).pack(side="left", padx=6)

        tk.Label(
            card,
            text="提示：0.0.0.0 可供局域网/公网访问；127.0.0.1 仅限本机。",
            font=("Helvetica", 9),
            fg="#b45309",
            anchor="w"
        ).pack(fill="x", pady=(5, 0))

        # 3. 操作按钮组
        btn_frame = tk.Frame(main_container)
        btn_frame.pack(fill="x", pady=(0, 12))

        self.toggle_btn = tk.Button(
            btn_frame,
            text="▶ 启动服务",
            font=("Helvetica", 12, "bold"),
            command=self.toggle_server,
            pady=6
        )
        self.toggle_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.open_btn = tk.Button(
            btn_frame,
            text="🌐 打开网站",
            font=("Helvetica", 12),
            command=self.open_local_browser,
            pady=6
        )
        self.open_btn.pack(side="right", padx=(8, 0))

        # 4. 实时请求日志（使用 Listbox 彻底根除 macOS Tk 8.5 内存泄漏）
        log_frame = tk.LabelFrame(
            main_container,
            text=" 实时请求日志 ",
            font=("Helvetica", 11, "bold"),
            fg="#374151",
            padx=10,
            pady=8
        )
        log_frame.pack(fill="both", expand=True)

        self.log_list = tk.Listbox(
            log_frame,
            height=8,
            font=("Menlo", 10),
            bg="#111827",
            fg="#4ade80",
            selectbackground="#374151",
            relief="flat",
            highlightthickness=0
        )
        self.log_list.pack(fill="both", expand=True)

    def update_mem_monitor(self):
        try:
            # 回收 macOS 自动释放池
            drain_autorelease_pool()
            # 读取当前进程真实物理内存占用（RSS，macOS ru_maxrss 单位是 bytes）
            rss_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            rss_mb = rss_bytes / (1024 * 1024)
            self.mem_badge.config(text=f"物理内存: {rss_mb:.1f} MB")
        except Exception:
            pass
        self.root.after(1000, self.update_mem_monitor)

    def append_log(self, text):
        def _append():
            try:
                self.log_list.insert("end", text)
                # 限制最多保留 100 行日志，避免无限制累积
                if self.log_list.size() > 100:
                    self.log_list.delete(0, 0)
                self.log_list.see("end")
            except Exception:
                pass
        self.root.after(0, _append)

    def browse_dir(self):
        new_dir = filedialog.askdirectory(initialdir=self.dir_var.get())
        if new_dir:
            self.dir_var.set(new_dir)
            if self.is_running:
                self.stop_server()
                self.start_server()

    def toggle_server(self):
        if self.is_running:
            self.stop_server()
        else:
            self.start_server()

    def apply_mode(self):
        if self.server:
            self.server.serve_mode = self.mode_var.get()
            mode_text = "index.html 首页" if self.mode_var.get() == "index" else "文件下载列表"
            self.append_log(f"展示模式已切换: {mode_text}")

    def start_server(self):
        if self.is_running:
            return

        port_str = self.port_var.get().strip()
        try:
            port = int(port_str)
        except ValueError:
            messagebox.showerror("错误", "端口号必须是数字")
            return
        if not 1 <= port <= 65535:
            messagebox.showerror("错误", "端口号必须在 1 到 65535 之间")
            return

        serve_dir = self.dir_var.get().strip()
        if not os.path.isdir(serve_dir):
            messagebox.showerror("错误", f"目录不存在: {serve_dir}")
            return

        bind_host = self.host_var.get().strip()
        if not bind_host:
            messagebox.showerror("错误", "监听 IP 不能为空")
            return

        try:
            handler = partial(GUIRequestHandler, directory=serve_dir)
            self.server = SecureThreadingHTTPServer((bind_host, port), handler)
            self.server.app_instance = self
            self.server.serve_mode = self.mode_var.get()

            self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.server_thread.start()
            self.is_running = True

            self.status_badge.config(text=f"🟢 运行中 ({port})", fg="#15803d")
            self.toggle_btn.config(text="⏹ 停止服务")
            scope = "所有网络接口" if bind_host == "0.0.0.0" else bind_host
            mode_text = "index.html 首页" if self.mode_var.get() == "index" else "文件下载列表"
            self.append_log(f"服务已启动: {bind_host}:{port}（{scope}）")
            self.append_log(f"服务目录: {serve_dir}")
            self.append_log(f"展示模式: {mode_text}")
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动服务:\n{e}")
            self.stop_server()

    def stop_server(self):
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass
            self.server = None

        self.is_running = False
        self.status_badge.config(text="🔴 已停止", fg="#b91c1c")
        self.toggle_btn.config(text="▶ 启动服务")
        self.append_log("服务已停止")

    def open_local_browser(self):
        port = self.port_var.get().strip()
        host = self.host_var.get().strip()
        browser_host = "127.0.0.1" if host == "0.0.0.0" else host
        webbrowser.open(f"http://{browser_host}:{port}/")

    def on_close(self):
        if self.is_running:
            self.stop_server()
        self.root.destroy()
        sys.exit(0)


if __name__ == "__main__":
    root = tk.Tk()
    app = MinimalServerGUI(root)
    root.mainloop()
