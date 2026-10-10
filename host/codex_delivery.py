"""Deliver user-approved preview text through the desktop's existing owner.

Private desktop IPC is versioned and may change. Fail closed on discovery or
protocol errors; never fall back to keyboard submission or retry a mutation.
"""
import json
from pathlib import Path
import socket
import struct
import time
import uuid


class DeliveryError(Exception):
    pass


class DesktopClient:
    def __init__(self, endpoint=None):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(5)
        try:
            self.sock.connect(str(endpoint or Path.home() / '.codex/ipc/ipc.sock'))
            self.client_id = 'initializing-client'
            self.client_id = self.call('initialize', 0, {'clientType': 'agenttouch'})['result']['clientId']
        except Exception:
            self.sock.close()
            raise

    def close(self):
        self.sock.close()

    def take(self, size, deadline):
        data = bytearray()
        while len(data) < size:
            self.sock.settimeout(max(.001, deadline-time.monotonic()))
            if time.monotonic() >= deadline:
                raise TimeoutError()
            part = self.sock.recv(size-len(data))
            if not part:
                raise EOFError()
            data.extend(part)
        return data

    def call(self, method, version, params, owner=None, dispatch=None):
        request_id = str(uuid.uuid4())
        request = dict(type='request', requestId=request_id, sourceClientId=self.client_id,
                       version=version, method=method, params=params, timeoutMs=10000)
        if owner:
            request['targetClientId'] = owner
        payload = json.dumps(request, separators=(',', ':')).encode()
        emit = lambda: self.sock.sendall(struct.pack('<I', len(payload)) + payload)
        if dispatch is None:
            emit()
        else:
            dispatch(emit)
        deadline = time.monotonic()+12
        while time.monotonic() < deadline:
            size = struct.unpack('<I', self.take(4, deadline))[0]
            if not 0 < size <= 268435456:
                raise DeliveryError('invalid frame')
            if size > 16*1024*1024:
                while size:
                    count = min(size, 65536)
                    self.take(count, deadline)
                    size -= count
                continue
            response = json.loads(self.take(size, deadline))
            if response.get('type') != 'response' or response.get('requestId') != request_id:
                continue
            if response.get('resultType') != 'success':
                raise DeliveryError('desktop rejected request')
            if owner and response.get('handledByClientId') != owner:
                raise DeliveryError('owner changed')
            return response
        raise TimeoutError()


def discover(client, thread_id):
    response = client.call('thread-owner-discovery', 1,
                           dict(hostId='local', conversationId=thread_id))
    owner = response.get('handledByClientId')
    if not owner or response.get('result', {}).get('supportsUntrustedAppInput') is not True:
        raise DeliveryError('owner unavailable')
    result = client.call('thread-follower-read-model-settings', 1,
                         dict(conversationId=thread_id), owner)['result']
    settings = result.get('settings')
    if not settings or settings.get('resumeState') == 'needs_resume':
        raise DeliveryError('open conversation on Mac first')
    return owner


def send_preview(row, text, validate, client_factory=DesktopClient, dispatch=None):
    tid = row['thread_id']
    if row['agent'] != 'codex' or row['host'] != 'local' or str(uuid.UUID(tid)) != tid:
        raise DeliveryError('unsupported target')
    text = text.strip()
    if not text or len(text.encode('utf8')) > 65536:
        raise DeliveryError('invalid preview')
    client = client_factory()
    try:
        owner = discover(client, tid)
        # Account and token are checked again after potentially slow IPC reads.
        if not validate():
            raise DeliveryError('target changed')
        message_id = str(uuid.uuid4())
        inputs = [dict(type='text', text=text, text_elements=[])]
        restore = dict(id=message_id, text=text, createdAt=int(time.time()*1000),
                       context=dict(prompt=text, addedFiles=[], fileAttachments=[],
                                    imageAttachments=[], ideContext=None))
        if row['state'] == 'waiting':
            raise DeliveryError('pending approval')
        if row['state'] == 'running':
            method, version = 'thread-follower-steer-turn', 1
            params = dict(conversationId=tid, input=inputs, restoreMessage=restore,
                          attachments=[], clientUserMessageId=message_id)
        elif row['state'] == 'idle':
            method, version = 'thread-follower-start-turn', 2
            params = dict(conversationId=tid, turnStart=dict(
                request=dict(threadId=tid, input=inputs, clientUserMessageId=message_id),
                context=dict(restoreMessage=restore, inheritThreadSettings=True)))
        else:
            raise DeliveryError('runtime unknown')
        response = client.call(method, version, params, owner, dispatch=dispatch)
        result = response.get('result', {})
        if response.get('method') != method or 'result' not in result:
            raise DeliveryError('unconfirmed delivery')
        return True
    finally:
        client.close()
