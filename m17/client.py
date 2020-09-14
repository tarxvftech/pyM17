#!/usr/bin/env python
import sys

from .apps import voip

if __name__ == "__main__":
    voip(*sys.argv[1:])
