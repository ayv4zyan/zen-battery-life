// mfga-input: real OS-level input and display queries for the measurement harness.
// Events are posted at the HID level, so browsers see them as genuine user input
// (trusted user activation, real trackpad gesture + momentum phases).
import AppKit
import ApplicationServices
import CoreGraphics
import Foundation

func die(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(2)
}

let keycodes: [String: CGKeyCode] = [
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "o": 31, "u": 32,
    "i": 34, "p": 35, "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
    "return": 36, "tab": 48, "space": 49, "escape": 53,
    "left": 123, "right": 124, "down": 125, "up": 126, "pagedown": 121, "pageup": 116,
]

func key(_ name: String, mods: [String]) {
    guard let code = keycodes[name] else { die("unknown key \(name)") }
    var flags = CGEventFlags()
    for m in mods {
        switch m {
        case "cmd": flags.insert(.maskCommand)
        case "shift": flags.insert(.maskShift)
        case "ctrl": flags.insert(.maskControl)
        case "alt": flags.insert(.maskAlternate)
        default: die("unknown modifier \(m)")
        }
    }
    let src = CGEventSource(stateID: .hidSystemState)
    let down = CGEvent(keyboardEventSource: src, virtualKey: code, keyDown: true)!
    let up = CGEvent(keyboardEventSource: src, virtualKey: code, keyDown: false)!
    down.flags = flags
    up.flags = flags
    down.post(tap: .cghidEventTap)
    usleep(30_000)
    up.post(tap: .cghidEventTap)
}

func move(_ x: Double, _ y: Double) {
    let e = CGEvent(mouseEventSource: nil, mouseType: .mouseMoved,
                    mouseCursorPosition: CGPoint(x: x, y: y), mouseButton: .left)!
    e.post(tap: .cghidEventTap)
}

func click(_ x: Double, _ y: Double) {
    let p = CGPoint(x: x, y: y)
    move(x, y)
    usleep(50_000)
    CGEvent(mouseEventSource: nil, mouseType: .leftMouseDown, mouseCursorPosition: p, mouseButton: .left)!
        .post(tap: .cghidEventTap)
    usleep(40_000)
    CGEvent(mouseEventSource: nil, mouseType: .leftMouseUp, mouseCursorPosition: p, mouseButton: .left)!
        .post(tap: .cghidEventTap)
}

// One trackpad "flick": a short finger gesture followed by OS-style momentum.
// deltaPx is the total finger travel (positive scrolls content down / reading forward).
func scrollEvent(_ dy: Int32, phase: Int64, momentum: Int64) {
    let e = CGEvent(scrollWheelEvent2Source: nil, units: .pixel, wheelCount: 1,
                    wheel1: -dy, wheel2: 0, wheel3: 0)!
    e.setIntegerValueField(.scrollWheelEventIsContinuous, value: 1)
    e.setIntegerValueField(.scrollWheelEventScrollPhase, value: phase)
    e.setIntegerValueField(.scrollWheelEventMomentumPhase, value: momentum)
    e.post(tap: .cghidEventTap)
}

func flick(deltaPx: Double) {
    let hz = 120.0
    let frame = useconds_t(1_000_000 / hz)
    // Finger phase: ~100 ms, ease-in.
    let fingerFrames = 12
    var sent = 0.0
    let fingerTotal = deltaPx * 0.35
    scrollEvent(0, phase: 1, momentum: 0)  // kCGScrollPhaseBegan
    for i in 1...fingerFrames {
        let target = fingerTotal * Double(i) / Double(fingerFrames)
        let d = Int32((target - sent).rounded())
        sent += Double(d)
        scrollEvent(d, phase: 2, momentum: 0)  // Changed
        usleep(frame)
    }
    scrollEvent(0, phase: 4, momentum: 0)  // Ended
    // Momentum phase: exponential decay, like AppKit's.
    var v = (deltaPx - fingerTotal) * (1 - 0.95)
    scrollEvent(Int32(v.rounded()), phase: 0, momentum: 1)  // momentum begin
    while v >= 0.5 {
        v *= 0.95
        scrollEvent(Int32(v.rounded()), phase: 0, momentum: 2)  // continue
        usleep(frame)
    }
    scrollEvent(0, phase: 0, momentum: 3)  // end
}

// Private DisplayServices brightness getter (read-only).
func brightness() -> Float {
    let path = "/System/Library/PrivateFrameworks/DisplayServices.framework/DisplayServices"
    guard let h = dlopen(path, RTLD_NOW), let sym = dlsym(h, "DisplayServicesGetBrightness") else {
        return -1
    }
    typealias Fn = @convention(c) (UInt32, UnsafeMutablePointer<Float>) -> Int32
    let fn = unsafeBitCast(sym, to: Fn.self)
    var b: Float = -1
    _ = fn(CGMainDisplayID(), &b)
    return b
}

let args = Array(CommandLine.arguments.dropFirst())
guard let cmd = args.first else {
    die("usage: mfga-input trusted|key K [mods..]|move X Y|click X Y|flick PX|scroll SECONDS PX INTERVAL|brightness|screen")
}
switch cmd {
case "trusted":
    print(AXIsProcessTrusted() ? "yes" : "no")
case "key":
    guard args.count >= 2 else { die("key needs a name") }
    key(args[1], mods: Array(args.dropFirst(2)))
case "move":
    move(Double(args[1])!, Double(args[2])!)
case "click":
    click(Double(args[1])!, Double(args[2])!)
case "flick":
    flick(deltaPx: Double(args[1])!)
case "scroll":
    // scroll SECONDS PX INTERVAL: repeated flicks of PX every INTERVAL seconds.
    let total = Double(args[1])!, px = Double(args[2])!, interval = Double(args[3])!
    let start = Date()
    while Date().timeIntervalSince(start) < total {
        let t0 = Date()
        flick(deltaPx: px)
        let rest = interval - Date().timeIntervalSince(t0)
        if rest > 0 { usleep(useconds_t(rest * 1_000_000)) }
    }
case "brightness":
    print(String(format: "%.3f", brightness()))
case "screen":
    let f = NSScreen.main!.frame
    print("\(Int(f.width)) \(Int(f.height)) \(NSScreen.main!.maximumFramesPerSecond)")
default:
    die("unknown command \(cmd)")
}
