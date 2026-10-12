"""Read Codex's locally persisted draft, never its UI or replayed ASR text."""
import hashlib
import json
from pathlib import Path


def plain_text(node):
    if not isinstance(node, dict):raise ValueError('unsupported_draft')
    if node.get('marks'):raise ValueError('unsupported_draft')
    kind=node.get('type')
    if kind=='text':return node['text']
    if kind in ('hardBreak','hard_break'):return '\n'
    if kind not in ('doc','paragraph','blockquote','bulletList','orderedList','listItem','codeBlock','heading'):
        raise ValueError('unsupported_draft')
    parts=[plain_text(child) for child in node.get('content',[])]
    return ('\n' if kind in ('doc','blockquote','bulletList','orderedList','listItem') else '').join(parts)


class DraftSource:
    def __init__(self, root):self.root=Path(root)

    def read(self, row):
        state=json.loads((self.root/'.codex-global-state.json').read_text())
        drafts=state.get('electron-persisted-atom-state',{}).get('composer-prompt-drafts-v2',{})
        draft=drafts.get('local:'+row['thread_id'])
        if draft is None:return '', 'empty'
        if isinstance(draft,dict) and 'draft' in draft:
            if any(value for key,value in draft.items() if key!='draft'):
                raise ValueError('unsupported_draft')
            draft=draft['draft']
        prompt=draft if isinstance(draft,str) else draft.get('prompt')
        if isinstance(prompt,str):text=prompt
        elif isinstance(prompt,dict):text=plain_text(prompt['document'])
        else:raise ValueError('unsupported_draft')
        # Invisible attachments/checks must not be silently confirmed as text.
        if isinstance(draft,dict):
            # Native dictation sets this boolean on an otherwise plain draft.
            # It carries provenance, not additional message content.
            if 'usedDictation' in draft and not isinstance(draft['usedDictation'],bool):
                raise ValueError('unsupported_draft')
            if any(value for key,value in draft.items() if key not in ('prompt','usedDictation')):
                raise ValueError('unsupported_draft')
        digest=hashlib.sha256(json.dumps(draft,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        return text, digest

    def completed(self, start, stop):
        matches=[]
        for path in (self.root/'dictation-history').glob('*/metadata.json'):
            try:
                item=json.loads(path.read_text())
                # Control+M can choose the global native surface even with
                # Codex foreground. This remains only a completion marker;
                # preview text must independently come from the bound draft.
                if item.get('surface') in ('composer','global') and start*1000<=item.get('createdAtMs',0)<=stop*1000:
                    matches.append(item)
            except (ValueError,OSError,TypeError):continue
        # Completion is metadata transcript arrival, not just audio finalization.
        return len(matches)==1 and matches[0].get('status')=='completed' and bool(matches[0].get('text','').strip())
