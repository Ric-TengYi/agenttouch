"""Fail-closed native focus for a selected local Codex conversation.

AX reads only the focused window and focused element; no transcript is collected.
If this Codex version does not expose its route, selected voice stays unavailable.
"""
import ctypes as C
import json
import os
from pathlib import Path
import re
import subprocess
import time
from task_control import route_matches


class Accessibility:
    def __init__(self):
        self.ax = C.CDLL('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')
        self.cf = C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        self.ax.AXUIElementCreateApplication.argtypes = [C.c_int]
        self.ax.AXUIElementCreateApplication.restype = C.c_void_p
        self.ax.AXUIElementCopyAttributeValue.argtypes = [C.c_void_p, C.c_void_p, C.POINTER(C.c_void_p)]
        self.ax.AXUIElementCopyAttributeValue.restype = C.c_int
        self.cf.CFStringCreateWithCString.argtypes = [C.c_void_p, C.c_char_p, C.c_uint32]
        self.cf.CFStringCreateWithCString.restype = C.c_void_p
        self.cf.CFStringGetCString.argtypes = [C.c_void_p, C.c_char_p, C.c_long, C.c_uint32]
        self.cf.CFStringGetCString.restype = C.c_bool
        self.cf.CFArrayGetCount.argtypes = [C.c_void_p]; self.cf.CFArrayGetCount.restype = C.c_long
        self.cf.CFArrayGetValueAtIndex.argtypes = [C.c_void_p, C.c_long]; self.cf.CFArrayGetValueAtIndex.restype = C.c_void_p
        self.cf.CFGetTypeID.argtypes = [C.c_void_p]; self.cf.CFGetTypeID.restype = C.c_ulong
        self.cf.CFStringGetTypeID.restype = C.c_ulong
        self.cf.CFURLGetTypeID.restype = C.c_ulong
        self.cf.CFURLGetString.argtypes = [C.c_void_p]; self.cf.CFURLGetString.restype = C.c_void_p
        self.cf.CFRelease.argtypes = [C.c_void_p]
        self.diagnostic = {}

    def attr(self, obj, name):
        key = self.cf.CFStringCreateWithCString(None, name.encode(), 0x08000100)
        value = C.c_void_p()
        try:
            return value.value if self.ax.AXUIElementCopyAttributeValue(obj, key, C.byref(value)) == 0 else None
        finally:
            self.cf.CFRelease(key)

    def string(self, value):
        if not value:
            return ''
        kind = self.cf.CFGetTypeID(value)
        if kind == self.cf.CFURLGetTypeID():
            value = self.cf.CFURLGetString(value)
        elif kind != self.cf.CFStringGetTypeID():
            return ''
        buf = C.create_string_buffer(4096)
        return buf.value.decode('utf8', 'replace') if self.cf.CFStringGetCString(value, buf, len(buf), 0x08000100) else ''

    def text_attr(self, obj, name):
        value = self.attr(obj, name)
        try:
            return self.string(value)
        finally:
            if value: self.cf.CFRelease(value)

    def matches(self, pid, thread_id, require_editor=True):
        app = self.ax.AXUIElementCreateApplication(pid)
        focused = self.attr(app, 'AXFocusedUIElement')
        owned = []
        try:
            # Search fields and sidebar links are never a selected composer.
            # Only a focused multiline editor can start dictation. Its own
            # ancestry must expose the selected route; sibling URLs do not count.
            role = self.text_attr(focused, 'AXRole') if focused else ''
            self.diagnostic = dict(reason='editor_not_focused', focused_role=role, ancestors=[])
            if not focused or role != 'AXTextArea':
                return False
            self.diagnostic['reason'] = 'route_unavailable'

            obj = focused
            for _ in range(24):
                url = self.text_attr(obj, 'AXURL')
                self.diagnostic['ancestors'].append(dict(role=self.text_attr(obj, 'AXRole'),
                    description=self.text_attr(obj, 'AXDescription')[:160],
                    identifier=self.text_attr(obj, 'AXIdentifier')[:100],
                    dom_id=self.text_attr(obj, 'AXDOMIdentifier')[:100],
                    url=url[:200] if url.startswith(('app://','codex://')) else ''))
                if route_matches(url, thread_id):
                    self.diagnostic['reason'] = 'matched'
                    return True
                parent = self.attr(obj, 'AXParent')
                if not parent:
                    return False
                owned.append(parent)
                obj = parent
            return False
        finally:
            for value in owned + [focused, app]:
                if value: self.cf.CFRelease(value)


def focus_codex(row, frontmost, post_key, keyspec, ax=None, opener=subprocess.run, pause=time.sleep):
    tid = row['thread_id']
    if row.get('host') != 'local' or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', tid):
        return False
    try:
        ax = ax or Accessibility()
        result = opener(['open', '-b', 'com.openai.codex', 'codex://threads/' + tid], capture_output=True, timeout=3)
        if result.returncode:
            return False
        for _ in range(8):
            pause(.15)
            bundle, pid = frontmost()
            if bundle == 'com.openai.codex' and ax.matches(pid, tid, True):
                return frontmost() == (bundle, pid)
        # Written only after a user-triggered selection/voice action. No
        # transcript values or sibling UI tree are collected.
        diagnostic = getattr(ax, 'diagnostic', {})
        if isinstance(ax, Accessibility) and isinstance(diagnostic, dict):
            output = Path.home() / '.agentpet/task-focus-diagnostic.json'
            fd = os.open(str(output), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, 'w') as stream:
                json.dump(diagnostic, stream, ensure_ascii=False)
        return False
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False
