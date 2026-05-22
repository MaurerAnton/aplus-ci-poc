# syntax=docker/dockerfile:1
# A+ Programming Language — Docker image
# Builds the Morgan Stanley A+ interpreter from source.

FROM ubuntu:20.04 AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ make xorg-dev ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

ADD https://github.com/louyx/aplus/archive/refs/heads/master.tar.gz /tmp/aplus.tar.gz
RUN tar xzf /tmp/aplus.tar.gz --strip-components=1 && rm /tmp/aplus.tar.gz

RUN CXXFLAGS="-std=gnu++98 -fpermissive -Wno-error" \
    ./configure --prefix=/opt/aplus \
    && make -j"$(nproc)" \
    && make install

FROM ubuntu:20.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    libx11-6 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/aplus /opt/aplus

ENV PATH="/opt/aplus/bin:${PATH}"
ENV APLUS_HOME="/opt/aplus"

WORKDIR /workspace

ENTRYPOINT ["/opt/aplus/bin/a+"]
CMD ["--help"]
