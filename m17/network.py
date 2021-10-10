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

        #implementations must also have self.sendq and self.recvq queues appropriate for threading or multiprocessing or whatever
        #recvq is packets received from the socket
        #sendq is packets to be sent out from our service

    def add_connection(self, call, conn, prot):
        new_connection = dattr({
                call: call,
                conn: conn,
                prot: prot
                })
        self.connections[conn] = new_connection

    def del_connection(self, conn):
        del self.connections[conn]

    def check_and_prune_connections(self):
        for call in self.connections:
            self.connections[call].prot.check_and_prune_if_dead()

class n7tae_reflector_protocol:
    """

    Requires an M17 callsign, 
    a peer (udpconn) which is "0.0.0.0" and a port when a server, and a parent (service)
    the service parameter currently needs to implement:
        service.add_connection(call, conn, protocol) (where protocol is an instance of n7tae_reflector_protocol, so pass self)
        service.del_connection(conn) 
    The service should also call status check methods of this class as appropriate:
        check_connection

    Can be subclassed to override send() for other protocols i guess
    """
    def __init__(self, mycallsign, udpconn, sock, service, mode="client"):
        self.mycallsign=mycallsign
        self.mycall_b = bytes(m17.address.Address(callsign=self.mycallsign))
        self.udpconn = udpconn
        self.service = service #parent, usually a reflector or client
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(udpconn)
        self.sock.setblocking(False)


        if mode=="server":
            ...

    def connect_out(self ):
        data = b"CONN" + self.mycall_b + self.module.encode("ascii")
        self.send(data )

    def disco(self):
        printf("DISC")
        data = b"DISC" + self.mycall_b 
        self.send(data)

    def connect_in(self, pkt):
        """
        pkt must not have the front magic bytes (4 bytes)
        so make sure to strip them (i.e. pass in pkt[4:] )
        """
        print("Connection from ", udpconn);
        print("pkt:", pkt);
        callsign_40 = pkt[:6]
        my_channel = chr(pkt[6])
        print(callsign_40)

        addr = int.from_bytes(callsign_40, 'big')
        print(addr)
        theircall = m17.address.Address(addr=addr)
        print("from: ", theircall, " for my module ",my_channel)
        ...

    def handle_disc( pkt):
        """
        pkt must not have the front magic bytes (4 bytes)
        so make sure to strip them (i.e. pass in pkt[4:] )
        """
        callsign_40 = pkt[:6]
        addr = int.from_bytes(callsign_40, 'big')
        theircall = m17.address.Address(addr=addr)
        ...

    def pong(self):
        data = b"PONG" + self.mycall_b 
        self.send(data)
        self.last_send_pongtime = time.time()

    def ping(self):
        data = b"PING" + self.mycall_b 
        self.send(data)
        self.last_send_pingtime = time.time()

    def check_and_prune_if_dead(self):
        # self.ping()
        # check last_[recv,send]_p[i,o]ngtime times and act "appropriately"
        # self.service.del_connection(call)
        pass

    def send(self,  pkt):
        print("SEND:", pkt)
        self.sock.sendto(pkt, self.udpconn)

    def recv(self):
        bs, clientconn = self.sock.recvfrom( 1500 ) 
        return self.handle(bs, clientconn)

    def handle(self, pkt, from_conn):
        print("RECV:", pkt)
        if pkt.startswith(b"PING"):
            self.last_recv_pingtime = time.time()
            self.pong()
        if pkt.startswith(b"PONG"):
            self.last_recv_pongtime = time.time()
            # self.pong()
        elif pkt.startswith(b"ACKN"):
            pass
        elif pkt.startswith(b"NACK"):
            self.disco()
            #do more than this, like disco, reconnect, etc

            raise(Exception("Refused by reflector"))
        elif pkt.startswith(b"CONN"):
            return self.connect_in( pkt[4:])
        elif pkt.startswith(b"DISC"):
            return self.handle_disc( pkt[4:])
        else:
            assert pkt[:4] == b"M17 "
            ...




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
                prot.send( data, udpconn, sock)
            time.sleep(.000001)

    def reflector(self):
        while 1:
            pkt, from_conn = self.recvq.get()
            for conn in self.connections:
                if conn == from_conn:
                    continue
                self.connections[conn].prot.send(pkt)


