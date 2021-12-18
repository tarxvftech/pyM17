#!/usr/bin/env python

from m17.address import Address
import m17.misc as misc
import scapy
import scapy.all as s
import scapy.packet as sp
import scapy.fields as sf
import scapy.contrib.coap as scoap
import scapy.contrib.mqtt as smqtt
import binascii
from scapy.compat import List, Union
from scapy.modules.six import integer_types

#post-payload field support in scapy 
# https://github.com/secdev/scapy/issues/1021
# https://github.com/secdev/scapy/blob/11832deee0067e1db2660ff1f61e5d4e979adf27/scapy/fields.py#L641

#TODO: M17 type 1 bits, M17 type 4 bits, X25, AX25, APRS, MQTT-SN
#https://m17-protocol-specification.readthedocs.io/en/latest/
#https://www.oasis-open.org/committees/download.php/66091/MQTT-SN_spec_v1.2.pdf
# 6lowpan: https://en.wikipedia.org/wiki/6LoWPAN

class X25(sp.Packet):
    #https://en.wikipedia.org/wiki/X.25
    pass
class AX25(sp.Packet):
    #https://www.tapr.org/pdf/AX25.2.2.pdf
    pass
class APRS(sp.Packet):
    #http://www.aprs.org/doc/APRS101.PDF
    pass


class BENBytesField(sf.Field[int, List[int]]):
    """Because I need the internal representation to be big endian to
    be easier to work with, and sf.NBytesField parses as little endian
    for some reason
    """
    def __init__(self, name, default, sz):
        # type: (str, Optional[int], int) -> None
        super().__init__(name, default, "<" + "B" * sz)

    def i2m(self, pkt, x):
        if isinstance(x, bytes):
            return x
        if isinstance(x, str):
            return x.encode("utf-8")
        return int.to_bytes(x, self.sz, "big")

    def m2i(self, pkt, x):
        # type: (Optional[Packet], Union[List[int], int]) -> int
        if isinstance(x, int):
            return x
        # x can be a tuple when coming from struct.unpack  (from getfield)
        if isinstance(x, (list, tuple)):
            return int.from_bytes( x, "big", signed=False)
        return 0

    def i2repr(self, pkt, x):
        # type: (Optional[Packet], int) -> str
        if isinstance(x, integer_types):
            return '%i' % x
        return super().i2repr(pkt, x)

    def addfield(self, pkt, s, val):
        # type: (Optional[Packet], bytes, Optional[int]) -> bytes
        return s + self.struct.pack(*self.i2m(pkt, val))

    def getfield(self, pkt, s):
        # type: (Optional[Packet], bytes) -> Tuple[bytes, int]
        return (s[self.sz:],
                self.m2i(pkt, self.struct.unpack(s[:self.sz])))  # type: ignore


class M17Addr( sf.Field[Union[str,int], bytes] ):
    addrsize=6
    def __init__(self, name, default):
        if isinstance(default, str):
            default= Address.encode(default)
        #else its an int
        super().__init__(name, default, "<"+"B"*self.addrsize);

    def h2i(self,pkt,x):
        if isinstance(x, int):
            return x
        if isinstance(x, str):
            return Address.encode(x)
        raise(Exception("Invalid type"))
        

    def i2repr(self, pkt, x):
        return "'%s'"%(Address.decode(x))

    def i2m(self, pkt, x):
        return int.to_bytes(x, self.addrsize, "big")

    def m2i(self, pkt, x):
        if isinstance(x, int):
            return x
        if isinstance(x, str):
            return Address.encode(x)
        # x can be a tuple when coming from struct.unpack  (from getfield)
        if isinstance(x, (list, tuple)):
            return int.from_bytes( x, "big", signed=False)
        return 0

    def addfield(self, pkt, s, val):
        # type: (Optional[Packet], bytes, Optional[int]) -> bytes
        return s + self.struct.pack(*self.i2m(pkt, val))

    def getfield(self, pkt, s):
        # type: (Optional[Packet], bytes) -> Tuple[bytes, int]
        return (s[self.sz:],
                self.m2i(pkt, self.struct.unpack(s[:self.sz])))  # type: ignore

class M17PacketType(sp.Packet):
    """
    0 	Packet/stream indicator, 0=packet, 1=stream
    1..2 	Data type indicator, 012 =data (D), 102 =voice (V), 112 =V+D, 002 =reserved
    3..4 	Encryption type, 002 =none, 012 =AES, 102 =scrambling, 112 =other/reserved
    5..6 	Encryption subtype (meaning of values depends on encryption type)
    7..10 	Channel Access Number (CAN)
    11..15 	Reserved (don’t care)
    """
    fields_desc = [
            sf.BitField('_resv',0,5 ),
            sf.BitField('can',0,4 ),
            sf.BitField('encsubtype',0,2 ),
            sf.BitField('enctype',0,2 ),
            sf.BitEnumField('datamode',0,2, {0:"_resv",1:"D",2:"V",3:"V+D"}),
            sf.BitEnumField('frametype',0,1, {0:"packet",1:"stream"}),
            ]

class M17LSF(sp.Packet):
    #needs syncs or other marker to distinguish 
    #between LSF and data frames
    name = "M17LSF"
    fields_desc = [
            M17Addr('dst', ""), #can be either way
            M17Addr('src', 0x0),
            M17PacketType, #16 bits
            # sf.ShortField('streamtype',0),
            BENBytesField('meta',0,14),
            ]
class M17LSFandCRC(sp.Packet):
    #not implemented yet
    name = "M17LSFandCRC"
    fields_desc = [
            M17LSF,
            # sf.FCSField('crc',0) 
            ]

class M17RF(sp.Packet):
    #not implemented yet
    #needs syncs or other marker to distinguish 
    #between LSF and data frames
    name = "M17StreamFrame"
    fields_desc = [
            BENBytesField('lsfchunk', 0, 6),
            sf.ShortField('fn',0),
            BENBytesField('data', 0, 16),
            ]

class DVRef(sp.Packet):
    name = "DVRef"
    magic_enum = {
            b"CONN":"connect",
            b"ACKN":"success",
            b"NACK":"failure",
            b"PING":"ping",
            b"PONG":"pong",
            b"DISC":"disconnect",
            b"M17 ":"M17",
            }
    fields_desc = [
            s.StrFixedLenEnumField('magic', b"CONN", 4, magic_enum),
            s.ConditionalField(
                M17Addr('callsign', 0x0), 
                lambda pkt: pkt.magic in [ b"CONN", b"PING", b"PONG", b"DISC" ]
                ),
            s.ConditionalField(
                s.XByteField('module', 0x0), 
                lambda pkt: pkt.magic == b"CONN"
                ),
            ]

    def mysummary(self):
        mysum = self.undersummary() + self.sprintf("DVRef %DVRef.magic%")
        if self.magic in [ b"CONN", b"PING", b"PONG", b"DISC" ]:
            #disc only sometimes has callsign - only when requesting
            #a disc, not acking one. no way to tell which is which on a
            #per-packet basis.
            mysum += self.sprintf(" %DVRef.callsign%")
        if self.magic == b"CONN":
            mysum += self.sprintf(" > %DVRef.module%")
        return mysum

    def undersummary(self):
        mysum = ""
        if isinstance(self.underlayer.underlayer, s.IP) and isinstance(self.underlayer, s.UDP):
            mysum += self.underlayer.underlayer.sprintf("%IP.src%:%UDP.sport% > %IP.dst%:%UDP.dport% ")
        elif isinstance(self.underlayer.underlayer, s.IPv6) and isinstance(self.underlayer, s.UDP):
            mysum += self.underlayer.underlayer.sprintf("%IPv6.src%:%UDP.sport% > %IPv6.dst%:%UDP.dport% ")
        elif isinstance(self.underlayer, s.UDP):
            mysum += self.underlayer.sprintf("%UDP.sport% > %UDP.dport% ")
        return mysum
        

class M17IP(sp.Packet):
    name = "M17IP"
    fields_desc = [
            # BENBytesField('magic', b"M17 ", 4),
            sf.XShortField('sid',0),
            M17LSF, #but no CRC on IP LICHs - or maybe any LICHs
            #now that's just magic, ain't it? (embedding a full packet as a field)
            sf.XShortField('fn',0), #if high bit set, this is last packet
            # sf.ShortField('crc',0), 
            sf.FCSField('crc',0) 
            ]
    def mysummary(self):
        mysum = self.undersummary()
        # mysum = self.sprintf("M17[%M17IP.sid%, %M17IP.frametype%/%M17IP.datamode%, %M17IP.fn%] ")
        mysum += self.sprintf("M17[%M17IP.sid%, %M17IP.fn%] ")
        mysum += self.sprintf("%M17IP.src% > %M17IP.dst% ")
        return mysum

    def undersummary(self):
        mysum = ""
        if isinstance(self.underlayer, DVRef):
            mysum += self.underlayer.undersummary()
        elif isinstance(self.underlayer.underlayer, s.IP) and isinstance(self.underlayer, s.UDP):
            mysum += self.underlayer.underlayer.sprintf("%IP.src%:%UDP.sport% %M17IP.src% > %IP.dst%:%UDP.dport% %M17IP.dst%")
        elif isinstance(self.underlayer.underlayer, s.IPv6) and isinstance(self.underlayer, s.UDP):
            mysum += self.underlayer.underlayer.sprintf("%IPv6.src%:%UDP.sport% %M17IP.src% > %IPv6.dst%:%UDP.dport% %M17IP.dst%")
        elif isinstance(self.underlayer, s.UDP):
            mysum += self.underlayer.sprintf("%UDP.sport% %M17IP.src% > %UDP.dport% %M17IP.dst% ")
        return mysum


class C2_3200(sp.Packet):
    name = "C2_3200"
    fields_desc = [
            BENBytesField('data', 0, 16),
            ]


class UTFStyleIntField( sf.Field[int, bytes] ):
# class UTFStyleIntField( sf.Field[Union[str,int], bytes] ):
#maybe support protocol names as a string?

    def i2m(self, pkt, x):
        return misc.encode_utf_style_int(x)

    def m2i(self, pkt, x):
        blen,val = misc.parse_utf_style_int(x)
        return val

    def addfield(self, pkt, s, val):
        return s + self.i2m(pkt,val)

    def getfield(self, pkt, s):
        blen,val = misc.parse_utf_style_int(s)
        return (s[blen:], val)

class M17PacketModeDataType(UTFStyleIntField):
    pass

class M17PacketModeFrame(sp.Packet):
    name = "M17PacketModeFrame"
    fields_desc = [
            M17PacketModeDataType('proto',0),
            #payload
            ]
class M17SMS(s.Raw):
    name = "M17SMS"
    fields_desc = [
            s.StrField("msgbody", "Hello World!")
            ]
    def mysummary(self):
        return self.underlayer.underlayer.sprintf("%M17IP.src% > %M17IP.dst%: %msgbody%")

#bind_layers can only bind using keys from the low layer (e.g. UDP fields when binding UDP and DVRef)
s.bind_layers(M17IP, C2_3200, frametype=1, datamode=2)
s.bind_layers(M17IP, M17PacketModeFrame, frametype=0)
s.bind_layers(M17PacketModeFrame, s.Raw, proto=0x0)
s.bind_layers(M17PacketModeFrame, AX25, proto=0x1)
s.bind_layers(M17PacketModeFrame, APRS, proto=0x2)
# s.bind_layers(M17PacketModeFrame, sixlowpan, proto=0x3)
s.bind_layers(M17PacketModeFrame, s.IP, proto=0x4)
s.bind_layers(M17PacketModeFrame, M17SMS, proto=0x5)
# s.bind_layers(M17PacketModeFrame, Winlink, proto=0x6)

#raw M17, no reflector - can be enabled safely, but won't be default
#i don't think (2021 12 17) anyone out there did raw M17 but me with this python, so keeping disabled for now
# s.bind_layers(s.UDP, M17IP, sport=17000)
# s.bind_layers(s.UDP, M17IP, dport=17000)
# s.bind_layers(s.UDP, M17IP, dport=17000, sport=17000) 

#with reflector
s.bind_layers(s.UDP, DVRef, dport=17000)
s.bind_layers(s.UDP, DVRef, sport=17000)
s.bind_layers(s.UDP, DVRef, sport=17000,dport=17000) #last one is the default when creating packets
s.bind_layers(DVRef, M17IP, magic=b"M17 ")


if __name__ == "__main__":
    # lsfb = b"\x00\x00\x01\x61\xAE\x1F\x00\x00\x01\x61\xAE\x1F\x00\x05"
    # lsf = M17LSF(_pkt=lsfb)
    # lsf = M17LSF(dst="SP5WWP",src="W2FBI")
    # lsf.show()
    # ip = M17IP(
            # sid=0xbeef,
            # dst="KC1AWV",
            # src="W2FBI",
            # frametype="stream",
            # datamode="V+D",
            # enctype=0,
            # encsubtype=0,
            # can=2,
            # meta=b'C'*14,
            # fn=0x3,
            # crc=0xffff
            # ) / ("A"*8 + "B"*8)
    # ip.show()
    # scapy.utils.hexdump(ip)

    # encap = M17PacketModeFrame()/s.IP()/s.UDP()/scoap.CoAP()
    # encap.show()
    # scapy.utils.hexdump(encap)

    # encap = M17PacketModeFrame()/s.IP()/s.UDP()/smqtt.MQTT()/smqtt.MQTTPublish(topic='#',value='hello world')
    # encap.show()
    # scapy.utils.hexdump(encap)


    # encap = M17PacketModeFrame()/M17SMS("ABCDEF")
    # encap.show()
    # scapy.utils.hexdump(encap)

    # encap = M17PacketModeFrame(_pkt=b"\x05ABCDEF")
    # encap.show()
    # scapy.utils.hexdump(encap)
    # examples = [
            # s.IP(dst="0.0.0.1",src="0.0.0.2")/s.UDP(sport=17000,dport=17000)/DVRef(magic="CONN"),
            # s.IP(dst="0.0.0.2",src="0.0.0.1")/s.UDP(sport=17000,dport=17000)/DVRef(magic="ACKN"),
            # s.IP(dst="0.0.0.1",src="0.0.0.2")/s.UDP(sport=17000,dport=17000)/DVRef()/M17IP(),
            # ]
    # for p in examples:
        # print(p.summary())
    # for p in examples:
        # P = s.IP(_pkt=bytes(p))
        # print(P.summary())
    # import pdb; pdb.set_trace()

    # x=s.IP()/s.UDP()/DVRef()/M17IP()/M17PacketModeFrame()/M17SMS()
    # print(x)
    # print(x.summary())
    # print(x.show())
    # import pdb; pdb.set_trace()


    while 1:
        a=s.sniff(filter="udp and port 17000",timeout=2)
        a.summary()
    # a = s.rdpcap("scapy_test.pcapng")
    # a.summary()

