
import bitstruct
from .address import Address
from .const import *
from .misc import *

class initialLICH:
    """
    16b  SYNC 0x3243 
    
    parts that get replicated in regularFrames:
        48b  Address dst
        48b  Address src
        16b  int(M17_Frametype)
        128b nonce (for encryption)

    [4b  tail (for convenc)]
    """
    sz = int((16+48+48+16+128)/8)
    def __init__(self, 
            framer=None, 

            src:Address=None, 
            dst:Address=None,
            ftype=None,
            nonce=None):

        if framer:
            self.framer = framer
            self.src = framer.src
            self.dst = framer.dst
            self.ftype = framer.ftype
            self.nonce = framer.nonce
        else:
            self.src = src
            self.dst = dst
            self.ftype = ftype
            self.nonce = nonce if nonce else b"\x00"*16

    def __str__(self):
        return "LICH: " + self.src.callsign + " =[%d]> "%(self.ftype) + self.dst.callsign

    def __bytes__(self):
        b = SYNC
        b += bitstruct.pack("u48",self.framer.dst.addr)
        b += bitstruct.pack("u48",self.framer.src.addr)
        b += bitstruct.pack("u16",self.framer.ftype)
        b += self.framer.nonce
        return b

    def chunks(self):
        me = bytes(self)[2:] #skip the SYNC for making chunks to be replicated 
        return chunk( me, 6)

    @staticmethod
    def from_bytes(data:bytes):
        d = initialLICH.dict_from_bytes(data)
        return initialLICH(**d)

    @staticmethod
    def dict_from_bytes(data:bytes):
        """
        expects to have SYNC already stripped
        """
        d = {}
        # assert data[0:2] == SYNC
        # data = data[2:]
        d["dst"], d["src"], d["ftype"] = bitstruct.unpack("u48u48u16", data[:14])
        d["dst"] = Address(addr=d["dst"])
        d["src"] = Address(addr=d["src"])
        d["nonce"] = data[14:14+16]
        return d

    @staticmethod
    def recover_bytes_from_bytes_frames( bytes_frames:list):
        frames = [ regularFrame.dict_from_bytes(b) for b in bytes_frames ]
        #frame number gives us the idea of which part of the LICH we have in it
        #assuming that the first regular frame has the first part of the lich
        #per the spec
        #so we really just need one each of the "numbers on the clock"
        #so we could do this better by taking in packets and returning a LICH once 
        #each spot is filled, which might be more robust

        #code below assumes there's a solution in the frames, that there's only one frame
        #for each spot on the "clock", etc, so it will be fragile with real RF

        idx_frame_number = [ (frames.index(x), x["frame_number"]) for x in frames]
        # idx_frame_number = [ (0,9),(1,10),(2,11),(3,12),(4,13) ]
        #reorder so fn%5 == 0 is first
        # print( list(map( lambda x: x, idx_frame_number) ) )
        zeroth_chunk = list(map( lambda x: x[1]%5 == 0, idx_frame_number)).index(True)
        # print(zeroth_chunk)
        reordered = frames[zeroth_chunk:] + frames[0:zeroth_chunk]
        # print(reordered)
        b=b""
        for p in reordered:
            b += p["lich_chunk"]
        return b


class regularFrame:
    """
    16b  SYNC 0x3243 (not counted in size)
    48b  LICH chunk
    16b  Frame number counter
    128b payload
    16b  CRC-16 chksum

    4b   tail (convenc) (not implemented here)
    """
    sz = int((16+48+16+128)/8)
    lich_chunk_sz = int(48/8);
    payload_sz = int(128/8)
    def __init__(self, frame_number, payload, LICH:initialLICH=None, lich_chunk:bytes=None):
        """
        Can instantiate with either a full LICH object or just a lich_chunk 
        """
        self.LICH = LICH
        self.lich_chunk = lich_chunk
        self.frame_number = frame_number
        self.payload = payload
        if self.LICH:
            self.LICH_chunks = self.LICH.chunks()

    def __str__(self):
        return "M17[%d]: %s"%(self.frame_number,_x(self.payload))

    def __bytes__(self):
        b=SYNC
        if self.LICH:
            lich_chunk_idx = self.frame_number % 5; 
            assert len(self.LICH_chunks[lich_chunk_idx]) == 48/8
            b += self.LICH_chunks[lich_chunk_idx]
        else:
            b += self.lich_chunk
        b += bitstruct.pack("u16", self.frame_number)
        b += bytes(self.payload)
        b += bytes([0]*2) #crc16
        # b += bitstruct.pack("u4",0)
        return b

    @staticmethod
    def from_bytes(data:bytes):
        d = regularFrame.dict_from_bytes(data)
        return regularFrame(**d)

    @staticmethod
    def dict_from_bytes(data:bytes):
        """
        Expects to have had SYNC 16b already stripped
        """
        d = {}
        # assert data[0:2] == SYNC
        # data = data[2:]
        d["lich_chunk"] = data[0:6]
        d["frame_number"]= bitstruct.unpack("u16", data[6:8])[0]
        d["payload"] = data[8:8+16]
        #ignore the CRC, if we're over TCP that's covered anyway
        # d["chksum"] = bitstruct.unpack("u16", data[8+16:8+16+2])[0]
        return d

def is_LICH( b:bytes ):
    """
    No real way to tell other than size with the implementation in this file
    in RF, they would be the same size
    """
    return len(b) in [initialLICH.sz, initialLICH.sz-2]
class M17_Frametype(int):

    """
    low bits v high bits
    stream?
    data?
    voice?
    non-codec2?
    non-3200bps?
    2b: encryption-type
    2b: encryption-subtype
    remaining of 16: reserved
    codec2 3200bps voice stream 00101
    """
    fields = [
            (1, "is_stream"),
            (1, "has_data"),
            (1, "has_voice"),
            (1, "non_codec2"),
            (1, "non_3200bps"),
            (2, "enc_type"),
            (2, "enc_subtype"),
            (7, "reserved"),
            ]
