#!/usr/bin/env python
import sys
import time
import queue
import socket
import unittest
import binascii
import multiprocessing

from .const import *
from .misc import example_bytes,_x,chunk,dattr
from .blocks import *
import m17.network as network
from m17.address import Address


#reflector app (mycall)

def refquery():
    x = network.simple_n7tae_client(mycall="U4TIME",bind=None)
    x.connect("M17-XVF","Z")
    import pdb; pdb.set_trace()
def refchk(*args):
    checker = network.reflector_checker(mycall="U4TIME",bind=None)
    for ref in args:
        checker.start_check(ref)
    time.sleep(3)
    print(checker.results())
    checker.close()


def M17SMS(mycall, refname, theirmodule):
    shell = textshell(mycall)
    config = default_config(3200)
    config.m17.dst = Address(callsign=refname)
    config.m17.dst.set_reflector_module(theirmodule)
    config.m17.src = Address(callsign=mycall)
    config.m17.src.set_reflector_module("S")

    n7tae = client_blocks(mycall)
    n7tae.start()
    #hmmm. client_blocks and the protocol class itself need a rewrite to handle this, eh?
    #TODO: for now, be careful that n7tae connect() only connects to dst set in config 
    #this is easy at this specific moment because textshell isn't hooked up to the protocol either lol

    n7tae.connect(refname,theirmodule)
    # rxchain = [ shell.receiver(), m17packetframe, tobytes, n7tae.sender() ]
    rxchain = [ shell.receiver(), m17packetframe, tobytes, n7tae.sender() ]
    txchain = [ n7tae.receiver(), 
            m17parse, m17frame_extractpayload, m17packet_payload2body, toutf8,
            shell.sender() ]
    modules, wait = modular(config, [rxchain,txchain])
    shell.cmdloop()
    for proc in modules['processes']:
        proc["process"].terminate()

def echoshell(callsign):
    shell = textshell(callsign)
    chain = [shell.receiver(), shell.sender() ]
    config = {}
    modules, wait = modular(config, [chain])
    shell.cmdloop()
    for proc in modules['processes']:
        proc["process"].terminate()
    # wait(modules)


def parrot(refname, theirmodule):
    #A parrot service for M17 - it's a full client that records and plays back after incoming stream is over PTT is released
    mycall = "MP4RROT"
    mymodule = "Z"

    me = Address(callsign=mycall)
    me.set_reflector_module(mymodule)

    them = Address(callsign=refname)
    them.set_reflector_module(theirmodule)

    c = client_blocks(mycall)
    c.connect(refname,theirmodule)
    chain = [c.receiver(), m17parse, m17voiceframes2streams, tee('stream'), teestreamfile('parrot'), m17streams2frames, 
            m17rewriter(src=me,dst=them, streamid=random.randint(1,2**16-1)),
            throttle(27), 
            #nominally 25, but i'm trying a little higher to try to workaround some stuttering in a temporary way 
            #also you totally don't need throttles for most m17 clients, they will just buffer all the packets and play them back xD
            tobytes, c.sender()]
    config = {}
    c.start()
    modules, wait = modular(config, [chain])
    wait(modules)


def streams_toS3(mycall, refname,theirmodule):
    port=17000
    mymodule="T"
    assert( refname.startswith("M17-") and len(refname) <= 7 )
    #should also be able to look up registered port in dns at some point
    host = network.m17ref_name2host(refname)

    me = Address(callsign=mycall)
    me.set_reflector_module(mymodule)
    them = Address(callsign=refname)
    them.set_reflector_module(theirmodule)
    c = client_blocks(mycall)
    rx_chain = [c.receiver(), m17parse, m17voiceframes2streams, tee(''), tee_s3uploader_m17streams('m17','transcribeme'), null ]
    config = {}
    c.start()
    modules, wait = modular(config, [rx_chain])
    wait(modules)

def stream_saver(mycall, refname,theirmodule):
    port=17000
    mymodule="S"
    assert( refname.startswith("M17-") and len(refname) <= 7 )
    #should also be able to look up registered port in dns at some point
    if refname != "M17-XVF":
        host = network.m17ref_name2host(refname)
    else:
        host = "127.0.0.1"
    # print(host)

    me = Address(callsign=mycall)
    me.set_reflector_module(mymodule)
    them = Address(callsign=refname)
    them.set_reflector_module(theirmodule)
    c = client_blocks(mycall)
    rx_chain = [c.receiver(), m17parse, m17voiceframes2streams, tee('stream'), teestreamfile('saved'), null ]
    # rx_chain = [m17parse,... ]
    config = {}
    c.start()
    modules, wait = modular(config, [rx_chain])
    wait(modules)

def client(mycall,mymodule,refname,theirmodule,port=default_port,mode=3200):
    #TODO Update for new APIs
    mode=int(mode) #so we can call modular_client straight from command line
    port=int(port)

    me = Address(callsign=mycall)
    me.set_reflector_module(mymodule)
    them = Address(callsign=refname)
    them.set_reflector_module(theirmodule)
    c = client_blocks(mycall)

    tx_chain = [mic_audio, codec2enc, vox, m17voiceframe, tobytes, c.sender()]
    rx_chain = [c.receiver(), m17parse, payload2codec2, codec2dec, spkr_audio]
    config = default_config(mode)
    config.m17.dst = "%s %s"%(refname,theirmodule)
    config.m17.src = mycall
    print(config)
    c.start()
    modules, wait = modular(config, [tx_chain, rx_chain])
    wait(modules)


##### OLD AND NOT MAINTAINED BUT KEPT BECAUSE THEY DID INTERESTING THINGS #####


def _udp_mirror(refcallsign, port=default_port):
    # reflects your own UDP packets back to you after a delay
    port=int(port)

    pkts = {}
    def packet_handler(sock, active_connections, bs, conn):
        if conn not in pkts:
            pkts[ conn ] = dattr({ "packets":[], "lastseen":time.time()})
        else:
            this = pkts[conn]
            pkts[conn].packets.append( (time.time()-this.lastseen, bs ) )
            pkts[conn].lastseen = time.time()
    def timer(sock):
        def replay(conn,packets):
            for reltime,bs in packets:
                time.sleep(reltime)
                sock.sendto( bs, conn) 
        delthese = []
        for conn in pkts:
            if pkts[conn].lastseen + 10 < time.time():
                #as udp_server is written, this will stop us from recvfrom - and that's okay for now
                #if we have multiple users, we may well timeout on several in a row because of the delays we're seeing here
                #what i wish i had was a setTimeout like in JS, but I'm sure I can do something with asyncio later to get what I want (and actually support multiple udp_mirror users)
                replay(conn, pkts[conn].packets) 
                delthese.append(conn) 
        for conn in delthese:
            del pkts[conn]
    srv = udp_server(port, packet_handler, timer)
    srv()

def _udp_reflector(refcallsign, port=default_port):
    # "Reflects" an incoming stream to all connected users.
    # ✔ So first, we need a way to receive connections and keep track of them, right?
    # We also have our own callsign, but we'll deal with that later.

    port=int(port)
    def packet_handler(sock, active_connections, bs, conn):
        others = [c for c in active_connections.keys() if c != conn]
        for c in others:
            sock.sendto(bs, c)
    srv = udp_server(port, packet_handler)
    srv()

def _to_icecast(icecast_url, mode=3200,port=default_port):
    mode=int(mode) #so we can call modular_client straight from command line
    port=int(port)
    rx_chain = [udp_recv(port), m17parse, payload2codec2, codec2dec, ffmpeg(icecast_url)]
    # rx_chain = [udp_recv(port), m17parse, tee('m17'), payload2codec2, codec2dec, ffmpeg(icecast_url)]
    config = default_config(mode)
    modules, wait = modular(config, [rx_chain])
    wait(modules)

def _to_pcm(mode=3200,port=default_port):
    mode=int(mode) #so we can call modular_client straight from command line
    port=int(port)
    rx_chain = [udp_recv(port), m17parse, tee('m17'), payload2codec2, codec2dec, teefile('m17.raw'), null]
    config = default_config(mode)
    modules, wait = modular(config, [rx_chain])
    wait(modules)

def _recv_dump(mode=3200,port=default_port):
    mode=int(mode) #so we can call modular_client straight from command line
    port=int(port)
    rx_chain = [udp_recv(port), teefile("rx"), m17parse, tee('M17'), payload2codec2, teefile('out.c2_3200'),codec2dec, teefile('out.raw'), spkr_audio]
    config = default_config(mode)
    modules, wait = modular(config, [rx_chain])
    wait(modules)

def _voip(host="localhost",port=default_port,voipmode="full",mode=3200,src="W2FBI",dst="SP5WWP"):
    mode=int(mode) #so we can call modular_client straight from command line
    port=int(port)

    #this requires remote host to have port forwarded properly and everything - it doesn't
    # reuse the server socket connection (which would support NAT traversal)

    #this means the tx and rx paths are completely separate, which is,
    # if nothing else, simple to reason about

    tx_chain = [mic_audio, codec2enc, vox, m17voiceframe, tobytes, udp_send((host,port))]
    rx_chain = [udp_recv(port), m17parse, payload2codec2, codec2dec, spkr_audio]
    if voipmode == "tx":
        #disable the rx chain
        #useful for when something's already bound to listening port
        rx_chain = []
    if voipmode == "rx":
        #disable the tx chain
        #useful for monitoring incoming packets without sending anything
        tx_chain = []
    config = default_config(mode)

    config.m17.dst = dst
    config.m17.src = src
    print(config)

    modules, wait = modular(config, [tx_chain, rx_chain])
    wait(modules)

def _echolink_bridge(mycall,mymodule,refname,refmodule,refport=default_port,mode=3200):
    mode=int(mode) #so we can call modular_client straight from command line
    refport=int(refport)
    if( refname.startswith("M17-") and len(refname) <= 7 ):
        #should also be able to look up registered port in dns
        host = network.m17ref_name2host(refname)
        print(host)
        #fallback to fetching json if its not in dns already
    else:
        raise(NotImplementedError)
    myrefmod = "%s %s"%(mycall,mymodule)
    c = m17ref_client_blocks(myrefmod,refmodule,host,refport)
    echolink_to_m17ref = [udp_recv(55501), chunker_b(640), np_convert("<h"), integer_decimate(2), codec2enc, m17voiceframe, tobytes, c.sender()]
    m17ref_to_echolink = [ c.receiver(), m17parse, payload2codec2, codec2dec, integer_interpolate(2), udp_send(("127.0.0.1",55500)) ]
    config = default_config(mode)
    config.m17.dst = "%s %s"%(refname,refmodule)
    config.m17.src = mycall
    print(config)
    c.start()
    modules, wait = modular(config, [echolink_to_m17ref, m17ref_to_echolink])
    wait(modules)

def _m17_to_echolink(port=default_port, echolink_host="localhost",mode=3200, echolink_audio_in_port=55500):
    port=int(port)
    mode=int(mode)
    echolink_audio_in_port=int(echolink_audio_in_port)
    """
    decode and bridge m17 packets to echolink
    (useful for interopability testing)
    """
    chain = [
            udp_recv(port), 
            m17parse, payload2codec2, codec2dec, 
            integer_interpolate(2), #echolink wants 16k audio
            udp_send((echolink_host,echolink_audio_in_port)) 
            ]
    config = default_config(mode)
    config.verbose = 0
    modules, wait = modular(config, [chain])
    wait(modules)

def _test_chains_example():
    """
    example playground for testing 
    """
    test_chain = [
            mic_audio, 
            codec2enc, #.02ms of audio per q element at c2.3200 in this part of chain
            # delay(5/.02), #to delay for 5s, divide 5s by the time-length of a q element in this part of chain (which does change)
            # tee("delayed c2bytes: "),
            # teefile("out.m17"),
            # vox, 
            # ptt,
            # m17voiceframe, #.04ms of audio per q element at c2.3200
            # tobytes, 
            # udp_send, 
            # udp_recv, 
            # m17parse, 
            # payload2codec2, #back to .02ms per q el
            codec2dec, 
            # null,
            spkr_audio
            ]
    config = default_config(mode)
    config.verbose = 1
    modules, wait = modular(config, [test_chain])
    wait(modules)


if __name__ == "__main__":
    vars()[sys.argv[1]](*sys.argv[2:])

