"""Read-only local Mac telemetry. No shell commands or process/application data."""
import copy
import json
import math
from pathlib import Path
import threading
import time

def number(value):
    return value if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value) and value>=0 else None

def safe(fn):
    try:return fn()
    except Exception:return None

def rate(current,previous,elapsed):
    a,b=number(current),number(previous)
    return round((a-b)/elapsed,1) if a is not None and b is not None and a>=b and elapsed>0 else None

class Collector:
    def __init__(self,backend=None):
        if backend is None:
            try:import psutil;backend=psutil
            except ImportError:pass
        self.backend=backend;self.previous=None
    def capture(self):
        b=self.backend
        if b is None:return {}
        cpu=safe(b.cpu_times);mem=safe(b.virtual_memory)
        path='/System/Volumes/Data' if Path('/System/Volumes/Data').exists() else '/'
        disk=safe(lambda:b.disk_usage(path));io=safe(b.disk_io_counters)
        stats=safe(b.net_if_stats);net=safe(lambda:b.net_io_counters(pernic=True))
        physical={k:v for k,v in (net or {}).items() if k.startswith('en') and stats and k in stats and stats[k].isup}
        return {'cpu':[getattr(cpu,k,None) for k in ('user','nice','system','idle')],
                'memory_total':getattr(mem,'total',None),'memory_available':getattr(mem,'available',None),
                'disk_total':getattr(disk,'total',None),'disk_free':getattr(disk,'free',None),
                'disk_read':getattr(io,'read_bytes',None),'disk_write':getattr(io,'write_bytes',None),
                'net':{k:(getattr(v,'bytes_recv',None),getattr(v,'bytes_sent',None)) for k,v in physical.items()}}
    def sample(self,wall=None,mono=None):
        wall=time.time() if wall is None else wall;mono=time.monotonic() if mono is None else mono
        raw=self.capture();previous=self.previous;self.previous=(wall,mono,raw)
        out=dict(t='mac_perf',v=1,interval_s=2,observed_at=wall,cpu_pct=None,memory_pct=None,
                 memory_used=None,memory_total=number(raw.get('memory_total')),
                 disk_free=number(raw.get('disk_free')),disk_total=number(raw.get('disk_total')),
                 net_rx=None,net_tx=None,disk_read=None,disk_write=None,status='unavailable')
        total=out['memory_total'];avail=number(raw.get('memory_available'))
        if total and avail is not None and avail<=total:
            out['memory_used']=total-avail;out['memory_pct']=round(100*(total-avail)/total,1)
        if previous:
            last_wall,last_mono,old=previous;dt=mono-last_mono
            valid=0<dt<=15 and 0<wall-last_wall<=15
            if valid:
                a=raw.get('cpu',[]);b=old.get('cpu',[])
                if len(a)==len(b)==4 and all(number(v) is not None for v in a+b):
                    deltas=[x-y for x,y in zip(a,b)];total_cpu=sum(deltas)
                    if total_cpu>0 and min(deltas)>=0:out['cpu_pct']=round(100*(total_cpu-deltas[3])/total_cpu,1)
                for key in ('disk_read','disk_write'):out[key]=rate(raw.get(key),old.get(key),dt)
                new_net=raw.get('net') or {};old_net=old.get('net') or {}
                if new_net and set(new_net)==set(old_net):
                    for index,key in enumerate(('net_rx','net_tx')):
                        parts=[rate(v[index],old_net[k][index],dt) for k,v in new_net.items()]
                        if all(v is not None for v in parts):out[key]=round(sum(parts),1)
        keys=('cpu_pct','memory_pct','disk_free','net_rx','net_tx','disk_read','disk_write')
        known=sum(out[k] is not None for k in keys)
        out['status']='warming' if previous is None and known else 'ok' if known==len(keys) else 'partial' if known else 'unavailable'
        return out

class PerformanceService:
    def __init__(self):
        self.lock=threading.Lock();self.changed=threading.Condition(self.lock);self.sequence=0;self.current={'t':'mac_perf','v':1,'status':'unavailable','observed_at':0}
    def snapshot(self):
        with self.lock:result=copy.deepcopy(self.current)
        result['stale']=time.time()-result.get('observed_at',0)>10
        return result
    def start(self,push):
        def sample_loop():
            collector=Collector()
            while True:
                started=time.monotonic()
                try:
                    sample=collector.sample()
                    with self.changed:
                        self.sequence+=1
                        sample['seq']=self.sequence
                        self.current=sample
                        self.changed.notify()
                except Exception:pass
                time.sleep(max(.1,2-(time.monotonic()-started)))
        def send_loop():
            delivered=0
            while True:
                with self.changed:
                    self.changed.wait_for(lambda:self.sequence!=delivered)
                    sequence=self.sequence;sample=copy.deepcopy(self.current)
                try:push((json.dumps(sample,separators=(',',':'),allow_nan=False)+'\n').encode())
                except Exception:pass
                delivered=sequence
        threading.Thread(target=sample_loop,name='mac-performance',daemon=True).start()
        threading.Thread(target=send_loop,name='mac-performance-send',daemon=True).start()
