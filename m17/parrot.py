#!/usr/bin/env python
import sys

from .apps import parrot

if __name__ == "__main__":
    print(sys.argv)
    parrot(*sys.argv[1:])
