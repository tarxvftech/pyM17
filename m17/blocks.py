
import sys
import time
import queue
import socket

from .address import Address
from .frames import ipFrame
from .framer import M17_IPFramer
from .const import *
from .misc import example_bytes,_x,chunk,dattr
from .blocks import *

import numpy


def zeros(size, dtype, rate):
    def fn(config, inq, outq):
        while 1:
            outq.put(numpy.zeros(size, dtype))
            time.sleep(1/rate)
    return fn

def null(config, inq, outq):
    """
    Don't do nuffin.

    (Useful for stopping a q from filling up and preventing further processing)

    (Probably used after tee() or teefile() if you just want to collect
    data with those and not do further processing on the data stream)
    """
    while 1:
        x = inq.get()

def tee(header):
    """
    Print incoming items to screen before putting them on the next q
    bytes get printed as hex strings
    "header" parameter gets printed with each queue element to differentiate multiple tee()s
    named like standard UNIX tee(1)
    """
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
    """
    Same as tee, except assumes elements coming in are bytes, and writes
    them to a provided filename
    """
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

def throttle(n_per_second):
    """
    Read from the inq and only put elements on the outq at (no more than)
    a specified rate in q elements per second. As "no more than" might
    suggest, this is setting a maximum, not a minimum. Minimum is based
    on your hardware and a number of other factors.
    """
    raise(NotImplementedError) #TODO

def delay(size):
    """
    keep a rolling fifo of size "size", creating a predictable delay 
    (assuming they are coming in at a limited rate)

    See "throttle()" for enforcing a rate limit of elements per unit time.
    """
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
    take elements off the inq (like audio frames) and only put them on the outq
    if the "push to talk" evaluates truthy.

    Redo this to take a check function as a parameter and close around
    that instead of using config
    """
    while 1:
        x = inq.get()
        if config.ptt.poll(): #this will check for every single packet 
            outq.put(x)

def vox(config,inq,outq):
    """
    Watch for duplicate incoming q elements, and if there's more than
    a configurable threshold in a row, don't copy further duplicates

    This lets you use a microphone mute as a reverse PTT, among other things
    """
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
    """
    Pull audio off the default microphone in 8k, 1 channel, scale it
    into 16bit shorts since soundcard uses floats, and put them in the outq.

    inq is unconnected here.
    """
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
    """
    play mono (c=1) 8k audio into the speaker
    Accepts 16bit shorts, converts to soundcard expected format

    outq is unconnected here.

    buflen allows for slow computers that cant keep the buffers filled
    within the realtime constraints to still play smooth audio - just
    in stutters of specified length in frames
    """
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
    """
    convert everything passing through to bytes, just what it says on the tin
    """
    while 1:
        outq.put(bytes(inq.get()))


def m17frame(config,inq,outq):
    """
    frame incoming codec2 compressed audio frames into M17 packets
    """
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
    """
    Parse incoming bytes into M17 ipFrames
    """
    while 1:
        f = ipFrame.from_bytes(inq.get())
        if "verbose" in config and config.verbose:
            print(f)
        outq.put(f)


def payload2codec2(config,inq,outq):
    """
    Pull out an M17 payload and return just the raw Codec2 bytes
    """
    byteframe = int(config.codec2.bitframe/8) #TODO another place where we assume codec2 frames are byte-sized
    while 1:
        x = inq.get()
        for x in chunk(x.payload, byteframe):
            assert len(x) == byteframe
            outq.put(x) 

def codec2setup(mode):
    import pycodec2
    c2 = pycodec2.Codec2( mode )
    conrate = c2.samples_per_frame()
    bitframe = c2.bits_per_frame()
    return [c2,conrate,bitframe]

def codec2enc(config,inq,outq):
    """
    exact opposite of codec2dec

    8khz sample rate, 1 channel (mono audio)
    In: 16bit signed shorts, size varies but expects 160 samples for Codec2 3200
    Out: depends on Codec2 mode, but 3200 bps gives 8 bytes per 160 sample raw frame.
    """
    while 1:
        audio = inq.get()
        c2bits = config.codec2.c2.encode(audio)
        assert len(c2bits) == config.codec2.bitframe/8
        outq.put(c2bits)

def codec2dec(config,inq,outq):
    """
    exact opposite of codec2enc
    In: Depends on Codec2 mode, but expects 8 bytes for Codec2 mode 3200
    Out: 16 bit signed shorts, size varies but 160 samples for Codec2 mode 3200
    8khz sample rate, 1 channel (mono audio)
    """
    while 1:
        c2bits = inq.get()
        audio = config.codec2.c2.decode(c2bits)
        outq.put(audio)

def udp_send(sendto):
    """
    Send incoming bytes to udp (host,port)

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
    """
    Receive UDP datagram payloads as bytes and output them to outq
    Maintains UDP datagram separation on the q
    """
    def fn(config,inq,outq):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", port))
        # sock.setblocking(False)
        while 1:
            x, conn = sock.recvfrom( 1500 )
            #1500 is the maximum packet payload size

            #but what do I do with conn data, anything?
            # print(_x(x))
            outq.put(x)
    return fn

def integer_decimate(i):
    """
    For each incoming list of things, skip some of them, decimating the incoming signal
    e.g. integer_decimate(2) will cut a 16khz sampled audio signal to 8khz
    see integer_interpolate for the reverse
    """
    def fn(config,inq,outq):
        while 1:
            x = inq.get()
            de = x[::i]
            outq.put( x[::i] )
    return fn

def integer_interpolate(i):
    """
    for each incoming list of things, interpolate
    useful for going from 8khz audio to 16khz audio to match expected formats

    starting to look uncomfortably like gnuradio, innit?
    """
    def fn(config,inq,outq):
        import samplerate
        resampler = samplerate.Resampler('sinc_best', channels=1)
        while 1:
            x = inq.get()
            y = resampler.process(x, i )
            z = numpy.array(y, dtype="<h")
            outq.put( z )
    return fn

def chunker_b(size):
    """
    Incoming bytes will get chunked into a particular size for downstream
    nodes that don't do their own buffering
    """
    def fn(config,inq,outq):
        buf = b""
        while 1:
            x = inq.get()
            buf += x
            while len(buf) > size:
                outq.put(buf[:size])
                buf = buf[size:]
    return fn

def np_convert(outtype):
    """
    Use numpy to convert incoming elements to a numpy type
    """
    def fn(config,inq,outq):
        while 1:
            x = inq.get()
            y = numpy.frombuffer(x, outtype)
            outq.put(y)
    return fn

def check_ptt():
    """
    is there a good way to do cross platform ptt, or 
    should i abandon that idea and try to improve vox, or 
    just assume linux?
    """
    if int(time.time()/2) % 2 == 0:
        return True
    else:
        return False