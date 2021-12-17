import os
import sys
import enum
import time
import json
import struct
import random
import logging
import unittest
import binascii
import socket

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
    def __init__(self, mycallsign, mode, bind=None, peer=None):
        self.mode = mode
        if mode == "server":
            self.log = logging.getLogger("m17refl\t")
            #bind directly to specified port and wait for connections to this reflector
            self.listenconn = peer if peer else ("0.0.0.0",17000)
            self.peer = None
        else:# mode == "client"
            self.log = logging.getLogger("m17client(%s)\t"%(str(peer)))
            self.listenconn = bind if bind else ("0.0.0.0", 17000)
            self.peer = peer

            #bind to a port of my choosing and connect out to remote reflector
        self.nack_count = 0
        self.subs = {}

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
        self.sock.bind(self.listenconn)
        self.sock.setblocking(False)

        self.times = dattr({
                "recv_ping": None,
                "send_ping": None,
                "recv_pong": None,
                "send_pong": None,
                "recv": None,
                "send": None,
                })

    def add_subscription(self, theirmodule ):
        self.subs[theirmodule] = True
    def rm_subscription(self, theirmodule ):
        self.subs[theirmodule] = False
    def add_connection(self, call, my_channel, conn):
        if conn in self.connections:
            return False #already registered, NACK 'em
        new_connection = dattr({
                "call": call,
                "conn": conn,
                "chan": my_channel,
                })
        self.connections[conn] = new_connection
        return True

    def del_connection(self, conn):
        try:
            if conn in self.connections:
                del self.connections[conn]
        except KeyError as e:
            pass

    def check_and_prune_connections(self):
        for call in self.connections:
            self.connections[call].prot.check_and_prune_if_dead()

    @property
    def lastheard(self):
        times = [
                self.times.recv_ping,
                self.times.recv_pong,
                self.times.recv,
                ]
        deltatimes = [time.time() - t for t in times if t is not None]
        print(times,deltatimes)
        if len(deltatimes) > 0:
            return min(deltatimes)
        else:
            return None


    def close(self):
        self.sock.close()

    def connect(self, theirmodule="A"):
        data = b"CONN" + self.mycall_b + theirmodule.encode("ascii")
        self.add_subscription(theirmodule)
        self.send(data)

    def disco(self):
        """
        The official protocol assumes there's only one client per peer 
        (ipv6 is a clear winner to avoid NAT then, eh?)
        and only connected to one module at a time
        which is why DISC doesn't have any way to specify _what_ to disconnect from
        """

        self.log.info("DISC")
        data = b"DISC" + self.mycall_b 
        self.send(data)

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
        callsign_40 = pkt[:6]
        addr = int.from_bytes(callsign_40, 'big')
        theircall = m17.address.Address(addr=addr)
        self.log.info("%s (%s) sent DISC"%(peer, theircall))
        self.del_connection(peer)
        ...

    def pong(self, peer=None):
        data = b"PONG" + self.mycall_b 
        self.times.send_pong = time.time()
        self.send(data, peer)

    def ping(self, peer=None):
        data = b"PING" + self.mycall_b 
        self.times.send_ping = time.time()
        self.send(data, peer)

    def ack(self, peer=None):
        data = b"ACKN"
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
        for peer in self.connections:
            if peer == except_this_peer:
                continue
            self.send(pkt, peer)

    def send(self,  pkt, peer=None):
        if peer is None and self.peer is not None:
            peer = self.peer
        # self.log.debug("SEND %s: %s"%(peer, pkt))
        self.times.send = time.time()
        self.sock.sendto(pkt, peer)

    def recv(self):
        try:
            bs, clientconn = self.sock.recvfrom( 1500 ) 
            self.times.recv = time.time()
        except BlockingIOError as e:
            return None
        return self.handle(bs, clientconn)


    def handle(self, pkt, from_conn):
        # self.log.debug("RECV %s: %s"%(from_conn, pkt))
        if pkt.startswith(b"PING"):
            self.times.recv_ping = time.time()
            self.pong(from_conn)
        elif pkt.startswith(b"PONG"):
            self.times.recv_pong = time.time()
            # self.pong()
        elif pkt.startswith(b"ACKN"):
            #successful connection, but as a client
            self.nack_count = 0
        elif pkt.startswith(b"NACK"):
            #unsuccessful connection, as a client
            self.nack_count += 1
            if self.nack_count < 5:
                self.disco()
                for module, status in self.subs.items():
                    if status:
                        self.connect(module)
            else:
                raise(Exception("Refused (NACK) by reflector"))
        elif pkt.startswith(b"CONN"):
            if self.connect_in( pkt[4:], from_conn):
                self.ack(from_conn)
            else:
                self.nack(from_conn) 
                #really i don't think we should NACK them for already being connected. That's rude.
                #but leaving it as-is for now
        elif pkt.startswith(b"DISC"):
            return self.handle_disc( pkt[4:], from_conn)
        elif pkt.startswith(b"M17 "):
            # self.log.warning("M17 packet magic: %s"%(pkt[:4]))
            return pkt, from_conn
        else:
            self.log.warning("unhandled packet magic: %s"%(pkt[:4]))
            return pkt, from_conn


class simple_n7tae_client():
    def __init__(self, mycall, bind, peer, *args, **kwargs):
        self.mycall = mycall
        #client
        self.sendq = queue.Queue()
        #sendq is packets to be sent out from our service to the socket
        self.recvq = queue.Queue()
        #recvq is packets received from the socket


        self.prot = n7tae_protocol(mycall, mode="client", bind=bind, peer=peer)
        self.proc = threading.Thread(name="mrefd_client", 
                target=self.client, 
                args=( 
                    self.prot,
                    self.sendq,self.recvq, 
                    self.mycall, 
                    ))
        self.proc.daemon = True
        self.start()

    def connect(self, theirmodule):
        return self.prot.connect(theirmodule)
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
    def __init__(self, mycall, bind=None, peer=None, *args, **kwargs):
        #server
        self.mycall = mycall
        self.bind = bind
        self.peer = peer

        self.prot = n7tae_protocol(mycall, mode="server", bind=bind, peer=peer)
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
                if ret is not None:
                    print("SERVER:",ret)
                    pkt, conn = ret
                    prot.send_to_all_except(pkt, conn)
            except BlockingIOError as e:
                pass
            time.sleep(.00001)

class ReflectorProtocolTests(unittest.TestCase):
    def testPingPong(self):
        logging.info("pingpong test")
        a = n7tae_protocol("1",mode="server",bind=("0.0.0.0",17000))
        b = n7tae_protocol("2",mode="client",bind=("0.0.0.0",17001),peer=("127.0.0.1",17000))
        b.ping() #send ping
        a.recv() #a gets ping, pongs
        b.recv() #b gets pong
        self.assertTrue(a.lastheard > 0)
        self.assertTrue(b.lastheard > 0)
        a.close()
        b.close()


    def testConnect(self):
        logging.info("conn test")
        a = n7tae_protocol("1", mode="server", bind=("0.0.0.0",17000))
        b = n7tae_protocol("2", mode="client", peer=("127.0.0.1",17000),bind=("0.0.0.0",17001))
        # b.connect("1", ("127.0.0.1", 17000), "Z")
        b.connect("Z")
        a.recv() 
        b.recv()
        # self.assertTrue(b.is_connected("1","Z"))
        # can't really have state without concurrency for this, eh :/
        a.close()
        b.close()

    def testDisco(self):
        logging.info("disco test")
        a = n7tae_protocol("1", mode="server", bind=("0.0.0.0",17000))
        b = n7tae_protocol("2", mode="client", peer=("127.0.0.1",17000),bind=("0.0.0.0",17001))
        # b.connect("1", ("127.0.0.1", 17000), "Z")
        b.connect("Z")
        a.recv() 
        b.recv()
        a.recv() 
        self.assertTrue(a.lastheard > 0)
        self.assertTrue(b.lastheard > 0)
        b.disco()
        a.recv() 
        b.recv()
        self.assertTrue(a.lastheard > 0)
        self.assertTrue(b.lastheard > 0)
        a.close()
        b.close()

    def testZZClientServer(self):
        logging.info("ClientServer test")
        ref = simple_n7tae_reflector("REFLECTOR", bind=("0.0.0.0", 17000))
        cli1 = simple_n7tae_client("CLIENT1", bind=("0.0.0.0",17010), peer=("127.0.0.1", 17000))
        cli2 = simple_n7tae_client("CLIENT2", bind=("0.0.0.0",17011), peer=("127.0.0.1", 17000))
        cli1.connect('Z')
        cli2.connect('Z')
        i = 0
        cli1.send(b"M17 ABCDEFGHIJKLMNOPQRSTUVWXYZ")
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
        ref = simple_n7tae_reflector("REFLECTOR", bind=("0.0.0.0", 17000))
        cli1 = simple_n7tae_client("CLIENT1", bind=("0.0.0.0",17010), peer=("127.0.0.1", 17000))
        cli2 = simple_n7tae_client("CLIENT2", bind=("0.0.0.0",17011), peer=("127.0.0.1", 17000))
        cli1.connect('Z')
        cli2.connect('X')
        i = 0
        cli1.send(b"M17 ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        while i < 10:
            cli1.send(b"M17 ABCDEF %d"%(i))
            time.sleep(.01)
            x = cli2.recv()
            assert x == None
            i+=1
