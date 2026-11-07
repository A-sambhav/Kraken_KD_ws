class Transport:
    def send(self,frame): raise NotImplementedError
    def recv(self): raise NotImplementedError
    def stats(self): return {}
    def close(self): pass
