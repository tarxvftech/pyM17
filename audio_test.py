
import time
import numpy
import pycodec2
import pysoundcard


def audio_test(mode):
    mode = int(mode)
    c2 = pycodec2.Codec2( mode )
    conrate = c2.samples_per_frame()
    bitframe = c2.bits_per_frame()

    pa_rate = 8000
    sampwidth = 2
    pa_channels = 1
    print(conrate)

    def callback(in_data, out_data, time_info, status):
        # out_data[:] = in_data
        c2_bits = c2.encode( in_data.flatten() )
        out_data[:] = c2.decode( c2_bits ).reshape( (len(in_data),1) )
        return pysoundcard.continue_flag

    s = pysoundcard.Stream(channels=1, dtype=numpy.int16, samplerate=pa_rate, blocksize=conrate, callback=callback)

    now = time.time()
    s.start()
    while 1:
        time.sleep(.017)
    s.stop()

audio_test(3200)
