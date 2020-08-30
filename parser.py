
from .frames import regularFrame, initialLICH, is_LICH
from .const import *
from .misc import *

class M17_Parser:
    b=b""
    frames = []
    def in_bytes(self,data:bytes):
        # all data between SYNCs is assumed to be a good frame for now
        if SYNC in data:
            pkts = data.split(SYNC)
            for bpkt in pkts:
                if len(bpkt) == 0:
                    continue
                if len(bpkt) == regularFrame.sz:
                    f = regularFrame.from_bytes(bpkt)
                    self.frames.append(f)
                    # print(f)
                elif is_LICH(bpkt):
                    f = initialLICH.from_bytes(bpkt)
                    self.LICH = f
                    # print(f)
                else:
                    print("Invalid data, not a known packet", _x(bpkt))
                    import pdb; pdb.set_trace()
        else:
            self.b += data

    def out_c2_frames(self):
        if len(self.frames) <= 200: 
            #TODO we're running slowly, so store some up so it plays back without stuttering for demo purposes
            return []
        fs = self.frames
        self.frames = []
        c2_payloads = [f.payload for f in fs]
        return c2_payloads

