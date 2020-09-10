
helptext="""
`python -m m17` doesn't do anything on it's own (yet).
Examples:

Without `pip install m17[Codec2]`
    python -m m17.address W2FBI


With `pip install m17[Codec2]`
    python -m m17.audio_test 3200
    python -m m17.client 
"""
def main():
    print(helptext)


if __name__ == "__main__":
    main()
