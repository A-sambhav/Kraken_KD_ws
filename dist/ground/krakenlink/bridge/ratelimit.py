"""Drop-on-pressure byte token bucket and deterministic message priorities."""
import logging, time
PRIORITY={'ACK':0,'STATUS':1,'PONG':2,'DOA':3,'POSE':4,'SPECTRUM':5,'SETTINGS':6}
class TokenBucket:
    def __init__(self, rate_bps=625., capacity=None, transport='mavlink', logger=None):
        cap=1250. if transport=='mavlink' else 6250.
        if rate_bps>cap:
            (logger or logging.getLogger(__name__)).warning('rate %.1f exceeds %s hard cap %.1f; clamping',rate_bps,transport,cap); rate_bps=cap
        self.rate=float(rate_bps); self.capacity=float(capacity if capacity is not None else rate_bps); self.tokens=self.capacity; self.updated=time.monotonic(); self.dropped=0
    def allow(self,n,now=None):
        t=time.monotonic() if now is None else now
        self.tokens=min(self.capacity,self.tokens+max(0,t-self.updated)*self.rate); self.updated=t
        if n>self.tokens: self.dropped=(self.dropped+1)&0xffff; return False
        self.tokens-=n; return True
class PriorityQueue:
    def __init__(self): self.items=[]; self.order=0
    def put(self,kind,frame,vfo=0): self.items.append((PRIORITY[kind],self.order,vfo,kind,frame)); self.order+=1
    def pop(self):
        if not self.items:return None
        idx=min(range(len(self.items)),key=lambda i:(self.items[i][0],self.items[i][1] if self.items[i][3]!='DOA' else self.items[i][2]))
        return self.items.pop(idx)[3:]
