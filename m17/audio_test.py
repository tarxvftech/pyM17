import sys
import time
import numpy
import pycodec2

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
        while 1:
            audio = mic.record(numframes=conrate) #.transpose()
            audio = audio.flatten()
            audio = audio * 32767
            audio = audio.astype("<h") 
            c2_bits = c2.encode( audio )
            audio = c2.decode( c2_bits )
            audio = audio.astype("float")
            audio = audio / 32767
            sp.play(audio)

if __name__ == "__main__":
    audio_test_soundcard(int(sys.argv[1]))
