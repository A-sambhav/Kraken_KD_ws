"""Bridge uplink health state machine and loss window."""
import collections, time
class LinkMonitor:
    LOST,UP,DEGRADED=2,0,1
    def __init__(self): self.state=self.LOST; self.events=collections.deque()
    def received(self,valid=True,now=None):
        t=time.monotonic() if now is None else now; self.events.append((t,bool(valid))); self._trim(t)
        if valid and self.state==self.LOST:self.state=self.UP
        self.update(t)
    def _trim(self,t):
        while self.events and self.events[0][0]<t-10:self.events.popleft()
    def update(self,now=None):
        t=time.monotonic() if now is None else now; self._trim(t)
        age=t-self.events[-1][0] if self.events else float('inf')
        loss=1-sum(v for _,v in self.events)/len(self.events) if self.events else 1
        if age>=10:self.state=self.LOST
        elif self.state==self.LOST:
            if self.events and self.events[-1][1]:self.state=self.UP
        elif age>=3 or (loss>.2 and len(self.events)>1):self.state=self.DEGRADED
        elif self.state==self.DEGRADED and age<3 and loss<.1:self.state=self.UP
        return self.state
