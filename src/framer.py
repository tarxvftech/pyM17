
from .address import Address
from .frames import *

class M17_RFFramer:
    def __init__(self, src:Address, dst:Address, ftype, nonce=None ):
        self.src = src
        self.dst = dst
        self.ftype = ftype
        self.nonce = nonce if nonce else b"\x00"*16
        self.packet_count = 0
        assert len(self.makeLICH()) == initialLICH.sz
        self.LICH = initialLICH(framer=self)

    def makeLICH(self):
        return bytes(initialLICH(framer=self))

    @classmethod
    def fromLICH(cls,data:bytes):
        d = initialLICH.dict_from_bytes( data )
        return cls( **d )

    def payload_stream( self, payload:bytes):
        LICH = self.LICH
        payloads = chunk( payload, regularFrame.payload_sz )
        pkts = []
        for p in payloads:
            if len(p) < regularFrame.payload_sz:
                p = p + b"\x00"*(regularFrame.payload_sz - len(p))
            pkt = regularFrame(LICH=LICH, frame_number=self.packet_count, payload=p)
            self.packet_count+=1
            if self.packet_count >= 2**16:
                self.packet_count = 0
            pkts.append(pkt)
        return pkts

class M17_IPFramer(M17_RFFramer):
    def payload_stream( self, payload:bytes):
        #only difference is which frame we use, ipFrame instead of regularFrame
        LICH = self.LICH
        payloads = chunk( payload, regularFrame.payload_sz )
        pkts = []
        for p in payloads:
            if len(p) < regularFrame.payload_sz:
                p = p + b"\x00"*(regularFrame.payload_sz - len(p))
            pkt = ipFrame(LICH=LICH, frame_number=self.packet_count, payload=p)
            self.packet_count+=1
            if self.packet_count >= 2**16:
                self.packet_count = 0
            pkts.append(pkt)
        return pkts
