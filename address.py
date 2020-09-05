import sys
import string
callsign_alphabet = "\x00" + string.ascii_uppercase + string.digits + "-/." 
#"." is TBD
# print("Alphabet: %s"%(callsign_alphabet))
# print("len(Alphabet): %d"%(len(callsign_alphabet)))


class Address:
    def __init__(self, **kwargs):
        for k,v in kwargs.items():
            if k in ["addr","callsign"]:
                setattr(self,k,v)
        self.callsign = self.callsign.upper() if hasattr(self,"callsign") else self.decode(self.addr)
        self.addr = self.addr if hasattr(self,"addr") else self.encode(self.callsign)
    def __str__(self):
        return "%s == 0x%06x"%(self.callsign,self.addr)
    def __index__(self):
        return self.addr
    def __eq__(self, compareto):
        if type(compareto) == type(""):
            if compareto.isdigit(): #yeah, gross.
                return int(compareto) == self.addr
            else: 
                return compareto.upper() == self.callsign
        elif type(compareto) == type(1):
            return compareto == self.addr
        elif type(compareto) == type(self):
            return int(self) == int(compareto)
        else:
            return False

    @staticmethod
    def to_dmr_id(something):
        # if no db:
        # url = "https://database.radioid.net/static/users.json"
        # requests.get()
        #if db but not found, _check once_ using https://database.radioid.net/api/dmr/user/?id=3125404
        #return an Address encoded for DMR using database lookup?
        #or jsut the ID as an int?
        ...
    @staticmethod
    def from_dmr_id(dmr_int):
        #return an Address encoded for callsign using dmr database lookup to get callsign
        ...
    def is_dmr_id(self):
        return self.callsign.startswith("D") and self.callsign[1:].isdigit()
    def is_dmr_talkgroup(self):
        return any(
                self.is_brandmeister_tg()
                )
    def is_brandmeister_tg(self):
        return self.callsign.startswith("BM") and self.callsign[1:].isdigit()
    def is_dstar_reflector(self):
        return self.callsign.startswith("REF")

    @staticmethod
    def encode(callsign):
        num = 0
        for char in callsign.upper()[::-1]:
            charidx = callsign_alphabet.index(char)
            num *= 40
            num += charidx
        return num
    
    @staticmethod
    def decode(addr):
        num = addr
        if num >= 40**9:
            raise(Exception("Not a callsign"))
        chars = []
        while num > 0:
            idx = int(num%40)
            c =  callsign_alphabet[idx] 
            chars.append(c)
            # print(num,idx,c)
            num //= 40
        callsign = "".join(chars)
        return callsign


def show_help():
    print("""
Provide callsigns on the command line and they will be translated into M17 addresses
    """)
if __name__ == "__main__":
    if len(sys.argv) <= 1:
        show_help()
    else:
        for each in sys.argv[1:]:
            print(Address(callsign=each))
