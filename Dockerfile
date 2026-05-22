# syntax=docker/dockerfile:1
# A+ Programming Language — Docker image

FROM ubuntu:18.04 AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ make xorg-dev ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

ADD https://github.com/louyx/aplus/archive/refs/heads/master.tar.gz /tmp/aplus.tar.gz
RUN tar xzf /tmp/aplus.tar.gz --strip-components=1 && rm /tmp/aplus.tar.gz

# ── Pre-configure source patches for modern systems ──

# 1. Replace sys_errlist[] with strerror() everywhere
RUN find . -type f \( -name '*.c' -o -name '*.C' -o -name '*.h' -o -name '*.H' \) \
      -exec sed -i 's/sys_errlist\[\([^]]*\)\]/strerror(\1)/g' {} \;

# 2. Remove extern sys_nerr declarations
RUN find . -type f \( -name '*.c' -o -name '*.C' -o -name '*.h' -o -name '*.H' \) \
      -exec sed -i '/extern int sys_nerr;/d' {} \;

# 3. Replace sys_nerr usage
RUN find . -type f \( -name '*.c' -o -name '*.C' \) \
      -exec sed -i 's/sys_nerr/9999/g' {} \;

# 4. Forward-declare struct sigvec in files that need it
RUN for f in src/dap/sgnl.h src/dap/sgnlcatch.c src/dap/sgnldefault.c \
             src/dap/sgnlignore.c src/dap/sgnloriginal.c; do \
      [ -f "$f" ] && sed -i '1i struct sigvec { void (*sv_handler)(int); int sv_mask; int sv_flags; };' "$f"; \
    done

# 5. Define SV_INTERRUPT in files that use it
RUN for f in src/dap/sgnlcatch.c src/dap/sgnldefault.c \
             src/dap/sgnlignore.c src/dap/sgnloriginal.c; do \
      [ -f "$f" ] && sed -i '2i #define SV_INTERRUPT 0' "$f"; \
    done

# Build
RUN ./configure --prefix=/opt/aplus \
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
