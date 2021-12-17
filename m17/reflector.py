#!/usr/bin/env python
import sys

from .apps import reflector

if __name__ == "__main__":
    print(sys.argv)
    reflector(*sys.argv[1:])
