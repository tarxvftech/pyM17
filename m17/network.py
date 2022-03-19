import os
import sys
import enum
import time
import json
import struct
import random
import pprint
import socket
import logging
import unittest
import binascii
import subprocess

import queue
import threading
import multiprocessing

import bitstruct
import m17
import m17.misc
from m17.misc import dattr
import m17.address

import requests

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
pp = pprint.pprint


def m17ref_name2host(refname):
    return "%s.m17ref.tarxvf.tech"%(refname)

# def m17ref_name2dict(refname):
    # return "%s.m17ref.tarxvf.tech"%(refname)


class n7tae_protocol:
    """
    Requires 
    * an M17 callsign, 
    * a peer which is "0.0.0.0" and a port when a server, or the remote host and port when a client; 
    * a mode string, either "server" or "client"

    """
    def __init__(self, mycallsign, bind=None):
        self.log = logging.getLogger("n7tae")
        if bind:
            self.bind = bind
        else:
            self.bind = ("",17000+random.randint(1,999))
        self.peer = None
        self.starttime = time.time()


        #self.connections, a dict where 
        #   key is a udp socket (host,port) pair 
        #   and 
        #   value is an instance of n7tae_reflector_protocol
        #   or maybe key is a callsign? i like that better - except that can't work because we'll just end up looking up the call from the conn pair anyway!
        self.connections = {}

        self.mycallsign = mycallsign
        self.mycall_b = bytes(m17.address.Address(callsign=self.mycallsign))

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(self.bind)
        self.sock.setblocking(False)

    def is_alive(self, call=None, module=None, peer=None):
        #normalize call to peer, and peer to ip
        if not peer and not call:
            raise(Exception("What exactly are you connecting to? Provide either a host,port tuple or a reflector name"))
        elif not peer and call:
            host = m17ref_name2host(call)
            port = 17000
            peer = (host,port)
        ip = socket.gethostbyname(peer[0])
        if ip != peer[0]:
            peer = (ip,peer[1])

        if peer in self.connections:
            conn = self.connections[peer]
            now = time.time()
            times = [
                    conn.times.recv_ping,
                    conn.times.recv_pong,
                    conn.times.recv,
                    ]
            deltatimes = [now - t for t in times if t is not None]
            up = [t < 5 for t in deltatimes ]
            if any(up):
                return True
        return False

    def add_connection(self, call, module, peer):
        if peer in self.connections:
            return False #already registered, NACK 'em
        else:
            new_connection = dattr({
                    "call": call,
                    "module": module,
                    "original_peer": peer,
                    "nack_count": 0,
                    "ping_count": 0,
                    "pong_count": 0,
                    "disc_count": 0,
                    "times": dattr({
                        "recv_ping": None,
                        "send_ping": None,
                        "recv_pong": None,
                        "send_pong": None,
                        "recv": None,
                        "send": None,
                        })
                    })
            ip = socket.gethostbyname(peer[0])
            if ip != peer[0]:
                peer = (ip,peer[1])
        #we depend on the key in self.connections to be the ip,port tuple we will get from udp socket listener 
        #if it's a hostname, it won't match!
        #TODO: cache hostnames and check
        self.connections[peer] = new_connection
        return True

    def del_connection(self, peer):
        try:
            if peer in self.connections:
                del self.connections[peer]
        except KeyError as e:
            pass

    # def check_and_prune_connections(self):
        # for call in self.connections:
            # self.connections[call].prot.check_and_prune_if_dead()

    # @property
    # def lastheard(self):
        # times = [
                # self.times.recv_ping,
                # self.times.recv_pong,
                # self.times.recv,
                # ]
        # deltatimes = [time.time() - t for t in times if t is not None]
        # print(times,deltatimes)
        # if len(deltatimes) > 0:
            # return min(deltatimes)
        # else:
            # return None


    def close(self):
        self.sock.close()

    def connect(self, call=None, module="A", peer=None):
        if not peer and not call:
            raise(Exception("What exactly are you connecting to? Provide either a host,port tuple or a reflector name"))
        elif not peer and call:
            host = m17ref_name2host(call)
            port = 17000
            peer = (host,port)
        #else we got both or just peer, and peer takes precedence over call anyway
        
        self.add_connection(call,module,peer)
        #you might think we should only add the connection if it succeeds - but it's pretty often
        # we need to retry after a NACK+DISC conversation. Saving the connection allows us to track it and keep retrying.
        # we'll need a way to catch failing and flapping connections anyway, so need to expand the API in that direction
        data = b"CONN" + self.mycall_b + module.encode("ascii")
        self.send(data, peer)

    def disco(self, peer, sendcall=True):
        """
        The official protocol assumes there's only one client per peer 
        (ipv6 is a clear winner to avoid NAT then, eh?)
        and only connected to one module at a time
        which is why DISC doesn't have any way to specify _what_ to disconnect from
        """

        self.log.info("DISC")
        data = b"DISC"
        if sendcall:
            data += self.mycall_b 
        self.send(data, peer)

    def connect_in(self, pkt, peer):
        """
        pkt must not have the front magic bytes (4 bytes)
        so make sure to strip them (i.e. pass in pkt[4:] )
        """
        callsign_40 = pkt[:6]
        my_channel = chr(pkt[6])

        addr = int.from_bytes(callsign_40, 'big')
        theircall = m17.address.Address(addr=addr)
        self.log.info("Connection attempt from %s to my %s"%( theircall, my_channel))
        return self.add_connection(theircall, my_channel, peer)

    def handle_disc(self, pkt, peer):
        """
        pkt must not have the front magic bytes (4 bytes)
        so make sure to strip them (i.e. pass in pkt[4:] )
        """
        #TODO reflector sends CONN when it receives  DISC
        #need to handle when DISC has no callsign to disconnect
        #and use that to know to delete the connection and do nothing further
        callsign_40 = pkt[:6]
        addr = int.from_bytes(callsign_40, 'big')
        theircall = m17.address.Address(addr=addr)
        self.log.info("%s (%s) sent DISC"%(peer, theircall))
        self.connections[peer].disc_count += 1
        if self.connections[peer].disc_count > 5:
            self.log.warning("%s (%s) sent DISC too many times, deleting connection"%(peer, theircall))
            self.del_connection(peer)
        else:
            if addr:
                self.disco(peer,sendcall=False)
            conn = self.connections[peer]
            #TODO gets into loops with two peers
            self.connect(conn.call, conn.module, conn.original_peer)

    def pong(self, peer=None):
        data = b"PONG" + self.mycall_b 
        if peer in self.connections:
            self.connections[peer].times.send_pong = time.time()
        self.send(data, peer)

    def ping(self, peer=None):
        data = b"PING" + self.mycall_b 
        if peer in self.connections:
            self.connections[peer].times.send_ping = time.time()
        self.send(data, peer)

    def ack(self, peer=None):
        data = b"ACKN"
        self.send(data, peer)

    def info(self, peer=None):
        data = b"INFO"
        self.send(data, peer)
    def up_p(self, peer=None):
        data = b"UP? "
        self.send(data, peer)
    def alive(self, peer=None):
        data = b"ALIV"
        self.send(data, peer)

    def nack(self, peer=None):
        data = b"NACK"
        self.send(data, peer)

    def check_and_prune_if_dead(self):
        # self.ping()
        # check last_[recv,send]_p[i,o]ngtime times and act "appropriately"
        # self.del_connection(call)
        pass

    def send_to_all_except(self,  pkt, except_this_peer):
        peers = [peer for peer in self.connections if peer != except_this_peer]
        if peers:
            self.send(pkt, peers=peers)

    def send(self,  pkt, peer=None, peers=None):
        if peer is None and peers is None:
            peers = [peer for peer in self.connections]
            if len(peers) > 1:
                self.log.warning("Implicitly sending to multiple peers, this is unexpected at the moment")

        for p in peers or [peer]:
            # self.log.debug("SEND %s: %s"%(peer, pkt))
            if p in self.connections:
                self.connections[p].times.send = time.time()
            if p != None:
                self.sock.sendto(pkt, p)

    def recv(self):
        try:
            bs, peer = self.sock.recvfrom( 1500 ) 
            if peer in self.connections:
                self.connections[peer].times.recv = time.time()
            else:
                if bs[:4] not in  [b"CONN",b"PING",b"PONG"]: #TODO: add ALIV, UP?, etc
                    #drop it on the floor? or nack it?
                    # self.nack(peer)
                    # pp(self.connections)
                    self.log.warning("packet from unregistered peer %s:%d %s..."%(peer[0],peer[1], binascii.hexlify(bs[:16])))
                    return None
                else:
                    print(peer,bs[:4])
                    self.log.debug("packet from unregistered peer %s:%d %s..."%(peer[0],peer[1], binascii.hexlify(bs[:16])))
        except BlockingIOError as e:
            return None
        return self.handle(bs, peer)


    def handle(self, pkt, peer):
        #recv should ensure peer is in our active connections list before calling us
        #except for CONN, PING, and PONG
        # self.log.debug("RECV %s: %s"%(peer, pkt))
        if pkt.startswith(b"PING"):
            if peer in self.connections:
                self.connections[peer].times.recv_ping = time.time()
                self.connections[peer].ping_count += 1
            self.pong(peer)
        elif pkt.startswith(b"ALIV"):
            self.alive(peer)
        elif pkt.startswith(b"UP  "):
            pass
        elif pkt.startswith(b"UP? "):
            self.send(b"UP  " + "✔ ".encode("utf-8"), peer)
        elif pkt.startswith(b"INFO"):
            if len(pkt) == 4:
                #query, so respond
                uptime = subprocess.getoutput("uptime")
                info = {"name":"pyM17", "version":"0.9", "protocol":"2021-12-22-dev", "hostuptime":uptime, "reflectoruptime": time.time()-self.starttime}
                self.send(b"INFO" + json.dumps(info).encode("utf-8"), peer)
            else:
                #reply, so don't respond
                print(pkt)
        elif pkt.startswith(b"PONG"):
            if peer in self.connections:
                self.connections[peer].times.recv_pong = time.time()
                self.connections[peer].pong_count += 1
        elif pkt.startswith(b"ACKN"):
            #successful connection, but as a client
            call = self.connections[peer].call
            self.log.info("ACKN, connected with %s"%(call))
            self.connections[peer].nack_count = 0
            self.connections[peer].disc_count = 0
        elif pkt.startswith(b"NACK"):
            #unsuccessful connection, as a client
            self.connections[peer].nack_count += 0
            if self.connections[peer].nack_count < 5:
                #if we got a nack, we are probably just already registered from a previous session that hasn't timed out
                #so disconnect that session and try again
                self.disco(peer)
            else:
                #if after five tries, finally give up
                #this will currently bring everything to a screeching halt :)
                raise(Exception("Refused (NACK) by reflector"))
        elif pkt.startswith(b"CONN"):
            if self.connect_in( pkt[4:], peer):
                self.ack(peer)
            else:
                self.nack(peer) 
                #really i don't think we should NACK them for already being connected. That's rude.
                #but leaving it as-is for now
        elif pkt.startswith(b"DISC"):
            if len(pkt) > 4:
                return self.handle_disc( pkt[4:], peer)
            else:
                if peer in self.connections:
                    self.del_connection(peer=peer)
        elif pkt.startswith(b"M17 "):
            # self.log.warning("M17 packet magic: %s"%(pkt[:4]))
            return pkt, peer
        else:
            self.log.warning("unhandled packet magic: %s"%(pkt[:4]))
            return pkt, peer


class simple_n7tae_client():
    def __init__(self, mycall, bind, *args, **kwargs):
        self.mycall = mycall
        #client
        self.sendq = queue.Queue()
        #sendq is packets to be sent out from our service to the socket
        self.recvq = queue.Queue()
        #recvq is packets received from the socket


        self.prot = n7tae_protocol(mycall, bind=bind)
        self.proc = threading.Thread(name="mrefd_client", 
                target=self.client, 
                args=( 
                    self.prot,
                    self.sendq,
                    self.recvq, 
                    self.mycall, 
                    ))
        self.proc.daemon = True
        self.start()

    def connect(self, *args, **kwargs):
        return self.prot.connect(*args,**kwargs)
    def start(self):
        self.proc.start()
    def join(self):
        self.proc.join()
    def send(self, pkt):
        self.sendq.put_nowait(pkt)
    def recv(self):
        if not self.recvq.empty():
            return self.recvq.get_nowait()
        else:
            return None

    def client(self, prot, sendq, recvq, mycall):
        while 1:
            try:
                ret = prot.recv()
                if ret:
                    # print("CLIENT:",ret)
                    pkt, conn = ret
                    recvq.put( pkt ) 
            except BlockingIOError as e:
                pass
            if not sendq.empty():
                data = sendq.get_nowait()
                # print("SEND", data )
                prot.send( data )
            time.sleep(.00001)

class simple_n7tae_reflector():
    def __init__(self, mycall, bind=None, *args, **kwargs):
        #server
        self.mycall = mycall
        self.bind = bind

        self.prot = n7tae_protocol(mycall, bind=bind)
        self.proc = threading.Thread(name="mrefd-like_reflector", 
                target=self.server, 
                args=( 
                    self.prot,
                    self.mycall, 
                    ))
        if not kwargs.get('nodaemon'):
            self.proc.daemon = True
        self.proc.start()

    def join(self):
        self.proc.join()

    def server(self, prot, mycall):
        """
        """
        while 1:
            try:
                ret = prot.recv() 
                #only spits out packets the protocol itself doesn't handle but is otherwise transparent
                #e.g. no filtering or anything
                if ret is not None:
                    print("SERVER:",ret)
                    pkt, conn = ret
                    prot.send_to_all_except(pkt, conn)
            except BlockingIOError as e:
                pass
            time.sleep(.00001)

class reflector_checker(simple_n7tae_client):
    def start_check(self, call=None, peer=None):
        self.prot.connect(call,"Z", peer)
    def close(self):
        peers = list(self.prot.connections.keys()) 
        #list() allows us to avoid modifying the thing we're iterating over
        #by del_connection-ing the peer
        for peer in peers: 
            #del before DISC otherwise we may try to CONN again?
            #TODO this isn't sufficient...
            self.prot.del_connection(peer=peer)
            self.prot.disco(peer=peer)
        self.prot.close()
    def results(self):
        reflist = map(lambda x: x.call, self.prot.connections.values())
        return {ref: self.prot.is_alive(call=ref) for ref in reflist}

class ReflectorProtocolTests(unittest.TestCase):
    def testPingPong(self):
        logging.info("pingpong test")
        ap = ("127.0.0.1",17000)
        bp = ("127.0.0.1",17001)
        a = n7tae_protocol("1",bind=ap)
        b = n7tae_protocol("2",bind=bp)
        b.connect(peer=ap)
        a.recv() 
        b.recv()
        b.ping(ap) #send ping
        a.recv() #a gets ping, pongs
        b.recv() #b gets pong

        #TODO: lastheard needs to be updated to handle multiple peers
        # self.assertTrue(a.lastheard > 0)
        # self.assertTrue(b.lastheard > 0)
        a.close()
        b.close()


    def testConnect(self):
        logging.info("conn test")
        ap = ("127.0.0.1",17000)
        bp = ("127.0.0.1",17001)
        a = n7tae_protocol("1",bind=ap)
        b = n7tae_protocol("2",bind=bp)
        # b.connect("1", ("127.0.0.1", 17000), "Z")
        b.connect(peer=ap)
        a.recv() 
        b.recv()
        # self.assertTrue(b.is_connected("1","Z"))
        # can't really have state without concurrency for this, eh :/
        a.close()
        b.close()

    def testDisco(self):
        logging.info("disco test")
        ap = ("127.0.0.1",17000)
        bp = ("127.0.0.1",17001)
        a = n7tae_protocol("1",bind=ap)
        b = n7tae_protocol("2",bind=bp)
        b.connect(peer=ap)
        a.recv() 
        b.recv()
        a.recv() 
        # self.assertTrue(a.lastheard > 0)
        # self.assertTrue(b.lastheard > 0)
        b.disco(ap)
        a.recv() 
        b.recv()
        # self.assertTrue(a.lastheard > 0)
        # self.assertTrue(b.lastheard > 0)
        a.close()
        b.close()

    def testZZClientServer(self):
        logging.info("ClientServer test")
        ap = ("127.0.0.1",17000)
        bp = ("127.0.0.1",17010)
        cp = ("127.0.0.1",17011)
        ref = simple_n7tae_reflector("REFLECTOR", bind=ap)
        cli1 = simple_n7tae_client("CLIENT1", bind=bp)
        cli2 = simple_n7tae_client("CLIENT2", bind=cp)
        cli1.connect(peer=ap)
        cli2.connect(peer=ap)
        time.sleep(.05) #yield to the reflector
        i = 0
        cli1.send(b"M17 ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        time.sleep(.01) #yield to the reflector
        while i < 10:
            cli1.send(b"M17 ABCDEF %d"%(i))
            time.sleep(.01)
            x = cli2.recv()
            assert x != None
            i+=1
        x = cli2.recv()
        assert x != None

        #and now expect nothing
        x = cli2.recv()
        assert x == None
        # cli1.recv()
        # ref.join()

    def XZClientServer(self):
        # disabled by removing "test" from name until such time as modules are added to the python reflector implentation above
        logging.info("ClientServer - different modules test")
        ap = ("127.0.0.1",17000)
        bp = ("127.0.0.1",17010)
        cp = ("127.0.0.1",17011)
        ref = simple_n7tae_reflector("REFLECTOR", bind=ap)
        cli1 = simple_n7tae_client("CLIENT1", bind=bp)
        cli2 = simple_n7tae_client("CLIENT2", bind=cp)
        cli1.connect(module="Z",peer=ap)
        cli2.connect(module="X",peer=ap)
        cli1.send(b"M17 ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        time.sleep(.01)
        x = cli2.recv()
        # assert x == None
