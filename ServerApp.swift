import AppKit
import Foundation
import Darwin

class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    var window: NSWindow!
    var statusLabel: NSTextField!
    var memLabel: NSTextField!
    var dirField: NSTextField!
    var hostField: NSTextField!
    var portField: NSTextField!
    var modePopup: NSPopUpButton!
    var toggleButton: NSButton!
    var openButton: NSButton!
    var logView: NSTextView!
    
    var serverProcess: Process?
    var logPipe: Pipe?
    var memTimer: Timer?
    
    var isRunning = false
    
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        
        let width: CGFloat = 560
        let height: CGFloat = 570
        
        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: width, height: height),
            styleMask: [.titled, .closable, .miniaturizable],
            backing: .buffered,
            defer: false
        )
        window.title = "文件夹网站服务"
        window.center()
        window.delegate = self
        
        setupUI()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        
        startMemMonitor()
    }
    
    func setupUI() {
        guard let contentView = window.contentView else { return }
        
        let container = NSView(frame: NSRect(x: 20, y: 20, width: 520, height: 530))
        contentView.addSubview(container)
        
        // 1. 顶部栏
        let titleLabel = NSTextField(labelWithString: "文件夹网站服务")
        titleLabel.font = NSFont.systemFont(ofSize: 18, weight: .bold)
        titleLabel.frame = NSRect(x: 0, y: 495, width: 190, height: 26)
        container.addSubview(titleLabel)
        
        statusLabel = NSTextField(labelWithString: "🔴 未启动")
        statusLabel.font = NSFont.systemFont(ofSize: 12, weight: .bold)
        statusLabel.textColor = NSColor.systemRed
        statusLabel.alignment = .right
        statusLabel.frame = NSRect(x: 380, y: 498, width: 140, height: 22)
        container.addSubview(statusLabel)
        
        memLabel = NSTextField(labelWithString: "物理内存: -- MB")
        memLabel.font = NSFont.systemFont(ofSize: 12, weight: .bold)
        memLabel.textColor = NSColor.systemBlue
        memLabel.alignment = .right
        memLabel.frame = NSRect(x: 220, y: 498, width: 155, height: 22)
        container.addSubview(memLabel)
        
        // 2. 服务配置框
        let configBox = NSBox(frame: NSRect(x: 0, y: 340, width: 520, height: 145))
        configBox.title = "服务配置"
        configBox.titleFont = NSFont.systemFont(ofSize: 12, weight: .semibold)
        container.addSubview(configBox)
        
        guard let boxView = configBox.contentView else { return }
        
        let dirLabel = NSTextField(labelWithString: "服务目录:")
        dirLabel.font = NSFont.systemFont(ofSize: 12)
        dirLabel.frame = NSRect(x: 10, y: 82, width: 65, height: 22)
        boxView.addSubview(dirLabel)
        
        let documentsDir = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
            ?? FileManager.default.homeDirectoryForCurrentUser
        let defaultDir = documentsDir.path
        dirField = NSTextField(string: defaultDir)
        dirField.font = NSFont.systemFont(ofSize: 11)
        dirField.frame = NSRect(x: 80, y: 82, width: 320, height: 22)
        boxView.addSubview(dirField)
        
        let chooseBtn = NSButton(title: "选择文件夹...", target: self, action: #selector(chooseDirectory))
        chooseBtn.bezelStyle = .rounded
        chooseBtn.frame = NSRect(x: 404, y: 77, width: 106, height: 30)
        boxView.addSubview(chooseBtn)
        
        let hostLabel = NSTextField(labelWithString: "监听 IP:")
        hostLabel.font = NSFont.systemFont(ofSize: 12)
        hostLabel.frame = NSRect(x: 10, y: 49, width: 65, height: 22)
        boxView.addSubview(hostLabel)

        hostField = NSTextField(string: "0.0.0.0")
        hostField.font = NSFont.systemFont(ofSize: 12, weight: .semibold)
        hostField.frame = NSRect(x: 80, y: 49, width: 135, height: 22)
        boxView.addSubview(hostField)

        let portLabel = NSTextField(labelWithString: "端口:")
        portLabel.font = NSFont.systemFont(ofSize: 12)
        portLabel.frame = NSRect(x: 230, y: 49, width: 42, height: 22)
        boxView.addSubview(portLabel)
        
        portField = NSTextField(string: "9090")
        portField.font = NSFont.systemFont(ofSize: 12, weight: .semibold)
        portField.frame = NSRect(x: 272, y: 49, width: 75, height: 22)
        boxView.addSubview(portField)

        let modeLabel = NSTextField(labelWithString: "展示模式:")
        modeLabel.font = NSFont.systemFont(ofSize: 12)
        modeLabel.frame = NSRect(x: 10, y: 16, width: 65, height: 22)
        boxView.addSubview(modeLabel)

        modePopup = NSPopUpButton(frame: NSRect(x: 80, y: 12, width: 267, height: 28), pullsDown: false)
        modePopup.addItems(withTitles: ["index.html 首页", "文件下载列表"])
        modePopup.target = self
        modePopup.action = #selector(changeMode)
        boxView.addSubview(modePopup)
        
        let accessHint = NSTextField(labelWithString: "0.0.0.0 可供局域网/公网访问；127.0.0.1 仅限本机。")
        accessHint.font = NSFont.systemFont(ofSize: 11)
        accessHint.textColor = NSColor.systemOrange
        accessHint.frame = NSRect(x: 2, y: 311, width: 516, height: 18)
        container.addSubview(accessHint)

        // 3. 操作按钮
        toggleButton = NSButton(title: "▶ 启动服务", target: self, action: #selector(toggleServer))
        toggleButton.bezelStyle = .rounded
        toggleButton.font = NSFont.systemFont(ofSize: 13, weight: .bold)
        toggleButton.frame = NSRect(x: -2, y: 264, width: 255, height: 36)
        container.addSubview(toggleButton)
        
        openButton = NSButton(title: "🌐 打开网站", target: self, action: #selector(openBrowser))
        openButton.bezelStyle = .rounded
        openButton.font = NSFont.systemFont(ofSize: 13, weight: .medium)
        openButton.frame = NSRect(x: 265, y: 264, width: 257, height: 36)
        container.addSubview(openButton)
        
        // 4. 日志框
        let logLabel = NSTextField(labelWithString: "实时请求日志:")
        logLabel.font = NSFont.systemFont(ofSize: 12, weight: .semibold)
        logLabel.textColor = NSColor.secondaryLabelColor
        logLabel.frame = NSRect(x: 0, y: 238, width: 120, height: 20)
        container.addSubview(logLabel)
        
        let scroll = NSScrollView(frame: NSRect(x: 0, y: 0, width: 520, height: 235))
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder
        
        logView = NSTextView(frame: scroll.bounds)
        logView.isEditable = false
        logView.backgroundColor = NSColor(red: 0.07, green: 0.09, blue: 0.12, alpha: 1.0)
        logView.textColor = NSColor(red: 0.3, green: 0.9, blue: 0.4, alpha: 1.0)
        logView.font = NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
        logView.autoresizingMask = [.width]
        scroll.documentView = logView
        container.addSubview(scroll)
    }
    
    @objc func chooseDirectory() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.directoryURL = URL(fileURLWithPath: dirField.stringValue)
        if panel.runModal() == .OK, let url = panel.url {
            dirField.stringValue = url.path
            if isRunning {
                stopServer()
                startServer()
            }
        }
    }
    
    @objc func toggleServer() {
        if isRunning {
            stopServer()
        } else {
            startServer()
        }
    }

    @objc func changeMode() {
        guard isRunning else { return }
        let mode = modePopup.indexOfSelectedItem == 1 ? "list" : "index"
        stopServer()
        startServer()
        appendLog("🧭 展示模式已切换：\(mode == "index" ? "index.html 首页" : "文件下载列表")\n")
    }
    
    @objc func openBrowser() {
        let port = portField.stringValue.trimmingCharacters(in: .whitespaces)
        let configuredHost = hostField.stringValue.trimmingCharacters(in: .whitespaces)
        let browserHost = configuredHost == "0.0.0.0" ? "127.0.0.1" : configuredHost
        if let url = URL(string: "http://\(browserHost):\(port)/") {
            NSWorkspace.shared.open(url)
        }
    }
    
    func startServer() {
        guard !isRunning else { return }
        
        let dir = dirField.stringValue.trimmingCharacters(in: .whitespaces)
        let port = portField.stringValue.trimmingCharacters(in: .whitespaces)
        let bindHost = hostField.stringValue.trimmingCharacters(in: .whitespaces)
        let mode = modePopup.indexOfSelectedItem == 1 ? "list" : "index"

        var isDirectory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: dir, isDirectory: &isDirectory), isDirectory.boolValue else {
            showError("服务目录不存在或不是文件夹：\(dir)")
            return
        }
        guard let portNumber = Int(port), (1...65535).contains(portNumber) else {
            showError("端口必须是 1 到 65535 之间的数字。")
            return
        }
        var address = in_addr()
        guard inet_pton(AF_INET, bindHost, &address) == 1 else {
            showError("监听 IP 必须是有效的 IPv4 地址，例如 127.0.0.1 或 0.0.0.0。")
            return
        }

        let scriptPath: String
        if let bundledScript = Bundle.main.url(forResource: "headless_server", withExtension: "py") {
            scriptPath = bundledScript.path
        } else {
            scriptPath = URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .appendingPathComponent("headless_server.py")
                .path
        }

        let pythonCandidates = [
            "/opt/homebrew/bin/python3",
            "/usr/local/bin/python3",
            "/usr/bin/python3"
        ]
        guard let pythonPath = pythonCandidates.first(where: {
            FileManager.default.isExecutableFile(atPath: $0)
        }) else {
            showError("没有找到可用的 Python 3。")
            return
        }
        
        let process = Process()
        process.executableURL = URL(fileURLWithPath: pythonPath)
        process.arguments = [scriptPath, dir, port, bindHost, mode]
        
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = pipe
        process.terminationHandler = { [weak self] finishedProcess in
            DispatchQueue.main.async {
                guard let self, self.serverProcess === finishedProcess else { return }
                self.serverProcess = nil
                self.logPipe = nil
                self.isRunning = false
                self.statusLabel.stringValue = "🔴 已停止"
                self.statusLabel.textColor = NSColor.systemRed
                self.toggleButton.title = "▶ 启动服务"
                self.appendLog("🔴 服务进程已退出（状态码 \(finishedProcess.terminationStatus)）\n")
            }
        }
        
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            if let str = String(data: data, encoding: .utf8), !str.isEmpty {
                DispatchQueue.main.async {
                    self?.appendLog(str)
                }
            }
        }
        
        do {
            try process.run()
            serverProcess = process
            logPipe = pipe
            isRunning = true
            
            statusLabel.stringValue = "🟢 运行中 (\(port))"
            statusLabel.textColor = NSColor.systemGreen
            toggleButton.title = "⏹ 停止服务"
            let scope = bindHost == "0.0.0.0" ? "所有网络接口" : bindHost
            let modeText = mode == "index" ? "index.html 首页" : "文件下载列表"
            appendLog("🟢 服务启动成功 (\(bindHost):\(port)，\(scope))\n")
            appendLog("📂 服务目录：\(dir)\n")
            appendLog("🧭 展示模式：\(modeText)\n")
        } catch {
            showError(error.localizedDescription, title: "启动服务失败")
        }
    }

    func showError(_ message: String, title: String = "配置错误") {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = message
        alert.runModal()
    }
    
    func stopServer() {
        guard isRunning else { return }
        
        if let proc = serverProcess, proc.isRunning {
            // Clear the owned process first so an intentional SIGTERM is not logged as a crash.
            serverProcess = nil
            proc.terminate()
            proc.waitUntilExit()
        }
        serverProcess = nil
        logPipe = nil
        isRunning = false
        
        statusLabel.stringValue = "🔴 已停止"
        statusLabel.textColor = NSColor.systemRed
        toggleButton.title = "▶ 启动服务"
        appendLog("🔴 服务已停止\n")
    }
    
    func appendLog(_ text: String) {
        guard let storage = logView.textStorage else { return }
        let attr = NSAttributedString(string: text, attributes: [
            .foregroundColor: NSColor(red: 0.3, green: 0.9, blue: 0.4, alpha: 1.0),
            .font: NSFont.monospacedSystemFont(ofSize: 11, weight: .regular)
        ])
        storage.append(attr)
        if storage.length > 20000 {
            storage.deleteCharacters(in: NSRange(location: 0, length: storage.length - 15000))
        }
        logView.scrollToEndOfDocument(nil)
    }
    
    func startMemMonitor() {
        memTimer = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
            var totalMB: Double = 0
            
            var info = mach_task_basic_info()
            var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size / 4)
            let kerr = withUnsafeMutablePointer(to: &info) {
                $0.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                    task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), $0, &count)
                }
            }
            if kerr == KERN_SUCCESS {
                totalMB += Double(info.resident_size) / (1024 * 1024)
            }
            
            self?.memLabel.stringValue = String(format: "物理内存: %.1f MB", totalMB)
        }
    }
    
    func windowWillClose(_ notification: Notification) {
        stopServer()
        NSApp.terminate(nil)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
