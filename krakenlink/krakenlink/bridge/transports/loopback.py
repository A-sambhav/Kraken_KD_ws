import socket
from .base import Transport
class LoopbackTransport(Transport):
    """UDP endpoint; peer is host:port, bind_host:bind_port are local."""
    def __init__(self,host='127.0.0.1',port=14560,bind_host='127.0.0.1',bind_port=14561,timeout=0):
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); self.sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); self.sock.bind((bind_host,bind_port)); self.sock.setblocking(False); self.peer=(host,int(port)); self.tx=0; self.rx=0; self.bad=0
    def send(self,frame):
        try:self.sock.sendto(bytes(frame),self.peer); self.tx+=1; return True
        except OSError:return False
    def recv(self):
        try:data,_=self.sock.recvfrom(2048); self.rx+=1; return data
        except BlockingIOError:return None
        except OSError:self.bad+=1; return None
    def stats(self):return {'tx':self.tx,'rx':self.rx,'bad':self.bad}
    def close(self):self.sock.close()
