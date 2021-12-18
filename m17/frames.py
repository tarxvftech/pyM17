
import logging
import bitstruct
try:
    from .address import Address
    from .const import *
    from .misc import _x, chunk, example_bytes
except:
    from address import Address
    from const import *
    from misc import _x, chunk, example_bytes

crc_table = []

#crc stuff lifted gratefully from n7tae's mrefd
crc_poly=0x5935
crc_start=0xFFFF
def crc_init():
    for i in range(256):
        crc = 0
        c = i << 8
        for j in range(8):
            if (crc ^ c) & 0x8000:
                crc = ( crc << 1 ) ^ crc_poly;
            else:
                crc = crc << 1;
            c = c << 1;
        crc_table.append(crc)

def crc(data:bytes):
    crc = crc_start
    for a in range(len(data)):
        crc = (crc << 8) ^ crc_table[ ((crc >> 8) ^ data[a]) & 0x00FF ];
    return (crc & 0xffff)

crc_init()
assert crc(b"") == 0xffff
assert crc(b"A") == 0x206e
assert crc(b"123456789") == 0x772b

class initialLICH:
    """
    parts that get replicated in regularFrames:
        48b  Address dst
        48b  Address src
        16b  int(M17_streamtype)
        112b nonce (for encryption)
        #if actually sent on RF, needs a 16bit CRC also
    """
    sz = int((48+48+16+112)/8)
    def __init__(self, 
            src:Address=None, 
            dst:Address=None,
            streamtype=None,
            nonce=None):

        self.src = src
        self.dst = dst
        self.streamtype = streamtype
        if nonce:
            self.nonce = nonce 
        else:
            self.nonce = b"\x00"*14
        assert len(self.nonce) == 14

    def __eq__(self, other):
        return bytes(self) == bytes(other)
        # for name in ["src","dst","streamtype","nonce"]:
            # x = getattr(self,name)
            # y = getattr(other,name)
            # z = x == y
            # print(z,x,y) 


    def __str__(self):
        return "'"+self.src.callsign + "' =[%d]> '"%(self.streamtype) + self.dst.callsign + "'"

    def __bytes__(self):
        b = b""
        b += bitstruct.pack("u48",self.dst.addr)
        b += bitstruct.pack("u48",self.src.addr)
        b += bitstruct.pack("u16",self.streamtype)
        b += self.nonce
        assert len(self.nonce) * 8 == 112
        assert len(b) == self.sz
        # b += b"\x00\x00"
        return b
    

    def chunks(self):
        me = bytes(self)
        return chunk( me, 6)

    @staticmethod
    def from_bytes(data:bytes):
        d = initialLICH.dict_from_bytes(data)
        return initialLICH(**d)

    @staticmethod
    def dict_from_bytes(data:bytes):
        d = {}
        d["dst"], d["src"], d["streamtype"] = bitstruct.unpack("u48u48u16", data[:14])
        d["dst"] = Address(addr=d["dst"])
        d["src"] = Address(addr=d["src"])
        d["nonce"] = data[14:14+14]

        embedded_crc = data[28:30]
        #currently ignores two bytes crc, will accept even with bad crc

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
    48b  LICH chunk
    16b  Frame number counter
    128b payload
    16b  CRC-16 chksum
    """
    sz = int((48+16+128)/8)
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
    def isLastFrame(self):
        """
        high bit of 16 bit frame number indicates last frame
        """
        # print("Frame number: ", hex(self.frame_number))
        return self.frame_number & (1<<15)

    def __eq__(self, other):
        return bytes(self) == bytes(other)

    def __str__(self):
        return "M17[%d]: %s"%(self.frame_number,_x(self.payload))

    def __bytes__(self):
        b=b""
        if self.LICH:
            lich_chunk_idx = self.frame_number % 5; 
            assert len(self.LICH_chunks[lich_chunk_idx]) == 48/8
            b += self.LICH_chunks[lich_chunk_idx]
        else:
            b += self.lich_chunk
        b += bitstruct.pack("u16", self.frame_number)
        b += bytes(self.payload)
        b += crc(b).to_bytes(2,"big")
        return b

    @classmethod
    def from_bytes(cls,data:bytes):
        d = cls.dict_from_bytes(data)
        return cls(**d)

    @staticmethod
    def dict_from_bytes(data:bytes):
        d = {}
        d["lich_chunk"] = data[0:6]
        d["frame_number"]= bitstruct.unpack("u16", data[6:8])[0]
        d["payload"] = data[8:8+16]
        #ignore the CRC, it's not implemented yet
        # d["chksum"] = bitstruct.unpack("u16", data[8+16:8+16+2])[0]
        return d



class ipFrame(regularFrame):
    """
    32b "M17 " 
    16b  StreamID
    ?    Full LICH bytes (minus CRC)
    16b  Frame number counter
    128b payload
    16b  CRC-16 chksum
    """
    magicsz = 4
    streamidsz = 2 #bytes
    fnsz = 2 #bytes
    payloadsz = 16 #bytes
    sz = magicsz+streamidsz+initialLICH.sz+fnsz+payloadsz+2 #bytes
    def __init__(self, *args, **kwargs):
        self.streamid = kwargs.pop('streamid',0x0)
        super().__init__(*args,**kwargs)
        if not self.LICH:
            raise(Exception("ipFrames need a full LICH passed"))

    def __str__(self):
        return "SID[%04x] "%(self.streamid) + str(self.LICH) + " fn%05d: %s"%(self.frame_number,_x(self.payload))

    def __bytes__(self):
        b=b""
        b += b"M17 "
        b += bitstruct.pack("u16", self.streamid)
        b += bytes(self.LICH)
        b += bitstruct.pack("u16", self.frame_number)
        b += bytes(self.payload)
        b += crc(b).to_bytes(2,"big")
        if self.LICH.streamtype == 5:
            assert self.sz == len(b)
        return b

    @staticmethod
    def is_m17(data:bytes):
        return data[0:4] == b"M17 "

    @staticmethod
    def dict_from_bytes(data:bytes):
        assert ipFrame.is_m17(data)
        d = {}
        d["streamid"]= bitstruct.unpack("u16", data[4:6])[0]
        lich_start = 6
        lich_end = lich_start+initialLICH.sz
        d["LICH"] = initialLICH.from_bytes(data[lich_start:lich_end])
        d["frame_number"]= bitstruct.unpack("u16", data[lich_end:payload_start])[0]
        payload_start = lich_end+2
        if d["LICH"].streamtype == 5:
            payload_end = payload_start+16
        else:
            payload_end = len(data)-2
        d["payload"] = data[payload_start:payload_end]
        embedded_crc = data[payload_end:payload_end+2]
        if crc(data) != 0:
            logging.warning("invalid CRC")
        # d["crc"] = bitstruct.unpack("u16", ...
        return d

def is_LICH( b:bytes ):
    """
    No real way to tell other than size with the implementation in this file
    in RF, they would be the same size
    """
    return len(b) == initialLICH.sz

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
standard_voice_stream = 5
standard_data_packet = 2
