import os
import sys
import random
import binascii

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

def c_array_init_file(filename):
    with open(filename,"rb") as fd:
        c_array_init(fd.read())

def c_array_init(bs:bytes):
    print("uint8_t sample_stream[]={")
    line = ""
    cnt = 0
    tcount = 0
    for b in bs:
        line += hex(b) 
        line +=","
        cnt += 1
        tcnt += 1
        if cnt == 4:
            line+="\t"
        if cnt >= 8:
            print(line)
            line = ""
            cnt = 0
            continue
    print("}")
    #cat filename |grep -o 'x' |wc -l to know how big it is

if __name__ == "__main__":
    vars()[sys.argv[1]](sys.argv[2:])
