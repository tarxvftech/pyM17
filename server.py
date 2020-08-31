import threading
import socketserver
import queue
from .const import *

class GatewayHandler(socketserver.StreamRequestHandler):
    """
    Don't look at me! I'm the product of late night, confused work :(
    """
    rbufsize = 0
    wbufsize = 0
    disable_nagle_algorithm = True
    qs = []
    qs_lock = threading.Lock()
    tgs = []
    def handle(self):
        #server itself as self.server
        #self.request is the request
        #self.client_address
        #self.rfile to read from
        #self.wfile to write to
        my_q = queue.Queue()
        other_qs = self.qs
        with self.qs_lock:
            self.qs.append( my_q )
        print(self.client_address, " opened")
        try:
            while 1:
                x = self.rfile.read(encoded_buf_size)
                if len(x) == 0:
                    raise(Exception("Empty read"))
                with self.qs_lock:
                    for q in self.qs:
                        # if q == my_q:
                            # continue
                        q.put( x )
                if not my_q.empty():
                    self.wfile.write(my_q.get())

        except Exception as e:
            print(self.client_address, e)
        finally:
            with self.qs_lock:
                self.qs.remove( my_q )
            print(self.client_address, "closed")

def GatewayServer(port=default_port):
    serveraddr = ("0.0.0.0",port)

    server = socketserver.ThreadingTCPServer( serveraddr, GatewayHandler)
    server.allow_reuse_address = True
    with server:
        server.serve_forever()

if __name__ == "__main__":
    GatewayServer()
