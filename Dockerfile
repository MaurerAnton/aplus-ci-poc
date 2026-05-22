# syntax=docker/dockerfile:1
# A+ Programming Language — Docker image
# Builds the Morgan Stanley A+ interpreter from source.
# See: https://github.com/louyx/aplus

FROM ubuntu:22.04 AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ make xorg-dev ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN git clone --depth 1 https://github.com/louyx/aplus.git .

RUN ./configure --prefix=/opt/aplus \
    && make -j"$(nproc)" \
    && make install

FROM ubuntu:22.04 AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libx11-6 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/aplus /opt/aplus
COPY --from=builder /build/src/a/fsftest.+ /opt/aplus/share/examples/

ENV PATH="/opt/aplus/bin:${PATH}"
ENV APLUS_HOME="/opt/aplus"

RUN echo '1+2' | timeout 5 /opt/aplus/bin/a+ || true

WORKDIR /workspace

ENTRYPOINT ["/opt/aplus/bin/a+"]
CMD ["--help"]
