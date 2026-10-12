"""Bounded read-only calls to the bundled Codex app-server over stdio."""
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import time

class StdioReadOnly:
    def __init__(self):
        bundled=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex')
        binary=str(bundled) if bundled.is_file() else shutil.which('codex')
        if not binary:raise FileNotFoundError('codex_binary_unavailable')
        self.process=subprocess.Popen([binary,'app-server','--stdio'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
        self.selector=selectors.DefaultSelector()
        self.selector.register(self.process.stdout,selectors.EVENT_READ)
        self.buffer=b''
    def handshake(self):pass
    def send(self,message):
        if message.get('method') not in ('initialize','initialized','account/rateLimits/read'):
            raise ValueError('read_only_method_required')
        self.process.stdin.write((json.dumps(message)+'\n').encode());self.process.stdin.flush()
    def call(self,request_id,method,params):
        self.send(dict(id=request_id,method=method,params=params))
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            while b'\n' in self.buffer:
                line,self.buffer=self.buffer.split(b'\n',1)
                message=json.loads(line)
                if not isinstance(message,dict):continue
                if message.get('id')==request_id:
                    if 'error' in message:raise ValueError('rpc_query_rejected')
                    return message['result']
            for key,_ in self.selector.select(max(0,deadline-time.monotonic())):
                chunk=os.read(key.fd,65536)
                if not chunk:raise EOFError()
                self.buffer+=chunk
                if len(self.buffer)>4*1024*1024:raise ValueError('rpc_buffer_limit')
        raise TimeoutError()
    def close(self):
        self.selector.close()
        self.process.terminate()
        try:self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=2)
        for pipe in (self.process.stdin,self.process.stdout):pipe.close()
