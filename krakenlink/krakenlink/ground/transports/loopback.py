"""Ground-side UDP endpoint compatible with bridge LoopbackTransport."""
from ...bridge.transports.loopback import LoopbackTransport

class GroundLoopbackTransport(LoopbackTransport):
    def __init__(self,host='127.0.0.1',port=14561,bind_host='127.0.0.1',bind_port=14560):
        super().__init__(host,port,bind_host,bind_port)
