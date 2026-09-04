# FolderWeb

FolderWeb 是一个轻量、只读的文件夹 HTTP 服务。它既可以把 `index.html` 作为网站首页，也可以把目录内容显示成适合下载的文件列表。

项目包含原生 macOS 图形界面、Tk 图形界面和纯命令行服务端。

## 功能

- 两种展示模式：`index.html` 首页、文件下载列表
- 自定义服务目录、监听 IPv4 地址和端口
- 文件下载列表支持子目录、文件大小和修改时间
- 只读服务：拒绝 POST、PUT、DELETE、CONNECT 等写入或代理请求
- 阻止绝对 URL 代理请求和越出服务目录的符号链接
- 请求日志会转义控制字符
- 自动补充常见 Web、WASM、STL 和 STEP MIME 类型

## macOS 图形界面

从 [Releases](../../releases) 下载与 Mac 架构匹配的压缩包，解压后双击 `FolderWeb.app`。

应用启动后不会立即共享文件。选择目录、监听地址、端口和展示模式，再点击“启动服务”。

- `127.0.0.1`：仅本机访问
- `0.0.0.0`：监听所有网络接口，可供局域网访问；能否从公网访问还取决于路由器、防火墙和反向代理配置

本地构建需要 Xcode Command Line Tools：

```bash
./build_app.sh
open dist/FolderWeb.app
```

## Python 图形界面

```bash
python3 server_gui.py
```

需要 Python 3 和 Tkinter。

## 命令行

首页模式：

```bash
python3 headless_server.py \
  --directory /path/to/site \
  --bind 127.0.0.1 \
  --port 9090 \
  --mode index
```

下载列表模式：

```bash
python3 headless_server.py \
  --directory /path/to/files \
  --bind 0.0.0.0 \
  --port 9090 \
  --mode list
```

查看所有参数：

```bash
python3 headless_server.py --help
```

## 安全提示

FolderWeb 本身只提供 HTTP，不包含登录认证和 TLS。监听 `0.0.0.0` 或做公网端口映射前，请确认所选目录中没有密码、密钥、隐私文件、`.env` 或其他不应公开的内容。需要公网长期使用时，建议放在 HTTPS 反向代理之后，并增加访问控制。

