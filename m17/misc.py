import os
import sys
import random
import binascii
import unittest

def __b(size):
    def binary_print(num):
        return " ".join(map(
            lambda c: c.zfill(size),  #make sure each chunk is padded with zeros to size
            chunk(format(num, 'b'),-1*size) #chunk into size chunks, starting from the right
            ))
    return binary_print

_b4 = __b(4)
_b8 = __b(8)
_b16 = __b(16)
_b = _b8
_x = lambda b: binascii.hexlify(b, " ", -4)

def example_bytes(length):
    return bytearray(random.getrandbits(8) for _ in range(length))

def demonstrate_chunk():
    ab = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    print(chunk(ab, 5))
    print(chunk(ab, -5))

def chunk(b:bytes, size:int):
    """
    if size is positive, chunks starting left to right
    if size is negative, chunk from the right instead
    chunk size is abs(size)
    chunk size of 0 is an error
    returns a list of chunks of that size
    """
    fromright = size < 0
    size=abs(size)
    if fromright:
        return [ b[::-1][i:i+size][::-1] for i in range(0, len(b), size)][::-1]
        #I'm not sorry
        #okay, maybe a little bit.
    else:
        return [ b[i:i+size] for i in range(0, len(b), size)]

def test_b(x):
    print(_b4(int(x)))
    print(_b(int(x)))
    print(_b8(int(x)))
    print(_b16(int(x)))

class dattr(dict):
    """
    "dict-attr", used for when you don't want to type [""] all the time
    (and i think it looks nicer for things like config settings)
    """
    def __getattr__(self,name):
        """
        With a dattr, you can do this:
        >>> x = dattr({"abc":True})
        >>> x.abc
        True

        """
        if type(self[name]) == type({}): 
            #make sure we wrap any nested dicts when we encounter them
            self[name] = dattr(self[name]) #has to assign to save any changes to nested dattrs
            #e.g.  x.abc.fed = "in" 
        #otherwise just make our key,value pairs accessible through . (e.g. x.name)
        return self[name]
    def __setattr__(self,name,value):
        """
        With a dattr, you can do this:

        >>> x = dattr({"abc":True})
        >>> x.abc = False
        >>> x.abc
        False
        """
        self[name] = value


class test_nested_dattr(unittest.TestCase):
    def test_get(self):
        x = dattr({"abc":{
            "fed":"out"
            }})
        self.assertEqual(x.abc.fed, "out")

    def test_set(self):
        x = dattr({"abc":{
            "fed":"out"
            }})
        x.abc.fed = "in"
        self.assertEqual(x.abc.fed, "in")

def c_array_init_file(filename):
    with open(filename,"rb") as fd:
        c_array_init(fd.read())

def c_array_init(bs:bytes):
    print("uint8_t sample_stream[]={")
    line = ""
    cnt = 0
    for b in bs:
        line += hex(b) 
        line +=","
        cnt += 1
        if cnt == 4:
            line+="\t"
        if cnt >= 8:
            print(line)
            line = ""
            cnt = 0
            continue
    print("}")
    #cat filename |grep -o 'x' |wc -l to know how big it is

def parse_utf_style_int(fourbytes):
    #https://helloacm.com/how-to-validate-utf-8-encoding-the-simple-utf-8-validation-algorithm/
    #https://github.com/JuliaStrings/utf8proc/blob/master/utf8proc.c#L125
    #stolen from utf8proc, which is under MIT
    #https://github.com/JuliaStrings/utf8proc/blob/master/LICENSE.md
    # cont = ((b) & 0xc0) == 0x80)
    if isinstance(fourbytes, (bytes,list)):
        b = fourbytes[:4] 
    else:
        b = bytes([fourbytes])
    if b[0] < 0x80: 
        #< 0b1000_0000
        return (1,b[0])

    elif b[0] < 0xe0:
        #< 0b1110_0000
        #0b110
        return (2, ((b[0] & 0x1f)<<6) |  (b[1] & 0x3f))

    elif b[0] < 0xf0:
        #< 0b1111_0000
        return (3, ((b[0] & 0xf)<<12) | ((b[1] & 0x3f)<<6)  |  (b[2] & 0x3f))

    else:
        return (4, ((b[0] & 0x7)<<18) | ((b[1] & 0x3f)<<12) | ((b[2] & 0x3f)<<6) | (b[3] & 0x3f))

def encode_utf_style_int(length_in_bytes):
    #stolen from utf8proc, which is under MIT
    #https://github.com/JuliaStrings/utf8proc/blob/master/LICENSE.md
    n = length_in_bytes
    if n < 0:
        return bytes([0])
    elif n < 0x80:
        return bytes([n])
    elif n < 0x800:
        b = []
        b.append(0xc0 + (n >> 6))
        b.append(0x80 + (n & 0x3f))
        return bytes(b)
    elif n < 0x10000:
        b = []
        b.append(0xe0 + (n >> 12))
        b.append(0x80 + ((n>>6) & 0x3f))
        b.append(0x80 + (n & 0x3f))
        return bytes(b)
    elif n < 0x110000:
        b = []
        b.append(0xf0 + (n >> 18))
        b.append(0x80 + ((n >> 12) & 0x3f))
        b.append(0x80 + ((n >> 6) & 0x3f))
        b.append(0x80 + (n & 0x3f))
        return bytes(b)
    else:
        raise(Exception("Can't store value %d, won't fit"%(n)))

"""
for i in range(0,1114111, 1):
    x = encode_utf_style_int(i)
    # print(i,x)
    blen,val = parse_utf_style_int(x)
    assert val == i
"""

if __name__ == "__main__":
    vars()[sys.argv[1]](*sys.argv[2:])
