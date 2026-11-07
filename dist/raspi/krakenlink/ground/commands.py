"""Validated command encoding and idempotent retry scheduler."""
import random, struct, time
import threading
from ..proto.frame import Frame
from ..proto.messages import CommandMessage
from ..proto.validate import GAIN_X10

OPS={1:4,2:2,3:11,4:2,5:1,6:3,7:1,8:0,9:4}
class CommandClient:
    def __init__(self, send, clock=time.monotonic, start_id=None):
        self.send=send; self.clock=clock; self.next_id=random.randrange(65536) if start_id is None else start_id&65535
        self.commands={}; self.seq=0; self.lock=threading.RLock()
    def validate(self,opcode,params):
        p=bytes(params)
        if opcode not in OPS or len(p)!=OPS.get(opcode):raise ValueError('invalid opcode or parameter length')
        if opcode==1:
            (x,)=struct.unpack('<I',p)
            if not 24000000<=x<=1766000000 or x%1000:raise ValueError('center frequency out of range')
        elif opcode==2:
            if struct.unpack('<H',p)[0] not in GAIN_X10:raise ValueError('gain is not supported')
        elif opcode==3:
            i,m,f,b,s=struct.unpack('<BBIIb',p)
            if i>15 or not m or m&~7 or (m&2 and b<100) or (m&4 and not -150<=s<=0):raise ValueError('VFO value out of range')
        elif opcode==4:
            c,o=struct.unpack('<BB',p)
            if not 1<=c<=16 or not (o==255 or o<c):raise ValueError('active VFO values out of range')
        elif opcode==5 and p[0]>5:raise ValueError('DOA method out of range')
        elif opcode==6:
            t,d=struct.unpack('<BH',p)
            if t>1 or not 20<=d<=2000:raise ValueError('array values out of range')
        elif opcode==7 and p[0] not in (0,1):raise ValueError('DOA enable must be 0 or 1')
        elif opcode==9:
            d,s=struct.unpack('<HH',p)
            if not 2<=d<=100 or s>20:raise ValueError('telemetry rate out of range')
        return p
    def submit(self,opcode,params=b'',cmd_id=None):
        p=self.validate(opcode,params)
        with self.lock:
            cid=self.next_id if cmd_id is None else cmd_id&65535
            if cmd_id is None:self.next_id=(cid+1)&65535
            now=self.clock(); c={'cmd_id':cid,'opcode':opcode,'params':p,'status':'pending','attempts':0,'created':now,'last_send':now,'accepted_at':None,'reason':None,'detail':0}
            self.commands[cid]=c; self._transmit(c,False); return cid
    def _transmit(self,c,retry):
        frame=Frame(0x10,self.seq,CommandMessage(c['cmd_id'],c['opcode'],c['params']).encode(),retry=retry).encode(); self.seq=(self.seq+1)&65535
        self.send(frame); c['attempts']+=1; c['last_send']=self.clock()
    def receive_ack(self,ack):
        with self.lock:
            c=self.commands.get(ack.cmd_id)
            if c is None:return False
            c['reason']=ack.reason; c['detail']=ack.detail
            if ack.result==0:c['status']='accepted'; c['accepted_at']=c['accepted_at'] or self.clock(); c['last_send']=self.clock()
            elif ack.result==1:c['status']='done'
            elif ack.result==4:c['status']='done_warn'
            elif ack.result==2:c['status']='nack'
            elif ack.result==3:c['status']='timeout'
            return True
    def tick(self):
        with self.lock:
            now=self.clock()
            for c in list(self.commands.values()):
                if c['status']=='pending':
                    if c['attempts']>=5 and now-c['last_send']>=1:c['status']='no_response'
                    elif now-c['last_send']>=1:self._transmit(c,True)
                elif c['status']=='accepted':
                    age=now-c['accepted_at']
                    if age>=40:c['status']='timeout'
                    elif now-c['last_send']>=3:self._transmit(c,True)
            return {cid:dict(command) for cid,command in self.commands.items()}
    def snapshot(self):
        with self.lock:
            return {cid:dict(command) for cid,command in self.commands.items()}
