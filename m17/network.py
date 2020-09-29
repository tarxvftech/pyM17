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


class m17_networking_dht(m17_networking_direct):
    """
    real p2p for callsign lookup and introductions
    visualization tool for reading logs and a config to see packets and streams
        going back and forth between nodes, slowed down

    bayeux style multicast for heavily linked reflectors?
    DHT multicast for reflectors in general
    So unicast comes into reflector, who then broadcasts it back out...
    borg https://engineering.purdue.edu/~ychu/publications/borg.pdf
    bayeux https://apps.dtic.mil/sti/pdfs/ADA603200.pdf
    https://inst.eecs.berkeley.edu//~cs268/sp03/notes/Lecture22.pdf
    http://www0.cs.ucl.ac.uk/staff/B.Karp/opendht-sigcomm2005.pdf
    https://sites.cs.ucsb.edu/~ravenben/talks/apis-1-03.pdf
    https://www.cs.cornell.edu/home/rvr/papers/willow.pdf
    http://p2p.cs.ucsb.edu/chimera/html/overview.html
    https://sites.cs.ucsb.edu/~ravenben/publications/pdf/tapestry_jsac.pdf
    http://p2p.cs.ucsb.edu/chimera/html/papers.html
    http://rowstron.azurewebsites.net/
    https://www2.eecs.berkeley.edu/Pubs/TechRpts/2001/CSD-01-1141.pdf
    http://p2p.cs.ucsb.edu/chimera/html/home.html
    http://p2p.cs.ucsb.edu/cashmere/
    http://p2p.cs.ucsb.edu/chimera/html/overview.html
    https://github.com/topics/distributed-hash-table?o=asc&s=stars
    https://github.com/bmuller/kademlia
    https://github.com/DivyanshuSaxena/Distributed-Hash-Tables
    """
    pass

class m17_networking_direct:
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
                print("RECV",conn, data)
                recvq.put((data,conn))
            except BlockingIOError as e:
                pass
            if not sendq.empty():
                data,conn = sendq.get_nowait()
                print("SEND",conn, data)
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
        # print("Sending to %s M17J %s"%(conn,payload))
        self.sendQ.put((b"M17J" + payload, conn))

    def process_packet(self, payload, conn):
        if payload.startswith(b"M17 "):
            ...
            #voice and data packets
        elif payload.startswith(b"M17J"): #M17 Json development and evaluation protocol - the standard is, there is no standard
            msg = dattr(json.loads(payload[4:].decode("utf-8")))
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
                print("Got a holepunch packet from %s!"%(str(conn)))
                self.reg_store(msg.callsign, conn) #so we store it
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
        try:
            _,requestor_callsign = self.reg_fetch_by_conn(conn)
            target_callsign = msg.callsign
            _,theirconn = self.reg_fetch_by_callsign(msg.callsign)
        except KeyError as e:
            logging.error("Missing a registration, didn't find %s"%(e))
            return
        payload = json.dumps({"msgtype":"introducing", "callsign": requestor_callsign, "host": conn[0], "port":conn[1] }).encode("utf-8")
        self.M17J_send(payload, theirconn) #this port needs to be from our existing list of connections appropriate to the _callsign_
        #we need to arrange the port too, don't we? 
        payload = json.dumps({"msgtype":"introducing", "callsign": target_callsign, "host": theirconn[0], "port":theirconn[1] }).encode("utf-8")
        self.M17J_send(payload, conn) #this one we can reply to directly, of course

    def attempt_rendezvous(self, conn, msg):
        payload = json.dumps({"msgtype":"hi!", "callsign": self.callsign}).encode("utf-8")
        self.M17J_send(payload, (msg.host,msg.port))

    def have_link(self, callsign):
        try:
            last,conn = self.reg_fetch_by_callsign(callsign)
            return time.time() - last #<30
        except KeyError as e:
            return False

    def callsign_connect(self, callsign):
        self.request_rendezvous(callsign)

    def callsign_wait_connect(self, callsign):
        self.callsign_connect(callsign)
        start = time.time()
        while not self.have_link(callsign):
            time.sleep(.003)
            if time.time() - start > 3:
                return False
        #TODO now start the auto-keepalives here
        return True

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

    # x.callsign_connect("W2FBI") #this is how you do an automatic udp hole punch. 
    # #Registers the connection and maintains keepalives with that host. They should do the same.
    # x.have_link("W2FBI") #check if we are connected.
    # x.callsign_disco("W2FBI") #this is how you stop the keepalives and kill that connection (not implemented yet)
    # callsign_disco implies have_link will return False

    #hosts behind the same nat can expect failure when doing a direct call to each other, not exactly sure why - seems to be related to hairpin NATing


#spin this up on a public host for a demo like 
#`python3 -m m17.network CALLSIGN -s`
# (and put the address of the public server in primaries like m17.programradios.com, above) 

# demo clients should each `python3 -m m17.network UNIQUE_CALLSIGN` 
# and then one can type x.connect_callsign(
