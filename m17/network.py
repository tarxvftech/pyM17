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

import bitstruct
import m17
import m17.misc
from m17.misc import dattr
import m17.address

class m17_networking:
    def __init__(self, callsign, primaries):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind( ("0.0.0.0", 17000) )
        # self.sock.bind( ("::1", 17000) )

        self.recvQ = queue.Queue()
        receiverT = threading.Thread(target=self.recv)
        receiverT.start()

        self.conns = {}

        self.whereis = {}
        self.primaries = []
        self.callsign = callsign

        self.last = 0
        self.registration_period = 15

    def recv(self):
        """
        """
        while 1:
            data,conn = self.sock.recvfrom(1500)
            self.recvQ.put((data,conn))

    def loop(self):
        def looper(self):
            while 1:
                self.loop_once()
                time.sleep(.001)
        self.looper = threading.Thread(target=looper, args=(self,))
        self.looper.start()

    def loop_once(self):
        self.register_loop_once()
        if not self.recvQ.empty():
            data,conn = self.recvQ.get_nowait()
            if conn[0] not in self.conns:
                self.conns[ conn[0] ] = dattr({
                    "last": time.time(),
                    "port": conn[1]
                        })
            else:
                self.conns[ conn[0] ].last = time.time()
            self.process_packet( data, conn )

    def register_loop_once(self):
        if not self.callsign:
            return
        sincelastrun = time.time() - self.last
        if sincelastrun > self.registration_period:
            addr = m17.address.Address.encode(self.callsign)
            payload = json.dumps({"msgtype":"i am here", "m17_addr": addr }).encode("utf-8")
            for primary in primaries:
                self.registration_send(payload, primary)
            self.last = time.time()

    def process_packet(self, payload, conn):
        if payload.startswith(b"M17 "):
            ...
            #voice and data packets
        if payload.startswith(b"M17M"):
            self.rendezvous_process_packet(payload[4:], conn)
        if payload.startswith(b"M17R"):
            self.registration_process_packet(payload[4:], conn)

    def registration_process_packet(self, payload, conn):
        msg = dattr(json.loads(payload.decode("utf-8")))
        callsign = m17.address.Address.decode(msg.m17_addr)
        if msg.msgtype == "i am here": #remote host asks to tie their host and callsign together
            self.registration_store(callsign, conn) #so we store it
        if msg.msgtype == "where is?": #getting a query for a stored callsign
            loc,port,lastseen = self.query( callsign )
            self.registration_reply( conn, callsign, loc)
        if msg.msgtype == "is at": #getting a reply to a query
            print("Found %s at %s!"%(callsign, msg.host))
            # self.store( callsign, packet.srchost)
            ... #and now we continue with what we were trying to do, i s'pose
            # request rendezvous? here isn't where I want it to happen, but lets prove the concept i guess
            self.request_rendezvous(msg.host)

    def rendezvous_process_packet(self, payload, conn):
        msg = dattr(json.loads(payload.decode("utf-8")))
        if msg.msgtype == "introduce me?": #got a request: please introduce me to host, i'm trying to talk to them on port...
            ...
            #make a packet each to introduce peer1 and peer2
            self.arrange_rendezvous(conn,msg)
        if msg.msgtype == "introducing": #got an intro: I have an introduction for you, please contact ...
            #make packets to punch holes allowing other peer to contact us
            self.attempt_rendezvous(conn,msg)
        if msg.msgtype == "hi!": #got an "oh hey" packet
            #ignore it, it's just there to poke a hole so we can receive datagrams through it
            print("Got an opening packet from %s!"%(str(conn)))

    def store(self, callsign, host, port):
        print("[%s]\t[M17 registration] %s -> %s"%(self.host.hostname, callsign, host))
        self.whereis[ callsign ] = (host,port,time.time())

    def query( self, callsign ):
        return self.whereis[callsign]

    def registration_send(self, payload, conn):
        print("Sending to %s M17R %s"%(conn,payload))
        self.sock.sendto(b"M17R" + payload, conn)
    def rendezvous_send(self, payload, conn):
        print("Sending to %s M17M %s"%(conn,payload))
        self.sock.sendto(b"M17M" + payload, conn)

    def query_primary( self, callsign):
        addr = m17.address.Address.encode(callsign)
        payload = json.dumps({"msgtype":"where is?", "m17_addr": addr }).encode("utf-8")
        for primary in self.primaries:
            self.registration_send(payload, primary)


    def reply( self, packet, callsign, loc ):
        addr = m17.address.Address.encode(callsign)
        payload = json.dumps({"msgtype":"is at", "m17_addr": addr, "host":loc }).encode("utf-8")
        self.rendezvous_send(payload, conn)



    def request_rendezvous(self, dsthost):
        payload = json.dumps({"msgtype":"introduce me?", "addr": dsthost, "port":17000 }).encode("utf-8")
        for introducer in self.primaries:
            self.rendezvous_send(payload, introducer)
    
    def arrange_rendezvous(self, conn, msg):
        # requires peer1 and peer2 both be connected live to self (e.g. keepalives)
        # make packet to send to peer1 with payload initiating connection to peer2 and vice versa
        payload = json.dumps({"msgtype":"introducing", "addr": conn[0], "port":17000 }).encode("utf-8")
        self.rendezvous_send(payload, (msg.addr,17000)) #we need to arrange the port too, don't we?
        payload = json.dumps({"msgtype":"introducing", "addr": msg.addr, "port":17000}).encode("utf-8")
        self.rendezvous_send(payload, conn)

    def attempt_rendezvous(self, conn, msg):
        payload = json.dumps({"msgtype":"hi!"}).encode("utf-8")
        self.rendezvous_send(payload, (msg.addr,17000))


if __name__ == "__main__":
    primaries = [("m17.programradios.com.",17000)]
    x = m17_networking(sys.argv[1], primaries)
    # while 1:
        # x.loop_once()
    x.loop()
    time.sleep(5)
    for each in sys.argv[2:]:
        x.query_primary(each)
        time.sleep(1)
    time.sleep(30)
