import os
import sys
import cmd
import time
import wave
import queue
import socket
import random
import logging
import readline
import threading
import multiprocessing

#TODO: move all imports into respective blocks as needed

from .address import Address
from .frames import initialLICH, ipFrame, standard_data_packet
from .framer import M17_IPFramer
from .streams import M17_IPStream
from .const import *
from .misc import example_bytes,_x,chunk,dattr,encode_utf_style_int,parse_utf_style_int
from .blocks import *
import m17.network as network

import numpy

def default_config(c2_mode):
    c2,conrate,bitframe = codec2setup(c2_mode)
    print("conrate, bitframe = [%d,%d]"%(conrate,bitframe) )

    config = dattr({
        "m17":{
            "dst":"",
            "src":"",
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
    return config

def codeblock(callback):
    def fn(config, inq, outq):
        while 1:
            x = inq.get()
            y = callback(x)
            outq.put(y)
    return fn

def stream_reader(filename):
    def fn(config, inq, outq):
        with open(filename, "rb") as fd:
            data = fd.read()
            m17s = M17_IPStream.from_bytes(data)
            outq.put(m17s)
        while 1: #infinite loop so we don't kill the rest of the chain?
            #which means we'll hang forever...
            #fine for now.
            #obviously not fine for later
            time.sleep(1)
    return fn

def m17rewriter(*args,**kwargs):
    def m17rewriter_fn(config,inq,outq,testmode=False):
        while 1:
            if inq.empty() and testmode:
                return
            frame = inq.get()
            dst = kwargs.get('dst')
            src = kwargs.get('src')
            sid = kwargs.get('streamid')
            if sid:
                frame.streamid = sid
            if dst:
                if not isinstance(dst,Address):
                    dst = Address(callsign=dst)
                frame.LICH.dst = dst
            if src:
                if not isinstance(src,Address):
                    src = Address(callsign=src)
                frame.LICH.src = src
            outq.put(frame)
    return m17rewriter_fn

def udp_server( port, packet_handler, occasional=None ):
    """
    not meant to be used in a chain
    """
    def udp_server_fn():  #but still has a closure to allow running it as a process
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", port))
        sock.setblocking(False)
        active_connections = {}
        timeout = 30
        while 1:
            active_connections = {k:v for k,v in active_connections.items() if v + timeout < time.time()}
            try:
                bs, conn = sock.recvfrom( 1500 ) 
                active_connections[ conn ] = time.time() 
                packet_handler(sock, active_connections, bs, conn)
            except BlockingIOError as e:
                pass
            occasional(sock)
            time.sleep(.001)
    return udp_server_fn

def zeros(size, dtype, rate):
    def zeros_fn(config, inq, outq):
        while 1:
            outq.put(numpy.zeros(size, dtype))
            time.sleep(1/rate)
    return zeros_fn

class TwoWayBlock:
    def __init__(self):
        self.qs = {}
        raise(NotImplementedError)

    def probe(self, name, direction):
        """
        processes that can sample inputs and outputs
        direction describes the path of elements from fn - 
        e.g. if it's being used only to generate packets, the direction is "out"
        if it's being used to terminate a processing stream, the direction is "in"
        """
        if name not in self.qs:
            self.qs[name] = multiprocessing.Queue()
        def probe_fn(config,inq,outq):
            while 1:
                if direction == "in":
                    self.qs[name].put(inq.get())
                elif direction == "out":
                    outq.put(self.qs[name].get())
                time.sleep(.000001)
        return probe_fn
    def receiver(self):
        return self.probe("recv", "out")
    def sender(self):
        return self.probe("send", "in")

def reflector(mycall, *args, **kwargs):
    bind=("",17000)
    import sentry_sdk
    sentry_sdk.init(
        "https://241f77e18c5c44dd8c245c3c26588c03@o474357.ingest.sentry.io/6123140",
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        # We recommend adjusting this value in production.
        traces_sample_rate=1.0
        )
    #using the reflector like so:
    # network.simple_n7tae_reflector(mycall, bind=bind) 
    #exits immediately, so make sure to tell it to not daemonize the thread so it stays running:
    network.simple_n7tae_reflector(mycall, bind=bind, nodaemon=True)
    #if we exit, depend on systemd to bring us back up and hope sentry logs the error

def tee_s3uploader(bucket,filebasename):
    import boto3
    logging.getLogger('boto3').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('s3transfer').setLevel(logging.WARNING)
    log = logging.getLogger("tee_s3uploader")
    s3 = boto3.resource('s3')
    def s3uploader_fn(config,inq,outq):
        buk = s3.Bucket('%s'%(bucket))
        while 1:
            x = inq.get()
            buk.put_object(Key=filename,Body=x)
            # filename = "%s_%04x_%f.m17s"%(filenamebase, stream1.streamid, time.time())
            log.debug("uploaded to %s"%(filename))
            outq.put(x)
    return s3uploader_fn

def tee_s3uploader_m17streams(bucket,filenamebase):
    import boto3
    logging.getLogger('boto3').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('s3transfer').setLevel(logging.WARNING)
    log = logging.getLogger("tee_s3uploader_m17streams")
    s3 = boto3.resource('s3')
    def s3uploader_fn(config,inq,outq):
        buk = s3.Bucket('%s'%(bucket))
        while 1:
            stream1 = inq.get()
            filename = "%d_%04x_%s.m17s"%(time.time(), stream1.streamid, filenamebase)
            buk.put_object(Key=filename,Body=bytes(stream1))
            log.debug("uploaded to %s"%(filename))
            outq.put(stream1)
    return s3uploader_fn

class bot(TwoWayBlock):
    def __init__(self):
        self.qs = {
                #modular() sender() gets send_in, so we take input from send_out
                "send":multiprocessing.Queue(),
                #modular() receiver() reads from recv_out, so we put our own input into recv_in
                "recv":multiprocessing.Queue(),
                }
        self.msgin = self.qs['send']
        self.msgout = self.qs['recv']
        self.log = logging.getLogger('bot')
        self.proc = threading.Thread(name="bot", 
                target=self.mailman, 
                args=( 
                    self.qs,
                    ))
        self.proc.daemon = True
        self.proc.start()

    def mailman(self, qs):
        #only needed to translate an item on the queue into a method call
        msgin = qs['send']
        while 1:
            msg = msgin.get()
            self.handleIncoming(None, msg)

    def handleIncoming(self, metadata, msg):
        self.log.debug("(Unimplemented bot.handleIncoming()): Incoming: %s, %s", metadata, msg)
        pass
    def queueOutgoing(self, metadata, msg):
        # self.log.debug("Outgoing: %s, %s", metadata, msg)
        self.msgout.put(msg)
        pass

class textshell(cmd.Cmd,bot):
    #https://github.com/python/cpython/blob/3.10/Lib/cmd.py
    #needs a way to print incoming messages in realtime
    #so probably needs some threading
    #hey, want to have IRC over M17? 
    #(And Discord and Matrix?)
    #https://github.com/jesopo/ircrobots/
    #https://pypi.org/project/pydle/
    #https://github.com/itslukej/zirc
    def __init__(self, mycallsign):
        #i explicity want the inits of both bot and cmd.Cmd
        #so no super() here. giving this a shot because bot is so simple.
        cmd.Cmd.__init__(self)
        bot.__init__(self)
        self.callsign = mycallsign
        self.prompt = ""
        print("Ready")

    def do_dictate(self, line):
        print("speak. be heard.")
        print("Now recording, press enter to transcribe")
        input("(enter to stop)")

    def do_voice(self, line):
        parts = line.split()
        if len(parts):
            voice = parts[0]
        else:
            voice = "Matthew"
        print(f"now using M17 text and M17 voice {voice} ")

    def do_lang(self, line):
        default_lang = "en-US"
        print(f"lang {line} set")

    def do_text(self,line):
        print(f"now sending only M17 text")

    def do_disconnect(self, line):
        # print(f"disconnected from {reflectorname} module {module}")
        print(f"disconnected ")

    def do_connect(self, line):
        parts = line.split()
        if len(parts) < 2:
            print("?")
            return
        reflectorname,module = parts[0],parts[1]
        print(f"connecting to {reflectorname} module {module}")

    def do_EOF(self,line):
        return True
    def do_exit(self,line):
        return True
    def do_quit(self,line):
        return True
    def parseline(self, line):
        """Parse the line into a command name and a string containing
        the arguments.  Returns a tuple containing (command, args, line).
        'command' and 'args' may be None if the line couldn't be parsed.

        modified from stock: only recognizes commands prefixed with '/'
        this is so default() can be used to send messages.
        This allows for a prompt a little like irc
        """
        line = line.strip()
        if not line:
            return None, None, line
        elif line[0] == '?':
            line = 'help ' + line[1:]
        elif line[0] == '!':
            if hasattr(self, 'do_shell'):
                line = 'shell ' + line[1:]
            else:
                return None, None, line
        i, n = 0, len(line)
        #modified only here and below to add the '/' support
        while i < n and line[i] in self.identchars+'/':  #have to tell cmd.Cmd that '/' is an acceptable character for being part of a command name
            i=i+1
        cmd, arg = line[:i], line[i:].strip()

        if cmd and cmd[0] == '/':
            #strip the slash for command processing
            return cmd[1:], arg, line
        elif cmd in ['EOF']: #gah, special case because "EOF"'s a special string from cmd.Cmd
            return cmd, arg, line
        else:
            #if no slash, it's not a command, so onecmd() falls through to default() in cmd.Cmd().onecmd()
            return None, None, line

    def default(self, line):
        """Called on an input line when the command prefix is not recognized.
        Now sends messages to the connected channel
        """
        if line[0] == "/":
            print("unhandled command")
            return
        self.queueOutgoing(None, line)

    def handleIncoming(self, metadata, msg):
        #super().handleIncoming(metadata,msg)
        print("> ",msg)
    def emptyline(self,line=None):
        pass


class client_blocks(TwoWayBlock):
    #TODO simplify
    """
    You can't simply use the network client's own queues, because this is an adapter to the modular() queueing system.
    (Though there's an opportunity here for making the network client multiprocessing capable, instead of threaded eh?)
    (there're too many layers, and i can definitely make this simpler while retaining the modularity)
    """
    def __init__(self, mycall, bind=None):
        self.mycall = mycall
        self.qs = {
                "send":multiprocessing.Queue(),
                "recv":multiprocessing.Queue(),
                "cmds":multiprocessing.Queue(),
                }
        self.process = multiprocessing.Process(name="m17ref_client_blocks", 
                target=self.proc, 
                args=(
                    self.qs,
                    mycall,
                    bind
                    )
                )

    def start(self,daemon=True):
        self.process.daemon = daemon
        self.process.start()

    def connect(self, call=None, module="A", peer=None):
        self.qs["cmds"].put( ("connect", call, module, peer ) )

    def proc(self, qs, mycall,bind):
        """
        """
        cli = network.simple_n7tae_client(mycall, bind)
        #cli.sendq #(packets to send out)
        #cli.recvq #(packets we've just received)
        cmdq = qs["cmds"]
        sendq = qs["send"]
        recvq = qs["recv"]
        while 1:
            if not cmdq.empty():
                args = cmdq.get()
                print("client_blocks:",args)
                cmd, args = args[0], args[1:]
                if cmd == "connect":
                    cli.connect(*args)
            x = cli.recv()
            if x:
                recvq.put(x)
            if not sendq.empty():
                data= sendq.get_nowait()
                cli.sendq.put(data)
            time.sleep(.00005)


def null(config, inq, outq):
    """
    Don't do nuffin.

    (Useful for stopping a q from filling up and preventing further processing)

    (Probably used after tee() or teefile() if you just want to collect
    data with those and not do further processing on the data stream)
    """
    while 1:
        x = inq.get()


def m17frame_extractpayload(config, inq, outq):
    while 1:
        x = inq.get()
        outq.put( x.payload )

def m17packet_payload2body(config, inq, outq):
    """
    """
    while 1:
        x = inq.get()
        sz,val = parse_utf_style_int(x)
        #sz is how many bytes the utf-style-int takes up
        #val is the actual value of that int
        #in this case, it represents the Packet sub-format (raw, APRS, M17SMS, etc)
        outq.put( x[sz:] )


def tee(header):
    """
    Print incoming items to screen before putting them on the next q
    bytes get printed as hex strings
    "header" parameter gets printed with each queue element to differentiate multiple tee()s
    named like standard UNIX tee(1)
    """
    def tee_fn(config, inq, outq):
        while 1:
            x = inq.get()
            if type(x) == type(b""):
                print(header, _x(x))
            else:
                print(header, x)
            outq.put(x)
    return tee_fn

def ffmpeg(ffmpeg_url):
    ffmpeg_url_example="icecast://source:m17@m17tester.tarxvf.tech:876/live.ogg"
    def ffmpeg_fn(config, inq, outq):
        from subprocess import Popen, PIPE, STDOUT
        p = Popen(
                ["ffmpeg","-re", #ffmpeg, and limit reading rate to native speed so we don't spin a whole core with writing zeros to icecast
                    "-f","s16le","-ar", "8000", "-ac", "1", "-i", "/dev/stdin", #the input options
                    "-ar", "48000", "-ac", "2",
                    "-content_type", "'application/mpeg'",  #only support ogg for now
                    ffmpeg_url]
                , stdout=PIPE, stdin=PIPE, stderr=PIPE)
        while 1:
            try: 
                # audio = inq.get_nowait()
                audio = inq.get()
                p.stdin.write( audio.tobytes() )
            except queue.Empty as e:
                sys.stdout.write('aU')
                audio = numpy.zeros(config.codec2.conrate,dtype="<h")
            sys.stdout.flush()
            # time.sleep(1/50)
    return ffmpeg_fn

def teefile(filename):
    """
    Same as tee, except assumes elements coming in are bytes, and writes
    them to a provided filename
    """
    print("TEEFILE",filename)
    def teefile_fn(config, inq, outq):
        with open(filename,"wb") as fd:
            try:
                while 1:
                    x = inq.get()
                    fd.write(x)
                    fd.flush()
                    outq.put(x)
            except:
                print("Closing")
                fd.close()
    return teefile_fn

def throttle(n_per_second):
    """
    Read from the inq and only put elements on the outq at (no more than)
    a specified rate in q elements per second. As "no more than" might
    suggest, this is setting a maximum, not a minimum. Minimum is based
    on your hardware and a number of other factors.

    TODO implementation problem - stutters on long transmissions.
    Any delay at all in upstream leads to stuttering due to implementation here.
    """
    def throttle_fn(config,inq,outq):
        lastsent = 0
        time_s_between = 1/n_per_second
        while 1:
            x = inq.get()
            while lastsent + time_s_between >= time.time():
                time.sleep(.0002)
            outq.put(x)
            lastsent = time.time()
    return throttle_fn

def tee2wav(filename, samplerate, bytespersample, channels):
    wavfilename = "%s.wav"%(filename)
    def tee2wav_fn(config,inq,outq,testmode=False):
        with wave.open(wavfilename,"wb") as fd:
            fd.setnchannels(channels)
            fd.setsampwidth(bytespersample)
            fd.setframerate(samplerate) #codec2 output is 8khz s16le mono
            while 1:
                if inq.empty() and testmode:
                    return
                wavframe = inq.get()
                fd.writeframes(wavframe)
                outq.put(wavframe)
    return tee2wav_fn


def delay(size):
    """
    keep a rolling fifo of size "size", creating a predictable delay 
    (assuming they are coming in at a limited rate)

    See "throttle()" for enforcing a rate limit of elements per unit time.
    """
    def delay_fn(config, inq, outq):
        fifo = []
        while 1:
            x = inq.get()
            fifo.insert(0,x)
            if len(fifo) > size:
                outq.put(fifo.pop())
    return delay_fn

def ptt(config, inq, outq):
    """
    take elements off the inq (like audio frames) and only put them on the outq
    if the "push to talk" evaluates truthy.

    TODO: Redo this to take a check function as a parameter and close around
    that instead of using config

    TODO: This doesn't set or send EOT flags/frames.
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

    TODO: This doesn't set or send EOT flags/frames.
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

def toutf8(config,inq,outq):
    """
    convert bytes passing through to utf8 strings
    """
    while 1:
        outq.put(inq.get().decode('utf-8'))
def tossml(config,inq,outq):
    """
    convert text stream passing through to ssml stream
    (just adds tags for compatibility)
    """
    while 1:
        outq.put("<speak>" + inq.get() + "</speak>")


def m17packetframe(config,inq,outq,testmode=False):
    """
    frame outgoing payloads into packets
    TODO: lots of hardcoded values
    """
    if isinstance(config.m17.dst, Address):
        dst = config.m17.dst
    else:
        dst = Address(callsign=config.m17.dst)
    if isinstance(config.m17.src, Address):
        src = config.m17.src
    else:
        src = Address(callsign=config.m17.src)
    print(dst)
    print(src)
    fn = 0
    lich=initialLICH(
            dst=dst,
            src=src,
            streamtype=standard_data_packet,
            )
    while 1:
        if inq.empty() and testmode:
            return
        text = inq.get()
        body=text.encode("utf-8")
        payload = encode_utf_style_int(5) + body
        frame=ipFrame(
            streamid=random.randint(1,2**16-1),
            LICH=lich,
            frame_number=fn,
            payload=payload
            )
        fn += 1
        outq.put(frame)
        #TODO: assuming payloads are under max size for now

def m17voiceframe(config,inq,outq,testmode=False):
    """
    frame incoming codec2 compressed audio frames into M17 packets
    """
    dst = Address(callsign=config.m17.dst)
    src = Address(callsign=config.m17.src)
    print(dst)
    print(src)
    framer = M17_IPFramer(
            streamid=random.randint(1,2**16-1),
            dst=dst,
            src=src,
            streamtype=5, #TODO need to set this based on codec2 settings too to support c2.1600
            nonce=b"\xCC"*14
            )
    while 1:
        plen = 16 #TODO grab from the framer itself
        #need 16 bytes for M17 payload, each element on q should be 8 bytes if c2.3200
        #this will fail in funny ways if our c2 payloads dont fit exactly on byte boundaries
        if inq.empty() and testmode:
            return
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

def teestreamfile(filenamebase):
    """
    tee incoming streams to separate files named in a pattern.
    """
    def teestreamfile_fn(config,inq,outq,testmode=False):
        while 1:
            stream1 = inq.get()
            filename = "%s_%04x_%f.m17s"%(filenamebase, stream1.streamid, time.time())
            with open(filename, "wb") as fd:
                fd.write(bytes(stream1))
            outq.put(stream1)
    return teestreamfile_fn

def m17streams2frames(config,inq,outq,testmode=False):
    while 1:
        if inq.empty() and testmode:
            return
        stream = inq.get()
        for frame in stream:
            outq.put(frame)

def m17voiceframes2streams(config,inq,outq,testmode=False):
    """
    Batches up groups of parsed M17 frames (IP only for now) into streams.

    Uses a timeout and end of stream markers to know when to flush a
    stream to output.
    A stream is defined here as a single transmission, so all LSF frames
    should be the same and all frame counters should be monotonically
    increasing, ideally from zero.

    Alternatively you could rely on the SID (stream ID). which now that
    I've remembered exists I'm totally using.

    TODO: write tests to check
    * stream sid changes
    * last packet handling
    * first packet of a new stream doesn't get lost
    * timeouts 
    """
    framesthisstream = []
    lastsid = None
    lastframetime = None
    timeout = .5 #seconds


    # maxlength = 300 #seconds (300==5min)
    # maxpackets = maxlength / .04 #m17 frame is 40ms
    ##not implemented yet, not sure i want it

    log = logging.getLogger("m17frames2streams")
    def flush():
        nonlocal framesthisstream
        nonlocal log
        if len(framesthisstream):
            log.debug("flush stream!")
            s = M17_IPStream.from_frames( framesthisstream )
            outq.put(s)
            framesthisstream = []
    while 1:
        if not inq.empty():
            x = inq.get()
            if len(framesthisstream) and (x.isLastFrame()):
                log.debug("flush due to last frame")
                framesthisstream.append(x)
                flush()
                lastsid = None
                lastframetime = None
                #don't fall through, we already handled this frame
                continue
            elif len(framesthisstream) and (x.streamid != lastsid):
                log.debug("flush due to sid change")
                flush()
                #fall through so this frame of a new stream gets handled
            #default - handle frame as normal because it's not part of a new stream or the last packet of an old stream
            framesthisstream.append(x)
            lastsid = x.streamid
            lastframetime = time.time()
        else:
            #fallback - flush when there's been enough time
            #we only bother checking when the queue is empty because the queue will be empty a LOT
            #frames only likely to come in every multiple tens of milliseconds for a streaming service
            #and for replying recorded traffic, we can certainly keep up with a timeout, can't we?
            if lastframetime and lastframetime +timeout <= time.time():
                log.debug("flush due to timeout")
                flush()
                lastframetime = None
            time.sleep(.005) #streams don't mind being delayed much, since they get delivered all at once
        

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

def codec2enc(config,inq,outq,testmode=False):
    """
    exact opposite of codec2dec

    8khz sample rate, 1 channel (mono audio)
    In: 16bit signed shorts, size varies but expects 160 samples for Codec2 3200
    Out: depends on Codec2 mode, but 3200 bps gives 8 bytes per 160 sample raw frame.
    """
    while 1:
        if inq.empty() and testmode:
            return
        audio = inq.get()
        c2bits = config.codec2.c2.encode(audio)
        assert len(c2bits) == config.codec2.bitframe/8
        outq.put(c2bits)

def codec2dec(config,inq,outq,testmode=False):
    """
    exact opposite of codec2enc
    In: Depends on Codec2 mode, but expects 8 bytes for Codec2 mode 3200
    Out: 16 bit signed shorts, size varies but 160 samples for Codec2 mode 3200
    8khz sample rate, 1 channel (mono audio)
    """
    while 1:
        if inq.empty() and testmode:
            return
        c2bits = inq.get()
        audio = config.codec2.c2.decode(c2bits)
        outq.put(audio)

def udp_send(sendto):
    """
    Send incoming bytes to udp (host,port)

    sendto is the standard host,port) tuple like ("localhost",17000)
    """
    def udp_send_fn(config,inq,outq):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        while 1:
            bs = inq.get()
            sock.sendto( bs, sendto )
    return udp_send_fn

def udp_recv(port):
    """
    Receive UDP datagram payloads as bytes and output them to outq
    Maintains UDP datagram separation on the q
    Does not allow for responding to incoming packets. See udp_server for that.
    """
    def udp_recv_fn(config,inq,outq):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", port))
        # sock.setblocking(False)
        while 1:
            x, conn = sock.recvfrom( 1500 )
            #1500 is the maximum packet payload size

            #but what do I do with conn data, anything?
            # print(_x(x))
            outq.put(x)
    return udp_recv_fn

def integer_decimate(i):
    """
    For each incoming list of things, skip some of them, decimating the incoming signal
    e.g. integer_decimate(2) will cut a 16khz sampled audio signal to 8khz
    see integer_interpolate for the reverse
    """
    def int_decimate_fn(config,inq,outq):
        while 1:
            x = inq.get()
            de = x[::i]
            outq.put( x[::i] )
    return int_decimate_fn

def to_stereo(config, inq, outq):
    while 1:
        x = inq.get()
        z = numpy.repeat(x,2)
        outq.put( z )

def integer_interpolate(i):
    """
    for each incoming list of things, interpolate
    useful for going from 8khz audio to 16khz audio to match expected formats

    starting to look uncomfortably like gnuradio, innit?
    """
    def int_interp_fn(config,inq,outq):
        import samplerate
        resampler = samplerate.Resampler('sinc_best', channels=1)
        while 1:
            x = inq.get()
            y = resampler.process(x, i )
            z = numpy.array(y, dtype="<h")
            outq.put( z )
    return int_interp_fn

def chunk_and_pad_b(size):
    """
    Incoming bytes will get chunked into a particular size for downstream
    nodes that don't do their own buffering - and padded with zeros if necessary.
    """
    def chunker_fn(config,inq,outq,testmode=False):
        while 1:
            if inq.empty() and testmode:
                return
            buf = inq.get()
            while len(buf) > size:
                outq.put(buf[:size])
                buf = buf[size:]
            if len(buf) > 0:
                fill_needed = size - len(buf)
                buf += b"\x00"*fill_needed
                outq.put(buf)
    return chunker_fn

def chunker_b(size):
    """
    Incoming bytes will get chunked into a particular size for downstream
    nodes that don't do their own buffering
    """
    def chunker_fn(config,inq,outq,testmode=False):
        buf = b""
        while 1:
            if inq.empty() and testmode:
                return
            x = inq.get()
            buf += x
            while len(buf) > size:
                outq.put(buf[:size])
                buf = buf[size:]
    return chunker_fn

def np_convert(outtype):
    """
    Use numpy to convert incoming elements to a numpy type
    """
    def np_convert_fn(config,inq,outq,testmode=False):
        while 1:
            if inq.empty() and testmode:
                return
            x = inq.get()
            y = numpy.frombuffer(x, outtype)
            outq.put(y)
    return np_convert_fn

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


def modular(config, chains):
    """
    Take in a global configuration, and a list of lists of queue
    processing functions, and hook them up in a chain, each function in
    its own process
    Fantastic for designing, developing, and debugging new features.
    """
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
    modules = {
            "chains":chains,
            "queues":[],
            "processes":[],
            }

    for chainidx,chain in enumerate(modules["chains"]):
        inq = None
        manager = multiprocessing.Manager()
        for fnidx,fn in enumerate(chain):
            name = fn.__name__
            if fnidx != len(chain):
                outq = manager.Queue()
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

    def wait(modules):
        try:
            procs = modules['processes']
            while 1:
                if any(not p['process'].is_alive() for p in procs):
                    print("lost a client process ")
                    for p in procs:
                        print(p['name'], p['process'].name, p['process'].is_alive())
                    break
                time.sleep(.05)
            #I can see where this is going to need to change
            #it's fine for now, but a real server will need something different
        except KeyboardInterrupt as e:
            print("Got ^C, ")
        finally:
            print("closing down")
            for proc in procs:
                #messy
                #TODO make a rwlock for indicating shutdown
                proc["process"].terminate()
    return modules, wait
    """
    Good links I found:
    https://www.cloudcity.io/blog/2019/02/27/things-i-wish-they-told-me-about-multiprocessing-in-python/

    """
