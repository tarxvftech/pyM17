#!/usr/bin/env python
import sys
import time
import queue
import numpy
import socket
import threading
import pycodec2
import pysoundcard
import multiprocessing

from .const import default_port
from .address import Address
from .frames import ipFrame
from .framer import M17_IPFramer
from .const import *
from .misc import example_bytes,_x


class Client:
    def __init__(self, mode, host, port=default_port, udp=False):
        self.loopback_test = 0

        self.server = (host,port)
        print("sending to: ",self.server)

        mic_q = queue.Queue()
        spkr_q = queue.Queue()

        apsend_q = queue.Queue()
        aprecv_q = queue.Queue()

        [conrate, bitframe] = self.setup_audio_processor(mode)
        print("conrate, bitframe = [%d,%d]"%(conrate,bitframe) )
        self.audio_settings = self.setup_audio(mic_q, spkr_q, conrate)
        self.soundcard.start()
        if udp:
            self.networking = threading.Thread(target=self.udp_networker, args=(apsend_q, aprecv_q))
        else:
            self.networking = threading.Thread(target=self.tcp_networker, args=(apsend_q, aprecv_q))
        self.networking.start()

        self.audio_processor_out = threading.Thread(target=self.audio_processor_worker_in, args=(aprecv_q, spkr_q) )
        self.audio_processor_out.start()
        self.audio_processor_in = threading.Thread(target=self.audio_processor_worker_out, args=(mic_q, apsend_q) )
        self.audio_processor_in.start()

        self.qs = {
                "mic": mic_q,
                "spkr": spkr_q,
                "send": apsend_q,
                "recv": aprecv_q
                }


    def stop_audio():
        self.soundcard.stop()

    def start_audio():
        self.soundcard.start()

    def setup_audio( self, mic_q, spkr_q, conrate ):

        pa_rate = 8000
        sampwidth = 2
        pa_channels = 1

        def callback(in_data, out_data, time_info, status):
            if self.loopback_test == 1:
                out_data[:] = in_data
                return pysoundcard.continue_flag
            mic_q.put(in_data)
            # print(len(in_data), conrate)
            assert len(in_data) == conrate
            if spkr_q.empty():
                out_data[:] = numpy.zeros( (conrate,1) )
            else:
                out_data[:] = spkr_q.get_nowait().reshape( (conrate,1) )
            return pysoundcard.continue_flag

        s = pysoundcard.Stream(channels=1, dtype=numpy.int16, samplerate=pa_rate, blocksize=conrate, callback=callback)
        self.soundcard = s
    
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


    def setup_audio_processor(self, mode):
        c2 = pycodec2.Codec2( mode )
        conrate = c2.samples_per_frame()
        bitframe = c2.bits_per_frame()
        self.c2 = c2
        return [conrate, bitframe]

    def udp_networker(self, apsend_q, aprecv_q):
        """send only for now"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", self.server[1]))
        sock.setblocking(False)
        self.sock = sock

        print("networker sendto", self.server)
        you = Address(callsign="SP5WWP")
        me = Address(callsign="W2FBI")
        print(you)
        print(me)
        framer = M17_IPFramer(
                dst=you,
                src=me,
                ftype=5, nonce=b"\xbe\xef"*8 )

        now = time.time()
        last = now
        accumulated_delay = 0
        deadline = .02
        while 1:
            now = time.time()
            if self.loopback_test == 2:
                aprecv_q.put( apsend_q.get() )
                continue

            d = apsend_q.get() + apsend_q.get() #need 16 bytes for M17 payload, each element on q should be 8 bytes
            #TODO generalize to support other Codec2 sizes, and grab data until enough is here to send
            #TODO payload_stream needs to return packets and any unused data from the buffer to support that functionality
            pkts = framer.payload_stream(d)
            # fd = open("out.m17","ab")
            for pkt in pkts:
                d = bytes(pkt)
                # print(_x(d))
                # fd.write(d)
                sock.sendto( d, self.server )
            # fd.close()
            try:
                while 1:
                    #catch up if we get a burst
                    x, conn = sock.recvfrom( encoded_buf_size ) 
                    # print(conn)
                    # print("Got: ",_x(x))
                    f = ipFrame.from_bytes(x)
                    aprecv_q.put(f.payload)
            except BlockingIOError as e:
                #nothing to read
                # print(e)
                pass
            except Exception as e:
                raise(e)
                print(e)
            loop_dur = now - last 
            accumulated_delay += loop_dur-deadline
            print("%.4f"%(accumulated_delay))
            last = now

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
