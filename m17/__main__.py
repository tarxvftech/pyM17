
helptext="""
`python -m m17` doesn't do anything on it's own (yet).
Examples:

Without `pip install m17[Codec2]`
    python -m m17.address W2FBI


With `pip install m17[Codec2]`
    python -m m17.audio_test 3200

    Use your microphone mute as a reverse push to talk with these:
    python -m m17.client m17tester.tarxvf.tech 17010 tx srccall dstcall
    python -m m17.client localhost 17000 rx
    python -m m17.client raspi.lan 17000 full srccall dstcall
"""
def main():
    print(helptext)


if __name__ == "__main__":
    main()
