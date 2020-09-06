from archlinux
RUN pacman --noconfirm -Syyu base-devel 
RUN pacman --noconfirm -S codec2 python python-pip python-setuptools
RUN pip install --upgrade pip numpy Cython wheel setuptools
