"""Read the selected local conversation; never use history as a sendable draft."""
import json
from pathlib import Path
import re

CONTEXT = re.compile(r'<(environment_context|permissions instructions|collaboration_mode|external_codex_apps_open_page|INSTRUCTIONS|app-context|user_instructions)\b[^>]*>.*?</\1>', re.S)

INTERNAL_CITATION = re.compile(r'<(oai-mem-citation|citation_entries|rollout_ids)\b[^>]*>.*?(?:</\1>|$)', re.S)
INTERNAL_CLOSING = re.compile(r'</(?:oai-mem-citation|citation_entries|rollout_ids)>')

def display_text(text):
    return INTERNAL_CLOSING.sub('', INTERNAL_CITATION.sub('', CONTEXT.sub('', text))).strip()

def read_exchange(path, agent="codex"):
    path=Path(path)
    with path.open('rb') as f:
        size=f.seek(0,2);start=max(0,size-8*1024*1024);f.seek(start);data=f.read(8*1024*1024)
    lines=data.splitlines()[1:] if start else data.splitlines()
    question=answer=''; active_children=set(); child_turns=set(); main_turn=None
    for line in lines:
        try:
            msg=json.loads(line)
            if agent=='claude':
                if msg.get('isSidechain'):continue
                p=msg.get('message') or {}; role=p.get('role') or msg.get('type')
                if role not in ('user','assistant'):continue
                blocks=p.get('content') or []
                text=blocks if isinstance(blocks,str) else '\n'.join(b.get('text','') for b in blocks if isinstance(b,dict) and b.get('type')=='text' and isinstance(b.get('text'),str))
                text=display_text(text)
                if not text:continue
                if role=='user':question,answer=text.strip(),''
                elif question:answer=text.strip()
                continue
            p=msg.get('payload') or {}
            typ=p.get('type')
            if msg.get('type')=='event_msg':
                if typ=='task_started':
                    a=p.get('turn_attribution') or {}
                    turn=p.get('turn_id')
                    if a.get('parent_turn_id') or (turn and p.get('root_turn_id') and turn!=p['root_turn_id']):
                        active_children.add(turn);child_turns.add(turn)
                    else:main_turn=turn
                elif typ in ('task_complete','turn_aborted'):
                    active_children.discard(p.get('turn_id'))
                continue
            if msg.get('type')!='response_item' or typ!='message':continue
            metadata=p.get('internal_chat_message_metadata_passthrough') or {}
            message_turn=metadata.get('turn_id') if isinstance(metadata,dict) else None
            if message_turn in child_turns or (not message_turn and active_children):continue
            if p.get('role')=='assistant' and message_turn and main_turn and message_turn!=main_turn:continue
            role=p.get('role')
            if role not in ('user','assistant'):continue
            blocks=p.get('content') or []
            text='\n'.join(b.get('text','') for b in blocks if isinstance(b,dict) and b.get('type') in ('input_text','output_text') and isinstance(b.get('text'),str))
            text=display_text(text)
            if not text or text.startswith(('# AGENTS.md instructions','<send_user_message_question_reply>')):continue
            if role=='user':question,answer=text,''
            elif question:answer=text
        except (ValueError,TypeError,AttributeError):continue
    return {'question':question,'answer':answer}

def detail_message(agent,token,exchange,error=''):
    clipped=False
    result=dict(t='task_detail',v=1,agent=agent,token=token,error=error,
                question=exchange.get('question',''),answer=exchange.get('answer',''),clipped=False)
    for key in ('question','answer'):
        text=display_text(result[key]);result[key]=text.encode()[:1400].decode('utf8','ignore');clipped |= result[key]!=text
    while len(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode())+1>3900:
        key=max(('question','answer'),key=lambda k:len(result[k]))
        result[key]=result[key][:-80];clipped=True
    result['clipped']=clipped
    return result

def selected_detail(control,home):
    import dashboard as D
    with control.lock:
        selection=control.selected
    if not selection:return None
    token,agent,key,_=selection
    row=control.target(token)
    if not row:return detail_message(agent,token,{},'task_changed')
    if agent not in ('codex','claude'):return detail_message(agent,token,{},'source_unavailable')
    try:
        home=Path(home).resolve() if agent=='codex' else (Path.home()/'.claude').resolve()
        if agent=='codex' and D.identity(home,control.clock())[0]!=key:raise ValueError('identity')
        path=Path(row['rollout_path']).resolve()
        if not path.is_relative_to(home):raise ValueError('path')
        exchange=read_exchange(path,agent)
        if control.target(token) is None or (agent=='codex' and D.identity(home,control.clock())[0]!=key):return None
        return detail_message(agent,token,exchange)
    except (OSError,ValueError,KeyError,TypeError,IndexError):
        return detail_message(agent,token,{},'source_unavailable')
