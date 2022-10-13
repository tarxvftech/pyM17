#!/usr/bin/env python
import sys

from .apps import player


def printhelp():
    print("""
Provide a set of files to play. Does its level best but no guarantees.
Supports the follow types of files:
    .m17s - M17 Stream files as created by pyM17
        NB: only supports 3200bps codec2 right now.
        ^c to end playing that file and skip to next (yes, really, sorry)

Future:
    packet captures?
""")
if __name__ == "__main__":
    print(sys.argv[1:])
    if len(sys.argv) < 2:
        printhelp()
        sys.exit(1)
    else:
        for file in sys.argv[1:]:
            player(file)
