# Python package for M17 radio and radio-over-IP protocols

M17 is a new, experimental radio protocol similar to DMR/MotoTRBO, P25, D-STAR, and others.
It uses the Codec2 vocoder by David Rowe. 

See [M17 Project](https://m17project.org/) for more details.

This code will be pushed up to [the M17 project's newly created Github](https://github.com/m17-project) eventually.
As for now, it's all by yours truly.

[![Build Status](https://drone.mmcginty.me/api/badges/mike/pyM17/status.svg?ref=refs/heads/master)](https://drone.mmcginty.me/mike/pyM17)


This package has full Python support for handling M17 addresses, framing and parsing,
and including a full Python native VoIP client (for developers). 

## Features

### Base
* `python -m m17.address <callsign>` - print the encoded M17 base40 representation of the callsigns given
* see `frames.py` and `framer.py` in the source for M17 frame classes and example usage.

### [Codec2]
* `python -m m17.audio_test 3200` where 3200 can also be 1600, 1200, or other supported Codec2 bitrate. Takes your microphone, encodes and decodes it into Codec2, and plays it back. Useful for getting your microphone input tuned properly for Codec2.

## Installation

### Pip

You can install with `pip install m17`, and get a basic feature set
including framing and M17 address translation.

However, to get all features that use `Codec2`, including the full M17 VoIP node
and `audio_test`, you must first have `Codec2` installed on
your system, including the `Codec2` development headers, and `Cython`. Once that's
complete, you can then `pip install m17[Codec2]` to install all features.

Note that installing `Cython` separately before `pycodec2` seems to be
required in order to make sure it's available for `pycodec2`'s setup
process.

Here's an example for Arch Linux.
```
pacman -Syu base-devel codec2 python python-pip python-setuptools
pip install --upgrade pip numpy Cython wheel setuptools
pip install m17[Codec2]
```
Naturally you need the typical compilation tools, which on Arch are `base-devel`.

On systems that separate development headers, you need those too for
Codec2, i.e. both `codec2` and `codec2-dev`, or whatever the appropriate
names are for your distro.

On many Ubuntu and Debian systems, the codec2 packages in the distro
repositories is too out of date for use with pycodec2, so you may need
to follow the [upstream Codec2 instructions](https://github.com/drowe67/codec2)
and the [upstream pycodec2 instructions](https://github.com/gregorias/pycodec2)
to get a fully working installation of both. 

You may email me with clearly described problems regarding installation
and I will do my best to help.


TODO:
https://github.com/joerick/cibuildwheel

