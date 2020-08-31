#!/usr/bin/env python
import sys
import time
import queue
import numpy
import socket
import threading
import pycodec2
import multiprocessing

from .const import default_port
from .address import Address
from .frames import ipFrame
from .framer import M17_IPFramer
from .const import *
from .misc import example_bytes,_x


def networking_recv(aprecv_q):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", self.server[1]))
    # sock.setblocking(False)
    self.sock = sock
    while 1:
        try:
            #catch up if we get a burst
            x, conn = sock.recvfrom( encoded_buf_size ) 
            # print(conn)
            # print("Got: ",_x(x))
            f = ipFrame.from_bytes(x)
            aprecv_q.put(f.payload)
        except BlockingIOError as e:
            #nothing to read
            print(e)
            pass
        except Exception as e:
            raise(e)
            print(e)

def codec2setup(mode):
    c2 = pycodec2.Codec2( mode )
    conrate = c2.samples_per_frame()
    bitframe = c2.bits_per_frame()
    return [c2,conrate,bitframe]


def mic_audio(config,inq,outq):
    import soundcard as sc
    default_mic = sc.default_microphone()
    print(default_mic)
    with default_mic.recorder(samplerate=8000, channels=1) as mic:
        while 1:
            audio = mic.record(numframes=config.conrate)
            outq.put(audio)

def codec2enc(config,inq,outq):
    while 1:
        audio = inq.get()
        # assert len(audio) == config.conrate
        # if audio.dtype != numpy.int16:
            # audio = audio.astype(numpy.int16)
        # audio *= 2**15
        #audio from soundcard is floats from -1 to 1
        #these have to be multiplied such that they map from -32768:32767
        #this has to be done before astype, because astype is just a cast, e.g.
        #you then would have int16s with values -1,0,1
        audio = audio.flatten() * 32767
        audio = audio.astype("<h") 
        c2bits = config.c2.encode(audio)

        # assert len(c2bits) == config.bitframe/8
        outq.put(c2bits)

def m17frame(config,inq,outq):
    you = Address(callsign="SP5WWP")
    me = Address(callsign="W2FBI")
    print(you)
    print(me)
    framer = M17_IPFramer(
            dst=you,
            src=me,
            ftype=5, nonce=b"\xbe\xef"*8 )
    print("m17frame ready")
    while 1:
        d = inq.get() + inq.get() 
        #need 16 bytes for M17 payload, each element on q should be 8 bytes
        #TODO generalize to support other Codec2 sizes, and grab data until enough is here to send
        #TODO payload_stream needs to return packets and any unused data from the buffer to support that functionality
        pkts = framer.payload_stream(d)
        for pkt in pkts:
            outq.put(pkt)

def tobytes(config,inq,outq):
    print("tobytes ready")
    while 1:
        outq.put(bytes(inq.get()))

def networking_send(config,inq,outq):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    print("networking send ready")
    now = time.time()
    deadline = .02
    while 1:
        bs = inq.get()
        print(_x(bs))
        sock.sendto( bs, (config.server,config.port) )


class dattr(dict):
    def __getattr__(self,name):
        return self[name]

def modular_client():
    tx_chain = [mic_audio, codec2enc, m17frame, tobytes, networking_send]
    # rx_chain = [networking_recv, toframes, getpayload, codec2dec, spkr]
    rx_chain = []
    modules = {
            "_setup":[tx_chain, rx_chain]
            }
    c2,conrate,bitframe = codec2setup(3200)
    print("conrate, bitframe = [%d,%d]"%(conrate,bitframe) )
    config = dattr({
            "server":"localhost",
            "port":55533,
            "c2":c2,
            "conrate":conrate,
            "bitframe":bitframe,
            "queues":[]
            })
    """
    queues:
    n -> n2 -> n3 -> n4
    n has no inq
    n4 has no outq
    outq for n is inq for n2, etc
    for each chain:
        0 -> 1 -> 2 -> 3
          0    1     2
        if there's an old outq, inq=
        unless at end of chain, create an outq for each fn, outq=

    """
    for chainidx,chain in enumerate(modules["_setup"]):
        inq = None
        for fnidx,fn in enumerate(chain):
            print(fn.__name__)
            if fnidx != len(chain):
                outq = multiprocessing.Queue()
            else:
                outq = None
            process = multiprocessing.Process(target=fn, args=(config, inq, outq))
            modules[fn.__name__] = {
                    "inq":inq,
                    "outq":outq,
                    "process":process
                    }
            process.start()
            inq = outq




class Client:
    def __init__(self, mode, host, port=default_port, udp=False):
        self.loopback_test = 0

        self.server = (host,port)
        print("sending to: ",self.server)

        mic_q = multiprocessing.Queue()
        spkr_q = multiprocessing.Queue()
        apsend_q = multiprocessing.Queue()
        aprecv_q = multiprocessing.Queue()

        [conrate, bitframe] = self.setup_audio_processor(mode)

        self.audio_settings = self.setup_audio(mic_q, spkr_q, conrate)
        self.start_audio()

        self.networking = multiprocessing.Process(target=self.udp_networker, args=(apsend_q, aprecv_q))
        self.networking.start()

        self.audio_processor_out = multiprocessing.Process(target=self.audio_processor_worker_in, args=(aprecv_q, spkr_q) )
        self.audio_processor_out.start()
        self.audio_processor_in = multiprocessing.Process(target=self.audio_processor_worker_out, args=(mic_q, apsend_q) )
        self.audio_processor_in.start()

        self.qs = {
                "mic": mic_q,
                "spkr": spkr_q,
                "send": apsend_q,
                "recv": aprecv_q
                }


    def stop_audio(self):
        self.soundcard.stop()

    def start_audio(self):
        self.soundcard.start()

    
    def audio_processor_worker_in(self, aprecv_q, spkr_q):
        c2 = self.c2
        buf = b''
        bitframe = c2.bits_per_frame()
        byteframe = bitframe/8
        intbyteframe = int(byteframe)
        # print(bitframe, intbyteframe, byteframe)
        assert byteframe == intbyteframe
        while 1:
            buf += aprecv_q.get()
            c2_bits, buf = buf[0:intbyteframe], buf[intbyteframe:]
            if len(c2_bits) != byteframe:
                buf = c2_bits + buf
                print("c2 decode buffer underrun")
                continue
            wav = c2.decode( c2_bits )
            wav.reshape( (len(wav), 1)) 
            spkr_q.put( wav )

    def audio_processor_worker_out(self, mic_q, apsend_q):
        c2 = self.c2
        while 1:
            in_data = mic_q.get()
            c2_bits = c2.encode( in_data.flatten() )
            apsend_q.put(c2_bits)




    def tcp_networker(self, apsend_q, aprecv_q):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        def connect():
            print("connecting...")
            try:
                sock.connect( self.server )
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                print("connected")
            except ConnectionRefusedError as e:
                time.sleep(.5)
                return connect()
        connect()

        sock.setblocking(False)
        self.sock = sock
        while 1:
            # print("networker loop")
            if self.loopback_test == 2:
                aprecv_q.put( apsend_q.get() )
                continue
            try:
                d = apsend_q.get()
                sock.send( d )
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1) #I don't know if this is here for a reason, change it next time doing TCP
            except BrokenPipeError as e:
                print(e)
                connect()
            except ConnectionResetError as e:
                print(e)
                connect()
            except Exception as e:
                print(e)
                connect()
            # print("recv:")
            try:
                x = sock.recv(8)
                # print("Got: ",binascii.hexlify(x, b' ', -2))
                aprecv_q.put(x)
            except:
                pass

    def loop_forever(self):
        while 1:
            print("Q sizes")
            for k,v in self.qs.items():
                print(k, v.qsize())
            time.sleep(5)



def client(mode, host, port=default_port, proto="udp"):
    x = Client(mode=int(mode), host=host, port=int(port), udp=proto=="udp")
    x.loop_forever()

if __name__ == "__main__":
    client(*sys.argv[1:])
