#!/usr/bin/env python

from setuptools import setup, Command

NAME = 'm17'
DESCRIPTION = 'M17 radio (and radio-over-IP) protocol implementation'
URL = 'https://git.mmcginty.me/mike/m17_misc_utils'
EMAIL = 'm17.py@tarxvf.tech'
AUTHOR = 'tarxvf'
REQUIRES_PYTHON = '>=3.8.0'
VERSION = '0.0.1'

with open("requirements.txt","r") as fd:
    REQUIRED = list(map(lambda x:x.strip(), fd.readlines()))

