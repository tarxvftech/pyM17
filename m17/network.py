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

class n7tae_reflector_base:
    def __init__(self, 
            mycall, #always used!
            #bind details if server, destination if client
            *args, **kwargs
            ):
        self.mycall = mycall
        self.host = kwargs.get("host","0.0.0.0")
        self.port = kwargs.get("port", 17000)
        #required: 
        #self.connections, a dict where 
        #   key is a udp socket (host,port) pair 
        #   and 
        #   value is an instance of n7tae_reflector_protocol
        #   or maybe key is a callsign? i like that better - except that can't work because we'll just end up looking up the call from the conn pair anyway!
        self.connections = {}

        #implementations must also have self.sendq and self.recvq queues appropriate for threading or multiprocessing or whatever
        #recvq is packets received from the socket
        #sendq is packets to be sent out from our service

    def add_connection(self, call, my_channel, conn, prot):
        if conn in self.connections:
            return False #already registered, NACK 'em
        new_connection = dattr({
                "call": call,
                "conn": conn,
                "chan": my_channel,
                "prot": prot
                })
        self.connections[conn] = new_connection
        return True

    def del_connection(self, conn):
        del self.connections[conn]

    def check_and_prune_connections(self):
        for call in self.connections:
            self.connections[call].prot.check_and_prune_if_dead()


class n7tae_reflector_protocol_base:
    """

    Requires 
    * an M17 callsign, 
    * a peer which is "0.0.0.0" and a port when a server, or the remote host and port when a client; 
    * a parent (service) that is reponsible for the actual application using the reflector protocol, and probably handles the concurrency necessary
    * a mode string, either "server" or "client"

    the service parameter currently needs to implement:
        service.add_connection(call, chan, conn, protocol) (where protocol is an instance of n7tae_reflector_protocol, so pass self)
        service.del_connection(conn) 
    The service should also call status check methods of this class as appropriate:
        check_connection

    """
    def __init__(self, mycallsign, peer, service, mode):
        host,port = peer
        self.mode = mode
        self.log = logging.getLogger("m17refl(%s: %s:%d)\t"%(mode,peer[0].rjust(10), peer[1]))
        if mode == "server":
            #bind directly to specified port and wait for connections to this reflector
            self.listenconn = peer
            self.peer = None
        else:# mode == "client"
            self.listenconn = ("0.0.0.0", 17010)
            self.peer = peer

            #bind to a port of my choosing and connect out to remote reflector

        self.mycallsign = mycallsign
        self.mycall_b = bytes(m17.address.Address(callsign=self.mycallsign))
        self.service = service #parent, usually a reflector or client

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

    @property
    def lastheard(self):
        times = [
                self.times.recv_ping,
                self.times.recv_pong,
                self.times.recv,
                ]
        deltatimes = [time.time() - t for t in times if t is not None]
        if len(deltatimes) > 0:
            return min(deltatimes)
        else:
            return None


    def close(self):
        self.sock.close()

    def connect(self, module="A"):
        data = b"CONN" + self.mycall_b + module.encode("ascii")
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
        self.log.info("Connection from %s to my %s"%( theircall, my_channel))
        return self.service.add_connection(theircall, my_channel, peer, self)

    def handle_disc(self, pkt, peer):
        """
        pkt must not have the front magic bytes (4 bytes)
        so make sure to strip them (i.e. pass in pkt[4:] )
        """
        callsign_40 = pkt[:6]
        addr = int.from_bytes(callsign_40, 'big')
        theircall = m17.address.Address(addr=addr)
        self.log.info("%s (%s) sent DISC"%(peer, theircall))
        self.service.del_connection(peer)
        ...

    def pong(self, peer=None):
        data = b"PONG" + self.mycall_b 
        self.send(data, peer)
        self.times.last_send_pong = time.time()

    def ping(self, peer=None):
        data = b"PING" + self.mycall_b 
        self.send(data, peer)
        self.times.last_send_ping = time.time()
    def ack(self, peer=None):
        data = b"ACKN"
        self.send(data, peer)
    def nack(self, peer=None):
        data = b"NACK"
        self.send(data, peer)

    def check_and_prune_if_dead(self):
        # self.ping()
        # check last_[recv,send]_p[i,o]ngtime times and act "appropriately"
        # self.service.del_connection(call)
        pass

    def send(self,  pkt, peer=None):
        if peer is None and self.peer is not None:
            peer = self.peer
        self.log.debug("SEND %s: %s"%(peer, pkt))
        self.sock.sendto(pkt, peer)
        self.times.send = time.time()

    def recv(self):
        try:
            bs, clientconn = self.sock.recvfrom( 1500 ) 
            self.times.recv = time.time()
        except BlockingIOError as e:
            return None
        return self.handle(bs, clientconn)


    def handle(self, pkt, from_conn):
        self.log.debug("RECV %s: %s"%(from_conn, pkt))
        if pkt.startswith(b"PING"):
            self.times.last_recv_ping = time.time()
            self.pong(from_conn)
        elif pkt.startswith(b"PONG"):
            self.times.last_recv_pong = time.time()
            # self.pong()
        elif pkt.startswith(b"ACKN"):
            #successful connection, but as a client
            # self.add_connection()
            pass
        elif pkt.startswith(b"NACK"):
            #unsuccessful connection, as a client
            # self.disco()
            #do more than this, like disco, reconnect, etc
            raise(Exception("Refused (NACK) by reflector"))
        elif pkt.startswith(b"CONN"):
            if self.connect_in( pkt[4:], from_conn):
                self.ack(from_conn)
            else:
                self.nack(from_conn)
        elif pkt.startswith(b"DISC"):
            return self.handle_disc( pkt[4:], from_conn)
        else:
            self.log.warning("unhandled")
            # assert pkt[:4] == b"M17 "
            return pkt, from_conn

class asyncio_n7tae_reflector(n7tae_reflector_base):
    def __init__(self, *args, **kwargs):
        super().__init__(*args,**kwargs)

class simple_n7tae_reflector_client(n7tae_reflector_base):
    def __init__(self, *args, **kwargs):
        super().__init__(*args,**kwargs, mode="client")
        self.refcall=kwargs.get("refcall")
        self.refmodule=kwargs.get("refmodule")

class simple_n7tae_reflector(n7tae_reflector_base):
    def __init__(self, *args, **kwargs):
        super().__init__(*args,**kwargs, mode="server")

        #server
        self.sendq = multiprocessing.Queue()
        self.recvq = multiprocessing.Queue()
        self.manager = multiprocessing.Manager()
        self.connections = self.manager.dict()

        self.srv_process = multiprocessing.Process(name="n7tae-like_reflector", 
                target=self.server, 
                args=( 
                    self.sendq,self.recvq, 
                    self.connections,
                    self.mycall, 
                    self.host, 
                    self.port
                    ))

    def start(self):
        self.srv_process.start()

    def join(self):
        self.srv_process.join()

    def server(self, sendq, recvq, connections, mycall, host,port):
        """
        """
        srv_conn = (host, port)
        # sock = udp_non_blocking_server(srv_conn)
        prot = n7tae_reflector_protocol(mycall, srv_conn, service=self, mode="server")
        while 1:
            try:
                _ = prot.recv()
                # pktmagic, pkt, _, _ = remainder
                # recvq.put( (pktmagic, pkt, clientconn) )
                # if bs.startswith(b"M17 "):
                    # recvq.put( (bs,clientconn) ) #could also hand conn along later
            except BlockingIOError as e:
                pass
            if not sendq.empty():
                data,udpconn= sendq.get_nowait()
                print("SEND", data,udpconn)
                prot.send( data, udpconn)
            time.sleep(.000001)

    def reflector(self):
        while 1:
            pkt, from_conn = self.recvq.get()
            for conn in self.connections:
                if conn == from_conn:
                    continue
                self.connections[conn].prot.send(pkt)

class ReflectorProtocolTests(unittest.TestCase):
    def testPingPong(self):
        logging.info("pingpong test")
        a = n7tae_reflector_protocol_base("1",("0.0.0.0",17000), None,mode="server")
        b = n7tae_reflector_protocol_base("2",("127.0.0.1",17000), None,mode="client")
        b.ping() #send ping
        a.recv() #a gets ping, pongs
        b.recv() #b gets pong
        self.assertTrue(a.lastheard > 0)
        self.assertTrue(b.lastheard > 0)
        a.close()
        b.close()


    def testConnect(self):
        logging.info("conn test")
        asrv = n7tae_reflector_base("1")
        a = n7tae_reflector_protocol_base("1", ("0.0.0.0",17000), asrv, mode="server")
        b = n7tae_reflector_protocol_base("2", ("127.0.0.1",17000), None, mode="client")
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
        asrv = n7tae_reflector_base("1")
        bsrv = n7tae_reflector_base("2")
        #don't worry, this weird split API isn't sticking around
        a = n7tae_reflector_protocol_base("1", ("0.0.0.0",17000), asrv, mode="server")
        b = n7tae_reflector_protocol_base("2", ("127.0.0.1",17000), bsrv, mode="client")
        # b.connect("1", ("127.0.0.1", 17000), "Z")
        b.connect("Z")
        a.recv() 
        b.recv()
        self.assertTrue(a.lastheard > 0)
        self.assertTrue(b.lastheard > 0)
        b.disco()
        a.recv() 
        b.recv()
        self.assertTrue(a.lastheard > 0)
        self.assertTrue(b.lastheard > 0)
        a.close()
        b.close()
