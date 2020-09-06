#!/usr/bin/env python
import sys
import time
import queue
import numpy
import socket
import binascii
import pycodec2
import threading
import multiprocessing
import scipy 
import scipy.signal

from .const import default_port
from .address import Address
from .frames import ipFrame
from .framer import M17_IPFramer
from .const import *
from .misc import example_bytes,_x,chunk




def null(config, inq, outq):
    while 1:
        x = inq.get()

def tee(header):
    def fn(config, inq, outq):
        while 1:
            x = inq.get()
            if type(x) == type(b""):
                print(header, _x(x))
            else:
                print(header, x)
            outq.put(x)
    return fn

def teefile(filename):
    def fn(config, inq, outq):
        with open(filename,"wb") as fd:
            try:
                while 1:
                    x = inq.get()
                    fd.write(x)
                    fd.flush()
                    outq.put(x)
            except:
                fd.close()
    return fn

def delay(size):
    def fn(config, inq, outq):
        fifo = []
        while 1:
            x = inq.get()
            fifo.insert(0,x)
            if len(fifo) > size:
                outq.put(fifo.pop())
    return fn

def ptt(config, inq, outq):
    """
    """
    while 1:
        x = inq.get()
        if config.ptt.poll(): #this will check for every single packet 
            outq.put(x)

def vox(config,inq,outq):
    last = None
    repeat_count = 0
    while 1:
        x = inq.get()
        if x == last:
            repeat_count += 1
        else:
            repeat_count = 0
        last = x
        if repeat_count > config.vox.silence_threshold:
            continue
        outq.put(x)


def mic_audio(config,inq,outq):
    import soundcard as sc
    default_mic = sc.default_microphone()
    # print(default_mic)
    conrate = config.codec2.conrate
    with default_mic.recorder(samplerate=8000, channels=1, blocksize=conrate) as mic:
        while 1:
            audio = mic.record(numframes=conrate)
            #we get "interleaved" floats out of here, in a numpy column ([[][][]])(hence the flatten even though it's a single audio channel)
            audio = audio.flatten() * 32767 #scales from -1,1 to signed 16bit int values
            #rest of the system works in little endian shorts, so we scale it up and convert the type
            audio = audio.astype("<h") 
            outq.put(audio)

def spkr_audio(config,inq,outq):
    import soundcard as sc
    default_speaker = sc.default_speaker()
    # print(default_speaker)
    def silence():
        sp.play(numpy.zeros(config.codec2.conrate))

    with default_speaker.player(samplerate=8000, channels=1) as sp:
        buf = [] #allow for playing chunks of audio even when computer is slow
        buflen = 0 #0 is dont use
        while 1:
            #if we stop receiving audio because someone stops transmitting, 
            #we wont get anything off the queue, so we can't block (hence nowait)
            try: 
                audio = inq.get_nowait()
                #rest of system works in LE signed shorts but soundcard expects floats in and out
                #so convert it back to a float, and scale it back down to an appropriate range (-1,1)
                audio = audio.astype("float")
                audio = audio / 32767
                if buflen:
                    if len(buf) < buflen:
                        buf.append(audio)
                        silence()
                    else:
                        for b in buf:
                            sp.play(b)
                        buf = []
                sp.play(audio)
            except queue.Empty as e:
                #and if we have no data, just play zeros
                silence()


def tobytes(config,inq,outq):
    while 1:
        outq.put(bytes(inq.get()))


def m17frame(config,inq,outq):
    dst = Address(callsign=config.m17.dst)
    src = Address(callsign=config.m17.src)
    print(dst)
    print(src)
    framer = M17_IPFramer(
            dst=dst,
            src=src,
            streamtype=5, #TODO need to set this based on codec2 settings too to support c2.1600
            nonce=b"\xbe\xef\xf0\x0d" + b"a"*10 ) 
    while 1:
        plen = 16 #TODO grab from the framer itself
        #need 16 bytes for M17 payload, each element on q should be 8 bytes if c2.3200
        #this will fail in funny ways if our c2 payloads dont fit exactly on byte boundaries
        d = inq.get()
        while len(d) < plen:
            d += inq.get()
        #TODO generalize to support other Codec2 sizes, and grab data until enough is here to send
        #TODO payload_stream needs to return packets and any unused data from the buffer to support that functionality
        pkts = framer.payload_stream(d)
        for pkt in pkts:
            outq.put(pkt)

def m17parse(config,inq,outq):
    while 1:
        f = ipFrame.from_bytes(inq.get())
        print(f)
        outq.put(f)


def payload2codec2(config,inq,outq):
    byteframe = int(config.codec2.bitframe/8) #TODO another place where we assume codec2 frames are byte-sized
    while 1:
        x = inq.get()
        for x in chunk(x.payload, byteframe):
            assert len(x) == byteframe
            outq.put(x) 

def codec2setup(mode):
    c2 = pycodec2.Codec2( mode )
    conrate = c2.samples_per_frame()
    bitframe = c2.bits_per_frame()
    return [c2,conrate,bitframe]

def codec2enc(config,inq,outq):
    while 1:
        audio = inq.get()
        c2bits = config.codec2.c2.encode(audio)
        assert len(c2bits) == config.codec2.bitframe/8
        outq.put(c2bits)

def codec2dec(config,inq,outq):
    while 1:
        c2bits = inq.get()
        audio = config.codec2.c2.decode(c2bits)
        outq.put(audio)

def udp_send(sendto):
    """
    sendto is the standard host,port) tuple like ("localhost",17000)
    """
    def fn(config,inq,outq):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        while 1:
            bs = inq.get()
            sock.sendto( bs, sendto )
    return fn

def udp_recv(port):
    def fn(config,inq,outq):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", port))
        # sock.setblocking(False)
        while 1:
            x, conn = sock.recvfrom( encoded_buf_size ) 
            #but what do I do with conn data, anything?
            # print(_x(x))
            outq.put(x)
    return fn

def integer_decimate(i):
    """
    uh oh. I'm poorly reimplementing gnuradio blocks, thats a bad sign
    """
    def fn(config,inq,outq):
        while 1:
            x = inq.get()
            de = x[::i]
            outq.put( x[::i] )
    return fn

def integer_interpolate(i):
    """
    uh oh. I'm poorly reimplementing gnuradio blocks, thats a bad sign
    """
    def fn(config,inq,outq):
        import samplerate
        resampler = samplerate.Resampler('sinc_best', channels=1)
        while 1:
            x = inq.get()
            # print(type(x[0]), x[0],x[1])
            y = resampler.process(x, i )
            # print(type(y[0]), y[0],y[1])
            z = numpy.array(y, dtype="<h")
            # print(type(z[0]), z[0],z[1])
            # print(y[0],y[1],y[2])
            # print( len(y),len(x)*i)
            # assert len(y) == len(x)*i
            outq.put( z )
    return fn

def chunker_b(size):
    def fn(config,inq,outq):
        buf = b""
        while 1:
            x = inq.get()
            buf += x
            while len(buf) > size:
                outq.put(buf[:size])
                buf = buf[size:]
    return fn

def convert(outtype):
    def fn(config,inq,outq):
        while 1:
            x = inq.get()
            y = numpy.frombuffer(x, outtype)
            outq.put(y)
    return fn

class dattr(dict):
    """
    "dict-attr", used for when you don't want to type [""] all the time
    (and i think it looks nicer for things like config settings)
    """
    def __getattr__(self,name):
        if type(self[name]) == type({}): 
            #make sure we wrap any nested dicts when we return them
            return dattr(self[name])
        else:
            #otherwise just make our key,value pairs accessible through . (e.g. x.name)
            return self[name]

def check_ptt():
    if int(time.time()/2) % 2 == 0:
        return True
    else:
        return False

def modular_client(host="localhost",src="W2FBI",dst="SP5WWP",mode=3200,port=default_port):
    mode=int(mode)
    port=int(default_port)
    #about time to make this cleaner, eh? but what parts do i like and dislike about this?
    #if i get too carried away, i'll end up reimplementing something gnuradio, poorly
    #

    #a chain is a series of small functions that share a queue between each pair
    #each small function is its own process - which is absurd, except this
    #is a testing and development environment, so ease of implementation/modification
    #and modularity is the goal
    #this also means we can meet our latency constraint for writing out
    #to the speakers without any effort, even though our total latency
    #from mic->udp is greater than our deadline. 
    #As long as each function stays under the deadline individually, all we do is add latency from sampled->delivered
    #   (well, as long as we have enough processor cores, but it's current_year, these functions still arent that heavy, and its working excellently given what I needed it to do
    #if a function does get slower than realtime, can I make two in its place writing to the same queues?
    #   as long as i have enough cores still, that seems reasonable - but I'll have to think about it

    tx_chain = [mic_audio, codec2enc, vox, m17frame, tobytes, udp_send((host,port))]
    rx_chain = [udp_recv(17000), tee("rx"), m17parse, payload2codec2, codec2dec, teefile("m17.raw"), spkr_audio]

    echolink_bridge_in = [udp_recv(55501), chunker_b(640), convert("<h"), integer_decimate(2), codec2enc, m17frame, tobytes, udp_send((host,port)) ]
    echolink_bridge_monitor = [
                udp_recv(55501), 
                chunker_b(640), 
                convert("<h"), 
                integer_decimate(2), 
                codec2enc, 
                tee("RX"),
                m17frame, tobytes,
                m17parse,payload2codec2, 
                tee("RX"),
                codec2dec, 
                spkr_audio
                ]
    echolink_bridge_out = [
            mic_audio, codec2enc, vox, m17frame, tobytes, 
            m17parse, payload2codec2, codec2dec, 
            integer_interpolate(2),
            udp_send(("pidp8i",55500)) 
            ]
    m17_to_echolink = [
            udp_recv(17000), tee("rx"), 
            m17parse, payload2codec2, codec2dec, 
            integer_interpolate(2),
            udp_send(("pidp8i",55500)) 
            ]

    test_chain = [
            mic_audio, 
            codec2enc, #.02ms of audio per q element at c2.3200 in this part of chain
            # delay(5/.02), #to delay for 5s, divide 5s by the time-length of a q element in this part of chain (which does change)
            # tee("delayed c2bytes: "),
            # teefile("out.m17"),
            # vox, 
            # ptt,
            # m17frame, #.04ms of audio per q element at c2.3200
            # tobytes, 
            # udp_send, 
            # udp_recv, 
            # m17parse, 
            # payload2codec2, #back to .02ms per q el
            codec2dec, 
            # null,
            spkr_audio
            ]
    modules = {
            "chains":[
                # tx_chain, 
                rx_chain, 
                # test_chain, 
                # echolink_bridge_monitor, 
                # echolink_bridge_in, 
                # echolink_bridge_out
                # m17_to_echolink
                ],
            "queues":[],
            "processes":[],
            }
    c2,conrate,bitframe = codec2setup(mode)
    print("conrate, bitframe = [%d,%d]"%(conrate,bitframe) )
    config = dattr({
        "m17":{
            "dst":dst,
            "src":src,
            },
        "ptt":{
            "poll":check_ptt,
            },
        "vox":{
            "silence_threshold":10, #that's measured in queue packets
            },
        "codec2":{
            "c2":c2,
            "conrate":conrate,
            "bitframe":bitframe,
            },
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
    for chainidx,chain in enumerate(modules["chains"]):
        inq = None
        for fnidx,fn in enumerate(chain):
            name = fn.__name__
            if fnidx != len(chain):
                outq = multiprocessing.Queue()
                modules["queues"].append(outq)
            else:
                outq = None
            process = multiprocessing.Process(name="chain_%d/fn_%d/%s"%(chainidx,fnidx,name), target=fn, args=(config, inq, outq))
            modules["processes"].append({
                    "name":name,
                    "inq":inq,
                    "outq":outq,
                    "process":process
                    })
            process.start()
            inq = outq
    try:
        procs = modules['processes']
        while 1:
            if any(not p['process'].is_alive() for p in procs):
                print("lost a client process")
                break
            time.sleep(.05)
    except KeyboardInterrupt as e:
        print("Got ^C, ")
    finally:
        print("closing down")
        for proc in procs:
            #messy
            #TODO make a rwlock for indicating shutdown
            proc["process"].terminate()


if __name__ == "__main__":
    modular_client(*sys.argv[1:])

"""
https://www.cloudcity.io/blog/2019/02/27/things-i-wish-they-told-me-about-multiprocessing-in-python/

"""
