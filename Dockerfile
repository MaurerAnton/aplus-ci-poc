# syntax=docker/dockerfile:1
# A+ Programming Language — Docker image

FROM ubuntu:18.04 AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ make xorg-dev ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

ADD https://github.com/louyx/aplus/archive/refs/heads/master.tar.gz /tmp/aplus.tar.gz
RUN tar xzf /tmp/aplus.tar.gz --strip-components=1 && rm /tmp/aplus.tar.gz

# ── Pre-configure source patches ──

# 1. sys_errlist[X] -> strerror(X)
RUN find . -type f \( -name '*.c' -o -name '*.C' -o -name '*.h' -o -name '*.H' \) \
      -exec sed -i 's/sys_errlist\[\([^]]*\)\]/strerror(\1)/g' {} \;

# 2. Remove extern sys_nerr declarations
RUN find . -type f \( -name '*.c' -o -name '*.C' -o -name '*.h' -o -name '*.H' \) \
      -exec sed -i '/extern int sys_nerr;/d' {} \;

# 3. Replace sys_nerr usage
RUN find . -type f \( -name '*.c' -o -name '*.C' \) \
      -exec sed -i 's/sys_nerr/9999/g' {} \;

# 4. Add struct sigvec + SV_INTERRUPT fallback for sgnl.h
RUN for f in src/dap/sgnl.h; do \
      [ -f "$f" ] && ( \
        echo '#ifndef _STRUCT_SIGVEC_DEFINED'; \
        echo '#define _STRUCT_SIGVEC_DEFINED'; \
        echo 'struct sigvec { void (*sv_handler)(int); int sv_mask; int sv_flags; };'; \
        echo '#endif'; \
        echo '#ifndef SV_INTERRUPT'; \
        echo '#define SV_INTERRUPT 0'; \
        echo '#endif'; \
        cat "$f" \
      ) > "${f}.tmp" && mv "${f}.tmp" "$f"; \
    done

RUN CFLAGS="-D_GNU_SOURCE -DHAVE_SIGACTION=1" \
    CXXFLAGS="-std=gnu++98" \
    LIBS="-lX11 -lXext" \
    ./configure --prefix=/opt/aplus \
    && sed -i 's/#undef HAVE_SIGACTION/#define HAVE_SIGACTION 1/' config.h \
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
