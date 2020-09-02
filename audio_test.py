import sys
import time
import numpy
import pycodec2
import pysoundcard
import soundcard
import matplotlib
import matplotlib.pyplot as plt


def audio_test_pysoundcard(mode):
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

def audio_test_soundcard(mode):
    import soundcard as sc

    mode = int(mode)
    c2 = pycodec2.Codec2( mode )
    conrate = c2.samples_per_frame()
    bitframe = c2.bits_per_frame()
    pa_rate = 8000

    default_mic = sc.default_microphone()
    default_speaker = sc.default_speaker()
    print(default_mic, default_speaker)
    sc_config= {
            "samplerate": pa_rate,
            "blocksize": conrate
            }
    with default_mic.recorder(**sc_config,channels=1) as mic,\
        default_speaker.player(**sc_config,channels=1) as sp:
        # fig, ax = plt.subplots()
        # ax.grid()
        # plt.ion()
        # plt.show()
        while 1:
            audio = mic.record(numframes=conrate) #.transpose()
            # audio = audio[1] + audio[0]
            audio = audio.flatten()
            # ax.plot(audio)
            audio = audio * 32767
            audio = audio.astype("<h") 
            c2_bits = c2.encode( audio )
            audio = c2.decode( c2_bits )
            audio = audio.astype("float")
            audio = audio / 32767
            # ax.plot(audio)
            # plt.show()
            sp.play(audio)
            # plt.pause(.001)
            # ax.clear()

vars()[sys.argv[1]](*sys.argv[2:])
