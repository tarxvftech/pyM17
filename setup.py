#!/usr/bin/env python
import setuptools
from setuptools import setup
from os import path

#for reference: https://github.com/navdeep-G/setup.py/blob/master/setup.py
#
NAME = 'm17'
DESCRIPTION = 'M17 radio (and radio-over-IP) protocol implementation. https://github.com/M17-project/'
URL = 'https://git.mmcginty.me/mike/pym17'
EMAIL = 'pyM17@tarxvf.tech'
AUTHOR = 'tarxvf'
REQUIRES_PYTHON = '>=3.5.0'
VERSION = '0.0.10'

REQUIRED=[
        "bitstruct",
        "wheel"
        ]

this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()



#look into sourcing VERSION from git tag
#what's this __version__ thing I'm seeing?
setuptools.setup(
    name=NAME,
    version=VERSION,
    description=DESCRIPTION,
    long_description=long_description,
    long_description_content_type='text/markdown',
    author=AUTHOR,
    author_email=EMAIL,
    python_requires=REQUIRES_PYTHON,
    url=URL,
    install_requires=REQUIRED,
    packages=setuptools.find_packages(),
    include_package_data=True,
    extras_require={
        "Codec2":[
            "Cython",
            "numpy",
            "soundcard",
            "samplerate",
            "pycodec2"
            ]
        },
    classifiers=[
        # Trove classifiers
        # Full list: https://pypi.python.org/pypi?%3Aaction=list_classifiers
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ]
    )

