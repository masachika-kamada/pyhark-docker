FROM ubuntu:22.04

ENV TZ=Asia/Tokyo
ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY host.docker.internal:0.0
COPY hark-archive-keyring.asc /usr/share/keyrings/

RUN apt-get update && \
    apt-get install -y \
        tzdata \
        fish && \
    rm -rf /var/lib/apt/lists/*

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN apt-get update && \
    apt-get install -y \
        curl \
        wget \
        lsb-release \
        less \
        gnupg && \
    apt-key add /usr/share/keyrings/hark-archive-keyring.asc && \
    bash -c 'echo -e "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hark-archive-keyring.asc] http://archive.hark.jp/harkrepos $(lsb_release -cs) non-free\ndeb-src [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hark-archive-keyring.asc] http://archive.hark.jp/harkrepos $(lsb_release -cs) non-free" > /etc/apt/sources.list.d/hark.list'

RUN apt-get update && \
    apt-get install -y \
        libhark-lib \
        python3-hark-lib \
        python3-pip && \
    pip install https://github.com/kivy-garden/graph/archive/master.zip && \
    ln -s /usr/bin/python3 /usr/bin/python

CMD ["fish"]
