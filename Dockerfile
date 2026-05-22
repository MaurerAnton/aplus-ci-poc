# syntax=docker/dockerfile:1
# A+ Programming Language — Docker image
# Builds on ubuntu:18.04 to avoid glibc/GCC compatibility issues

FROM ubuntu:18.04 AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ make xorg-dev ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

ADD https://github.com/louyx/aplus/archive/refs/heads/master.tar.gz /tmp/aplus.tar.gz
RUN tar xzf /tmp/aplus.tar.gz --strip-components=1 && rm /tmp/aplus.tar.gz

# Create compat header + inject into source files that need it
RUN printf '#include <string.h>\n#include <signal.h>\n' \
         'struct sigvec { void (*sv_handler)(int); int sv_mask; int sv_flags; };\n' \
         '#define SV_INTERRUPT SA_INTERRUPT\n' > compat.h \
    && for f in src/dap/sgnl.h src/dap/sgnlcatch.c src/dap/sgnldefault.c \
                src/dap/sgnlignore.c src/dap/sgnloriginal.c; do \
         sed -i '1i#include "compat.h"' "$f"; \
       done

# Fix sys_errlist references (removed in glibc 2.32+)
RUN find . -type f \( -name '*.c' -o -name '*.C' -o -name '*.h' -o -name '*.H' \) \
      -exec sed -i 's/sys_errlist\[\([^]]*\)\]/strerror(\1)/g' {} \; \
    && find . -type f \( -name '*.c' -o -name '*.C' -o -name '*.h' -o -name '*.H' \) \
      -exec sed -i '/extern int sys_nerr;/d' {} \; \
    && find . -type f \( -name '*.c' -o -name '*.C' \) \
      -exec sed -i 's/sys_nerr/9999/g' {} \;

# Build with permissive C++ flags for 2008-era code
RUN CFLAGS="-I/build -include /build/compat.h" \
    CXXFLAGS="-std=gnu++98 -fpermissive" \
    ./configure --prefix=/opt/aplus \
    && make -j"$(nproc)" \
    && make install

FROM ubuntu:18.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    libx11-6 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/aplus /opt/aplus

ENV PATH="/opt/aplus/bin:${PATH}"
ENV APLUS_HOME="/opt/aplus"

WORKDIR /workspace

ENTRYPOINT ["/opt/aplus/bin/a+"]
CMD ["--help"]
