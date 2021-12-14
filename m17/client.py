#!/usr/bin/env python
import sys

from .apps import client

if __name__ == "__main__":
    print(sys.argv)
    client(*sys.argv[1:])
