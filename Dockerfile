# syntax=docker/dockerfile:1
# A+ Programming Language — Docker image

FROM ubuntu:18.04 AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ make xorg-dev libx11-dev ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

ADD https://github.com/louyx/aplus/archive/refs/heads/master.tar.gz /tmp/aplus.tar.gz
RUN tar xzf /tmp/aplus.tar.gz --strip-components=1 && rm /tmp/aplus.tar.gz

# Compat header: struct sigvec removed from modern glibc
# Define standalone (no #include <signal.h> to avoid conflicts)
RUN printf 'struct sigvec { void (*sv_handler)(int); int sv_mask; int sv_flags; };\n' \
         '#define SV_INTERRUPT 0\n' > /compat.h

RUN CFLAGS="-include /compat.h -DSV_INTERRUPT=0" \
    CXXFLAGS="-std=gnu++98" \
    LDFLAGS="-lX11" \
    ./configure --prefix=/opt/aplus \
    && make -j"$(nproc)" \
    && make install

FROM ubuntu:18.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    libx11-6 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/aplus /opt/aplus

ENV PATH="/opt/aplus/bin:${PATH}"

WORKDIR /workspace
ENTRYPOINT ["/opt/aplus/bin/a+"]
CMD ["--help"]
