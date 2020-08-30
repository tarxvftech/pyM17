

def run_framer():
    x = M17_Framer(
            dst=Address(callsign="WM4CH"),
            src=Address(callsign="W2FBI"), 
            ftype=5, #standard voice stream, 3200bps codec2
            nonce=example_bytes(16)
            )
    b = x.makeLICH()
    x2 = M17_Framer.fromLICH( b )
    assert b == x2.makeLICH()
    packets =[ x.makeLICH() ]
    # packets = []
    payload = b"\x00" * 1500
    payload = example_bytes(1500)
    packets += x.payload_stream(payload)
    # for p in packets:
        # print(binascii.hexlify(bytes(p)))
    packets_bytes = [ bytes(p) for p in packets ]

    #hand it a subset of packets and make sure it can recover the full bytes of it
    #even when they are in order, but wrapped around (e.g. 34512 instead of 12345)
    recoveredLICH = initialLICH.recover_bytes_from_bytes_frames( packets_bytes[3:3+5] )
    assert recoveredLICH == bytes(x.makeLICH())
    #TODO make it more robust, see recover_bytes_from_bytes_frames notes

    recovered_payload = b"".join( regularFrame.dict_from_bytes(p)["payload"] for p in packets_bytes if not is_LICH(p) )
    # print(binascii.hexlify(recovered_payload, " ", -4))
    # print(binascii.hexlify(payload, " ", -4))
    assert recovered_payload.rstrip(b"\x00") == payload.strip(b"\x00")
    # initialLICH.from_regularFrames( 

def stdin_parser():
    #how to parse from a stream of raw bytes, let's say if I missed the LICH and the first packet?
    #can i lock onto the LICH chunks?
    #dropped packets should solve the M17/IP issue
    #but can i detect a dropped byte in a stream of bytes from the repeating LICH?
    ...

# audio_test(3200)
