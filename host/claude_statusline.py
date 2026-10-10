#!/usr/bin/python3
"""Forward Claude's seven-day statusline quota while preserving its command."""
import json
from pathlib import Path
import subprocess
import sys
import urllib.request


def install(settings_path, deploy):
    path, deploy = Path(settings_path), Path(deploy)
    settings = json.loads(path.read_text()) if path.exists() else {}
    original = settings.get('statusLine')
    command = '/usr/bin/python3 ' + __import__('shlex').quote(str(deploy / 'claude_statusline.py'))
    if isinstance(original, dict) and original.get('command') == command:
        return
    if original and (not isinstance(original, dict) or original.get('type') != 'command'):
        raise ValueError('unsupported statusLine; preserved without changes')
    deploy.mkdir(parents=True, exist_ok=True)
    (deploy / 'claude_statusline_original.json').write_text(json.dumps(original))
    if path.exists():
        import time
        backup = path.with_name(path.name + '.agenttouch-' + str(time.time_ns()) + '.bak')
        backup.write_bytes(path.read_bytes())
    settings['statusLine'] = dict(original or {}, type='command', command=command)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.agenttouch.tmp')
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)


def main():
    if len(sys.argv) == 4 and sys.argv[1] == '--install':
        install(sys.argv[2], sys.argv[3])
        return 0
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw)
        body = json.dumps(payload.get('rate_limits') or {}).encode()
        req = urllib.request.Request('http://127.0.0.1:8788/dashboard/quota/claude', data=body,
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=0.2):
            pass
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    try:
        original = json.loads(Path(__file__).with_name('claude_statusline_original.json').read_text())
    except (OSError, ValueError):
        original = None
    if original and original.get('command'):
        return subprocess.run(original['command'], shell=True, input=raw).returncode
    return 0


if __name__ == '__main__':
    sys.exit(main())
