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
    def __init__(self, primaries, callsign, port=17000):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind( ("0.0.0.0", port) )
        self.sock.setblocking(False)
        # self.sock.bind( ("::1", 17000) )

        self.recvQ = queue.Queue()
        self.sendQ = queue.Queue()
        network = threading.Thread(target=self.networker, args=(self.recvQ, self.sendQ))
        network.start()
 
        self.conns = {} #i was intending this for client side, not sure it makes sense

        self.whereis = {}

        self.primaries = primaries
        self.callsign = callsign
        self.m17_addr = m17.address.Address.encode(self.callsign)

        self.last = 0
        self.registration_keepalive_period = 25
        self.connection_timeout = 25

    def networker(self, recvq, sendq):
        """
        """
        while 1:
            try:
                data,conn = self.sock.recvfrom(1500)
                print("RECV",conn)
                recvq.put((data,conn))
            except BlockingIOError as e:
                pass
            if not sendq.empty():
                data,conn = sendq.get_nowait()
                print("SEND",conn)
                self.sock.sendto(data,conn)
            time.sleep(.0001)

    def loop(self):
        def looper(self):
            while 1:
                self.loop_once()
                time.sleep(.005)
        self.looper = threading.Thread(target=looper, args=(self,))
        self.looper.start()

    def clean_conns(self):
        ...
        # self.conns = {conn: data for conn, data in self.conns if time.time() - data.last > self.connection_timeout}

    def loop_once(self):
        self.registration_keepalive()
        if not self.recvQ.empty():
            data,conn = self.recvQ.get_nowait()
            print("Recv:", data,conn)
            if conn[0] not in self.conns:
                self.conns[ conn ] = dattr({
                    "last": time.time(),
                    "conn": conn,
                        })
                print(self.conns)
            else:
                self.conns[ conn[0] ].last = time.time()
            self.process_packet( data, conn )
        # self.clean_conns()
        # self.clean_whereis()

    def M17J_send(self, payload, conn):
        print("Sending to %s M17J %s"%(conn,payload))
        self.sendQ.put((b"M17J" + payload, conn))

    def process_packet(self, payload, conn):
        if payload.startswith(b"M17 "):
            ...
            #voice and data packets
        elif payload.startswith(b"M17J"): #M17 Json development and evaluation protocol - the standard is, there is no standard
            msg = dattr(json.loads(payload[4:].decode("utf-8")))
            print("registration",msg,conn)
            if msg.msgtype == "i am here": #remote host asks to tie their host and callsign together
                self.reg_store(msg.callsign, conn) #so we store it
            # elif msg.msgtype == "where is?": #getting a query for a stored callsign
                # lastseen,theirconn = self.reg_fetch( callsign )
                # self.answer_where_is( conn, callsign, theirconn)
            # elif msg.msgtype == "is at": #getting a reply to a query
                # print("Found %s at %s!"%(callsign, msg.host))
                # # self.store( callsign, packet.srchost)
                # ... #and now we continue with what we were trying to do, i s'pose
                # # request rendezvous? here isn't where I want it to happen, but lets prove the concept i guess
            elif msg.msgtype == "introduce me?": #got a request: please introduce me to host, i'm trying to talk to them on port...
                ...
                #make a packet each to introduce peer1 and peer2
                self.arrange_rendezvous(conn,msg)
            elif msg.msgtype == "introducing": #got an intro: I have an introduction for you, please contact ...
                #make packets to punch holes allowing other peer to contact us
                self.attempt_rendezvous(conn,msg)
            elif msg.msgtype == "hi!": #got an "oh hey" packet
                #ignore it, it's just there to poke a hole so we can receive datagrams through it
                print("Got a holepunch packet from %s!"%(str(conn)))
        else:
            print("payload unrecognized")
            print("payload = ",payload)
            import pdb; pdb.set_trace()


    #user registration handling starts here
    def registration_keepalive(self):
        """
        Periodically re-register
        """
        if not self.callsign:
            return
        sincelastrun = time.time() - self.last
        if sincelastrun > self.registration_keepalive_period:
            for primary in primaries:
                self.register_me_with( primary )
            self.last = time.time()

    def register_me_with(self, server):
        payload = json.dumps({"msgtype":"i am here", "callsign": self.callsign }).encode("utf-8")
        self.M17J_send(payload, server)

    def reg_store(self, callsign, conn):
        print("[M17 registration] %s -> %s"%(callsign, conn))
        self.whereis[ callsign ] = (time.time(), conn)
        self.whereis[ conn ] = (time.time(), callsign)

    def reg_fetch_by_callsign( self, callsign ):
        return self.whereis[callsign]
    def reg_fetch_by_conn( self, conn ):
        return self.whereis[conn]

    # def callsign_lookup( self, callsign):
        # for primary in self.primaries:
            # self.ask_where_is( callsign, primary )
    # def ask_where_is( self, callsign, server ):
        # addr = m17.address.Address.encode(callsign)
        # payload = json.dumps({"msgtype":"where is?", "m17_addr": addr }).encode("utf-8")
        # self.M17J_send(payload, server)
    # def answer_where_is( self, conn, callsign, loc ):
        # addr = m17.address.Address.encode(callsign)
        # payload = json.dumps({"msgtype":"is at", "m17_addr": addr, "host":loc[0] }).encode("utf-8")
        # self.rendezvous_send(payload, conn)

    #the rendezvous stuff starts here
    def request_rendezvous(self, callsign):
        payload = json.dumps({"msgtype":"introduce me?", "callsign": callsign }).encode("utf-8")
        for introducer in self.primaries:
            self.M17J_send(payload, introducer)
    
    def arrange_rendezvous(self, conn, msg):
        # requires peer1 and peer2 both be connected live to self (e.g. keepalives)
        #sent to opposing peer with other sides host and expected port
        _,callsign = self.reg_fetch_by_conn(conn)
        _,theirconn = self.reg_fetch_by_callsign(msg.callsign)
        payload = json.dumps({"msgtype":"introducing", "callsign": callsign, "host": conn[0], "port":conn[1] }).encode("utf-8")
        self.M17J_send(payload, theirconn) #this port needs to be from our existing list of connections appropriate to the _callsign_
        #we need to arrange the port too, don't we? 
        payload = json.dumps({"msgtype":"introducing", "callsign": msg.callsign, "host": theirconn[0], "port":theirconn[1] }).encode("utf-8")
        self.M17J_send(payload, conn) #this one we can reply to directly, of course

    def attempt_rendezvous(self, conn, msg):
        payload = json.dumps({"msgtype":"hi!", "callsign": msg.callsign}).encode("utf-8")
        self.M17J_send(payload, (msg.host,msg.port))


if __name__ == "__main__":
    primaries = [("m17.programradios.com.",17000)]
    callsign = sys.argv[1]
    if "-s" in sys.argv[2:]:
        portnum = 17000
    else:
        portnum = (m17.address.Address.encode(callsign) % 32767) + 32767
    print(portnum)
    x = m17_networking(primaries, callsign=callsign, port=portnum )
    x.loop()
    import pdb; pdb.set_trace()
    #on selection of reflector or remote user:
    # x.callsign_lookup("M17REF A") #returns where to find that noun
    # x.callsign_lookup("W2FBI A")
    # x.callsign_lookup("W2FBI")
    # x.callsign_connect("W2FBI") #this is how you do an automatic udp hole punch. 
    # #Registers the connection and maintains keepalives with that host. They should do the same.
    # x.check_link("W2FBI") #check we are connected
    # x.check_link("17.12.15.13") #check 
    # x.callsign_disco("W2FBI") #this is how you stop the keepalives and kill that connection

    #get results ... how?

