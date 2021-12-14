
helptext="""
`python -m m17` doesn't do anything on it's own (yet).
Examples:

Does not require Codec2:
    python -m m17.address W2FBI

    python -m m17.reflector M17-XXX
    (all modules are bridged (modules not implemented yet))

    #python -m m17.apps stream_saver M17-XXX

With `pip install m17[Codec2]`
    python -m m17.audio_test 3200

    Uses VOX - you can use your microphone mute as an inverse ptt
    python -m m17.client YOURCALL A M17-M17 A
"""
def main():
    print(helptext)


if __name__ == "__main__":
    main()
