import AppKit
import Carbon

let dataDirectory = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/LGTVControl", isDirectory: true)

final class TVApp: NSObject, NSApplicationDelegate {
    var item: NSStatusItem!
    var statusItem: NSMenuItem!
    var keys: [EventHotKeyRef] = []
    var handler: EventHandlerRef?
    var pending: [(String, Bool)] = []
    var busy = false
    var screenPresent = false
    var debounce: DispatchWorkItem?
    var observers: [NSObjectProtocol] = []

    var configuration: [String: Any] = [:]
    func connected() -> Bool {
        let names = configuration["screen_names"] as? [String] ?? ["LG TV", "LG TV SSCR2"]
        return NSScreen.screens.contains { names.contains($0.localizedName) }
    }
    func log(_ message: String) {
        let url = dataDirectory.appendingPathComponent("app.log")
        let line = "\(ISO8601DateFormatter().string(from: Date())) \(message)\n"
        if let attributes = try? FileManager.default.attributesOfItem(atPath: url.path),
           let size = attributes[.size] as? NSNumber, size.intValue > 1_000_000 {
            try? Data().write(to: url)
        }
        if !FileManager.default.fileExists(atPath: url.path) { FileManager.default.createFile(atPath: url.path, contents: nil) }
        if let file = try? FileHandle(forWritingTo: url) {
            defer { try? file.close() }
            _ = try? file.seekToEnd()
            try? file.write(contentsOf: Data(line.utf8))
        }
    }
    func applicationDidFinishLaunching(_ notification: Notification) {
        try? FileManager.default.createDirectory(at: dataDirectory, withIntermediateDirectories: true)
        if let data = try? Data(contentsOf: dataDirectory.appendingPathComponent("config.json")),
           let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any] { configuration = json }
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.title = "LG"
        let menu = NSMenu()
        for port in 1...4 {
            let key = String(port)
            let labels = configuration["input_labels"] as? [String: String] ?? [:]
            let title = labels[key] ?? "HDMI \(port)"
            let row = NSMenuItem(title: title, action: #selector(selectInput(_:)), keyEquivalent: key)
            row.keyEquivalentModifierMask = [.command, .control]
            row.tag = Int(key)!
            row.target = self
            menu.addItem(row)
        }
        menu.addItem(.separator())
        statusItem = NSMenuItem(title: "Ready · LAN control", action: nil, keyEquivalent: "")
        menu.addItem(statusItem)
        let refresh = NSMenuItem(title: "Check TV status", action: #selector(refreshStatus), keyEquivalent: "")
        refresh.target = self; menu.addItem(refresh)
        let pair = NSMenuItem(title: "Pair TV (accept prompt on TV)", action: #selector(pairTV), keyEquivalent: "")
        pair.target = self; menu.addItem(pair)
        let folder = NSMenuItem(title: "Open configuration and logs", action: #selector(openData), keyEquivalent: "")
        folder.target = self; menu.addItem(folder)
        menu.addItem(.separator())
        let quit = NSMenuItem(title: "Quit LG TV Control", action: #selector(quitApp), keyEquivalent: "")
        quit.target = self; menu.addItem(quit)
        item.menu = menu
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let result = InstallEventHandler(GetApplicationEventTarget(), { _, event, context in
            guard let event = event, let context = context else { return OSStatus(eventNotHandledErr) }
            var keyID = EventHotKeyID()
            let result = GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), nil, MemoryLayout<EventHotKeyID>.size, nil, &keyID)
            guard result == noErr else { return result }
            let app = Unmanaged<TVApp>.fromOpaque(context).takeUnretainedValue()
            app.run("hdmi\(keyID.id)", quiet: false)
            return noErr
        }, 1, &spec, Unmanaged.passUnretained(self).toOpaque(), &handler)
        if result != noErr { log("Hotkey handler error: \(result)") }
        for (id, code) in [(1, kVK_ANSI_1), (2, kVK_ANSI_2), (3, kVK_ANSI_3), (4, kVK_ANSI_4)] {
            var ref: EventHotKeyRef?
            let status = RegisterEventHotKey(UInt32(code), UInt32(cmdKey | controlKey), EventHotKeyID(signature: 0x4C475456, id: UInt32(id)), GetApplicationEventTarget(), 0, &ref)
            if status == noErr, let ref = ref { keys.append(ref) }
            else { statusItem.title = "Hotkey registration failed: \(id)" }
            log("Register Cmd+Ctrl+\(id): \(status)")
        }
        screenPresent = connected()
        let center = NSWorkspace.shared.notificationCenter
        for name in [NSWorkspace.screensDidSleepNotification, NSWorkspace.willSleepNotification] {
            observers.append(center.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                guard let self = self, self.connected() else { return }
                self.run("sleep", quiet: true)
            })
        }
        for name in [NSWorkspace.screensDidWakeNotification, NSWorkspace.didWakeNotification] {
            observers.append(center.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
                guard let self = self, self.connected() else { return }
                self.run("wake", quiet: true)
            })
        }
        observers.append(NotificationCenter.default.addObserver(forName: NSApplication.didChangeScreenParametersNotification, object: nil, queue: .main) { [weak self] _ in
            self?.debounce?.cancel()
            let work = DispatchWorkItem { [weak self] in
                guard let self = self else { return }
                let now = self.connected()
                if now && !self.screenPresent { self.run("attach", quiet: false) }
                self.screenPresent = now
            }
            self?.debounce = work
            DispatchQueue.main.asyncAfter(deadline: .now() + 2, execute: work)
        })
        log("App started; registered \(keys.count) hotkeys; LG connected: \(screenPresent)")
    }
    @objc func selectInput(_ sender: NSMenuItem) { run("hdmi\(sender.tag)", quiet: false) }
    @objc func pairTV() { run("pair", quiet: false) }
    @objc func refreshStatus() { run("status", quiet: false) }
    @objc func openData() { NSWorkspace.shared.open(dataDirectory) }
    @objc func quitApp() { NSApp.terminate(nil) }

    func run(_ action: String, quiet: Bool) {
        if busy {
            if action == "sleep" || action == "wake" { pending.removeAll { $0.0 == "sleep" || $0.0 == "wake" } }
            pending.append((action, quiet)); return
        }
        guard let resources = Bundle.main.resourceURL else { return }
        busy = true
        let process = Process()
        process.executableURL = resources.appendingPathComponent("lgtv-helper/lgtv-helper")
        process.arguments = [action]
        process.currentDirectoryURL = dataDirectory
        let output = Pipe()
        process.standardOutput = output; process.standardError = output
        if !quiet { statusItem.title = "Running: \(action)…" }
        let captured = NSMutableData()
        let captureLock = NSLock()
        output.fileHandleForReading.readabilityHandler = { handle in
            let chunk = handle.availableData
            captureLock.lock()
            if captured.length < 262144 { captured.append(chunk) }
            captureLock.unlock()
        }
        process.terminationHandler = { [weak self] process in
            output.fileHandleForReading.readabilityHandler = nil
            let remaining = output.fileHandleForReading.readDataToEndOfFile()
            captureLock.lock()
            captured.append(remaining)
            let data = captured.copy() as! Data
            captureLock.unlock()
            let text = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.log("\(action) exit=\(process.terminationStatus)" + (action == "status" ? "" : " \(text)"))
                if process.terminationStatus == 0 {
                    if action == "status", let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                       let app = json["app"] as? String, let power = json["power"] as? [String: Any] {
                        self.statusItem.title = "\(app.replacingOccurrences(of: "com.webos.app.", with: "")) · \(power["state"] ?? "")"
                    } else if !quiet { self.statusItem.title = text }
                } else { self.statusItem.title = "TV connection failed (see log)" }
                self.busy = false
                if !self.pending.isEmpty { let next = self.pending.removeFirst(); self.run(next.0, quiet: next.1) }
            }
        }
        do { try process.run() }
        catch { busy = false; statusItem.title = "Could not start controller"; log("Launch error: \(error)") }
    }
    func applicationWillTerminate(_ notification: Notification) {
        keys.forEach { UnregisterEventHotKey($0) }
        if let handler = handler { RemoveEventHandler(handler) }
    }
}
let app = NSApplication.shared
let delegate = TVApp()
app.setActivationPolicy(.accessory)
app.delegate = delegate
app.run()
