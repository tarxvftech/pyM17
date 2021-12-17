import logging
import bitstruct
import binascii

import re
import unittest

try:
    from .frames import ipFrame, initialLICH
    from .const import *
    from .misc import _x, chunk, example_bytes
except:
    from frames import ipFrame, initialLICH
    from const import *
    from misc import _x, chunk, example_bytes

class M17_Stream():
    #could inherit from list, but ... nah
    #having done that on another project i think it's easier to reason about by having, not being
    #especially when coming back to it later
    def __init__(self):
        raise(NotImplementedError)

class M17_IPStream(M17_Stream):
    """
    This is not meant, despite the name (sorry, still can't think of a
    better name) for consuming real time streams. You want to use frames
    for that.

    This is meant to group frames as they fly by into chunks for post
    processing, like storage or archiving or voice transcription.

    It also includes a slightly smaller way of representing streams
    using a so-far-non-standard (because there is no standard) stream
    byte format for writing to disk.

    """
    log = logging.getLogger('M17_IPStream')
    bytesheader = b"M17Stream"
    def __init__(self, *args, **kwargs):
        #super().__init__(*args,**kwargs)
        self.LICH = None
        self.frames = []
        if len(args):
            self.set_frames( args )
        if len(self.frames):
            self.set_lich(self.frames[0].LICH)

    def __str__(self):
        return "M17_IPStream[%04x,%d] %s"%(self.streamid, len(self),str(self.LICH))

    def __bytes__(self):
        """
        """
        b = self.bytesheader #so it can be distinct from other M17 file formats

        #these parts for later use
        version = 0
        b += bitstruct.pack("u16", version)

        b += bitstruct.pack("u16", self.streamid)
        b += bytes(self.LICH)
        b += bitstruct.pack("u16", len(self)) 
        for f in self.frames:
            b += bitstruct.pack("u16", f.frame_number)
            b += bytes(f.payload)
        return b

    def get_payloads(self):
        return list(map(lambda x: x.payload, self.frames))

    @classmethod
    def from_bytes(cls,data:bytes):
        me = cls()
        hdr = cls.bytesheader
        assert data[:len(hdr)] == hdr
        offset = len(hdr)

        version = bitstruct.unpack("u16", data[offset:offset+2])[0]
        assert version == 0
        offset += 2 #skip version

        sid = bitstruct.unpack("u16", data[offset:offset+2])[0]
        offset += 2

        lichsz = initialLICH.sz
        lich = initialLICH.from_bytes(data[offset:offset+lichsz])
        offset += lichsz

        me.set_streamid(sid)
        me.set_lich(lich)
        numframes = bitstruct.unpack("u16", data[offset:offset+2])[0]
        offset += 2
        fnsz = ipFrame.fnsz
        paysz = ipFrame.payloadsz
        for i in range(numframes):
            frame_number = bitstruct.unpack("u16",data[offset:offset+fnsz] )[0]
            offset += fnsz
            payload = data[offset:offset+paysz]
            offset += paysz
            frame = ipFrame(
                    streamid=sid,
                    frame_number=frame_number,
                    payload=payload,
                    LICH=lich,
                    )
            me.add_frame(frame)
        return me

    def set_lich(self, lich):
        self.LICH = lich
    def set_streamid(self, sid):
        self.streamid = sid

    def add_frame(self, frame):
        self.frames.append(frame)

    def set_frames(self, frames):
        self.frames = frames
        self.set_lich(frames[0].LICH)
        self.set_streamid(frames[0].streamid)


    def __len__(self):
        return len(self.frames)
    def __getitem__(self, key):
        return self.frames[key]

    @classmethod
    def from_frames(cls,frames:list):
        """
        Expects a list of ipFrames that are to be grouped together.
        We might sanity check it and log warnings if they're not supposed
        to be part of the same stream, but it's on you to actually group
        them together.
        """
        assert( len(frames) > 0 )
        sids = set(map(lambda x:x.streamid, frames))
        print("SIDS:",sids)
        if len(sids) > 1:
            cls.log.warning("More than one stream id when making stream from frames")
        s = cls()
        s.set_frames(frames)
        return s


class testStreams(unittest.TestCase):
    def setUp(self):
        self.bs = []
        x="""
        4d31 3753 7472 6561 6d00 0011 9e00 1314
        31ae 1f9a f8db 61ae 1f00 0535 021e 02eb
        01f8 0115 0225 024d 0200 0300 00ca 84c3
        4258 97a9 2e88 64ee fada 4d30 8d00 0142
        bc6c da9e a6a4 eac1 9c25 465e c521 ed80
        02c8 8c26 4e5a f42d cace b86d db9c e427
        08
        """
        x = re.sub(r"\s+","",x)
        self.bs.append(binascii.unhexlify(x))
        x="""
        4d31 3753 7472 6561 6d00 00f1 6900 1314
        31ae 1f9a f8db 61ae 1f00 05de 012a 02da
        0199 0190 0152 0134 0100 0a00 0041 10e6
        d29e df3d e5c8 1c66 4e1e d561 ae00 01c1
        8c22 5eda e725 a9c2 8022 ce1c ccbd 6a00
        02c0 0022 e29c e5a9 a9c0 0002 e25a a7e1
        af00 03c0 0006 ab9c fc29 49c0 0002 aa94
        f721 c800 04c2 0002 e394 e5a9 c9c0 0026
        a3d6 dc29 ef00 05c7 8027 a39e e439 0dc3
        8027 ea9c e435 0e00 06c1 8026 fb96 e4a9
        6fc3 b46b fade 4f15 ac00 0747 38e2 f21e
        c4ac eec8 0843 76dc cc2d 8f00 08c7 84c1
        c21c d4e1 ca47 e8ea d2da cdb0 8f80 0953
        34c5 cade d439 acd2 b8e7 d394 cf29 39  
        """
        x = re.sub(r"\s+","",x)
        self.bs.append(binascii.unhexlify(x))
    def testFromToBytes(self):
        for bs in self.bs:
            x = M17_IPStream.from_bytes(bs)
            self.assertEqual(bytes(x),bs)
    def testFromBytesGetPayloads(self):
        for bs in self.bs:
            x = M17_IPStream.from_bytes(bs)
            for p in x.get_payloads():
                self.assertEqual(len(p), 16)

