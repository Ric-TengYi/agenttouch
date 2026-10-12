#!/usr/bin/python3
"""AgentTouch's own editable dictation window, controlled over private pipes.

No Codex UI reads or keyboard submission. The parent owns the pipes; text is
returned only to that parent and never logged. Cocoa runs on the main thread.
"""
import json
import queue
import sys
import threading


def main():
    import AppKit as A
    from Foundation import NSObject, NSTimer
    app = A.NSApplication.sharedApplication()
    app.setActivationPolicy_(A.NSApplicationActivationPolicyRegular)
    window = A.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        ((0, 0), (600, 330)), A.NSWindowStyleMaskTitled | A.NSWindowStyleMaskClosable,
        A.NSBackingStoreBuffered, False)
    window.setReleasedWhenClosed_(False)
    window.setTitle_('AgentTouch 语音预览')
    window.center()
    label = A.NSTextField.labelWithString_('在设备上按住语音键录入；可修改文字，再点设备“发送”。')
    label.setFrame_(((20, 285), (560, 28)))
    window.contentView().addSubview_(label)
    scroll = A.NSScrollView.alloc().initWithFrame_(((20, 20), (560, 255)))
    scroll.setHasVerticalScroller_(True)
    editor = A.NSTextView.alloc().initWithFrame_(((0, 0), (560, 255)))
    editor.setFont_(A.NSFont.systemFontOfSize_(18))
    editor.setRichText_(False)
    editor.setAutoresizingMask_(A.NSViewWidthSizable)
    scroll.setDocumentView_(editor)
    window.contentView().addSubview_(scroll)
    commands = queue.Queue()
    def read_commands():
        for line in sys.stdin:
            if len(line) > 100000:
                break
            try:
                commands.put(json.loads(line))
            except ValueError:
                break
        commands.put(dict(op='quit'))
    threading.Thread(target=read_commands, daemon=True).start()

    class Controller(NSObject):
        def tick_(self, timer):
            while True:
                try:
                    command = commands.get_nowait()
                except queue.Empty:
                    return
                op = command.get('op')
                if op == 'quit':
                    app.terminate_(None)
                    return
                if op == 'show':
                    editor.setString_('')
                    label.setStringValue_(str(command.get('title', ''))[:240])
                    window.makeKeyAndOrderFront_(None)
                    app.activateIgnoringOtherApps_(True)
                    window.makeFirstResponder_(editor)
                elif op == 'hide':
                    window.orderOut_(None)
                elif op != 'read':
                    continue
                result = dict(id=command.get('id'), active=bool(app.isActive() and
                              window.isKeyWindow() and window.firstResponder() == editor),
                              text=str(editor.string()))
                print(json.dumps(result, ensure_ascii=False), flush=True)
    controller = Controller.alloc().init()
    timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
        .05, controller, 'tick:', None, True)
    app.run()
    timer.invalidate()


if __name__ == '__main__':
    main()
