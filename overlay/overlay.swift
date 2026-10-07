// Full-screen, above-everything meeting alert. Exit codes: 0 dismiss, 10 join, 20 snooze.
// Usage: echo '<json payload>' | overlay   (keys: header, title, subtitle, link, join_label,
// snooze_label, dismiss_label, hint, auto_close, sound)
import AppKit

let payload = (try? JSONSerialization.jsonObject(
    with: FileHandle.standardInput.readDataToEndOfFile())) as? [String: Any] ?? [:]
func field(_ key: String, _ fallback: String) -> String { payload[key] as? String ?? fallback }

let header = field("header", "MEETING")
let title = field("title", "")
let subtitle = field("subtitle", "")
let joinURL = field("link", "")
let joinLabel = field("join_label", joinURL.isEmpty ? "OK  (Enter)" : "Join  (Enter)")
let snoozeLabel = field("snooze_label", "Snooze  (Space)")
let dismissLabel = field("dismiss_label", "Dismiss  (Esc)")
let hintText = field("hint", "")
let autoClose = (payload["auto_close"] as? NSNumber)?.doubleValue ?? 0
let soundOn = payload["sound"] as? Bool ?? true

final class OverlayWindow: NSWindow {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

// Layer-backed button: NSButton's stock bezels cap out around 32pt tall and render
// as washed-out slabs at this size, so draw the pill ourselves.
final class PillButton: NSButton {
    private let fill: NSColor
    private let hoverFill: NSColor

    init(label: String, primary: Bool, target: AnyObject, action: Selector, key: String) {
        fill = primary ? .white : NSColor(white: 1, alpha: 0.16)
        hoverFill = primary ? NSColor(white: 0.92, alpha: 1) : NSColor(white: 1, alpha: 0.28)
        super.init(frame: .zero)
        self.target = target
        self.action = action
        isBordered = false
        bezelStyle = .regularSquare
        wantsLayer = true
        layer?.cornerRadius = 18
        layer?.backgroundColor = fill.cgColor
        keyEquivalent = key
        let para = NSMutableParagraphStyle()
        para.alignment = .center
        attributedTitle = NSAttributedString(string: label, attributes: [
            .font: NSFont.systemFont(ofSize: 25, weight: .semibold),
            .foregroundColor: primary ? NSColor(calibratedRed: 0.72, green: 0.07, blue: 0.09, alpha: 1) : NSColor.white,
            .paragraphStyle: para,
        ])
    }

    required init?(coder: NSCoder) { fatalError() }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        trackingAreas.forEach(removeTrackingArea)
        addTrackingArea(NSTrackingArea(rect: bounds, options: [.mouseEnteredAndExited, .activeAlways], owner: self))
    }
    override func mouseEntered(with event: NSEvent) { layer?.backgroundColor = hoverFill.cgColor }
    override func mouseExited(with event: NSEvent) { layer?.backgroundColor = fill.cgColor }
}

final class App: NSObject, NSApplicationDelegate {
    var windows: [NSWindow] = []
    var beep: Timer?

    func applicationDidFinishLaunching(_ n: Notification) {
        NSApp.setActivationPolicy(.regular)
        for screen in NSScreen.screens { windows.append(makeWindow(on: screen)) }
        NSApp.activate(ignoringOtherApps: true)
        windows.first?.makeKeyAndOrderFront(nil)
        if soundOn { NSSound(named: "Sosumi")?.play() }
        beep = Timer.scheduledTimer(withTimeInterval: 4, repeats: true) { _ in
            if soundOn { NSSound(named: "Sosumi")?.play() }
            NSApp.activate(ignoringOtherApps: true)
            self.windows.forEach { $0.orderFrontRegardless() }
        }
        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { ev in
            switch ev.keyCode {
            case 36, 76: self.join(); return nil      // Return / Enter
            case 53: self.dismiss(); return nil       // Esc
            case 49: self.snooze(); return nil        // Space
            default: return ev
            }
        }
        if autoClose > 0 {
            Timer.scheduledTimer(withTimeInterval: autoClose, repeats: false) { _ in exit(0) }
        }
    }

    func makeWindow(on screen: NSScreen) -> NSWindow {
        let f = screen.frame
        let w = OverlayWindow(contentRect: f, styleMask: .borderless, backing: .buffered, defer: false, screen: screen)
        w.level = .screenSaver
        w.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
        w.isOpaque = false
        w.backgroundColor = NSColor(calibratedRed: 0.80, green: 0.08, blue: 0.10, alpha: 0.97)
        w.hasShadow = false

        let v = NSView(frame: NSRect(origin: .zero, size: f.size))
        let cx = f.width / 2, cy = f.height / 2
        let margin: CGFloat = 80

        let big = NSTextField(labelWithString: header)
        big.font = NSFont.systemFont(ofSize: 34, weight: .heavy)
        big.textColor = NSColor(white: 1, alpha: 0.8)
        big.alignment = .center
        big.frame = NSRect(x: 0, y: cy + 190, width: f.width, height: 44)

        let t = NSTextField(wrappingLabelWithString: title)
        t.font = NSFont.systemFont(ofSize: 76, weight: .bold)
        t.textColor = .white
        t.alignment = .center
        t.maximumNumberOfLines = 2
        t.frame = NSRect(x: margin, y: cy + 40, width: f.width - margin * 2, height: 140)

        let s = NSTextField(wrappingLabelWithString: subtitle)
        s.font = NSFont.systemFont(ofSize: 30, weight: .medium)
        s.textColor = NSColor(white: 1, alpha: 0.92)
        s.alignment = .center
        s.frame = NSRect(x: margin, y: cy - 60, width: f.width - margin * 2, height: 90)

        let specs: [(String, Bool, Selector, String)] = [
            (joinLabel, true, #selector(join), "\r"),
            (snoozeLabel, false, #selector(snooze), " "),
            (dismissLabel, false, #selector(dismiss), "\u{1b}"),
        ]
        let bw: CGFloat = 300, bh: CGFloat = 68, gap: CGFloat = 24
        let total = CGFloat(specs.count) * bw + CGFloat(specs.count - 1) * gap
        var x = cx - total / 2
        var buttons: [NSView] = []
        for (label, primary, sel, key) in specs {
            let b = PillButton(label: label, primary: primary, target: self, action: sel, key: key)
            b.frame = NSRect(x: x, y: cy - 190, width: bw, height: bh)
            x += bw + gap
            buttons.append(b)
        }

        let hint = NSTextField(labelWithString: hintText)
        hint.font = NSFont.systemFont(ofSize: 17)
        hint.textColor = NSColor(white: 1, alpha: 0.65)
        hint.alignment = .center
        hint.frame = NSRect(x: 0, y: cy - 250, width: f.width, height: 26)

        ([big, t, s, hint] + buttons).forEach { v.addSubview($0) }
        w.contentView = v
        w.orderFrontRegardless()
        return w
    }

    @objc func join() {
        if let u = URL(string: joinURL), ["http", "https"].contains(u.scheme?.lowercased() ?? "") { NSWorkspace.shared.open(u) }
        exit(10)
    }
    @objc func snooze() { exit(20) }
    @objc func dismiss() { exit(0) }
}

let app = NSApplication.shared
let delegate = App()
app.delegate = delegate
app.run()
