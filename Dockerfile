# syntax=docker/dockerfile:1
# A+ Programming Language — Docker image
# Builds the Morgan Stanley A+ interpreter from source.

FROM ubuntu:22.04 AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ make xorg-dev ca-certificates wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Download A+ 4.22-1 source tarball
ADD https://github.com/louyx/aplus/archive/refs/heads/master.tar.gz /tmp/aplus.tar.gz
RUN tar xzf /tmp/aplus.tar.gz --strip-components=1 && rm /tmp/aplus.tar.gz

# Patch for modern glibc: sys_errlist + struct sigvec removed
RUN sed -i '/extern int sys_nerr;/d' src/dap/error.c \
    && sed -i 's#if (errnum < 1 || errnum > sys_nerr)#if (0)#g' src/dap/error.c \
    && sed -i 's#sys_errlist\[errnum\]#strerror(errnum)#g' src/dap/error.c \
    && find . -type f \( -name '*.c' -o -name '*.C' \) \
      -exec sed -i 's#(errno<sys_nerr)?sys_errlist\[errno\]:"unknown error"#strerror(errno)#g' {} \; \
    && find . -type f \( -name '*.c' -o -name '*.C' \) \
      -exec sed -i 's#sys_errlist\[errno\]#strerror(errno)#g' {} \; \ \
    && printf '#include <string.h>\n#include <signal.h>\nstruct sigvec { void (*sv_handler)(int); int sv_mask; int sv_flags; };\n#define SV_INTERRUPT SA_INTERRUPT\n' > /build/compat.h

RUN CFLAGS="-Wno-error -include /build/compat.h" \
    CXXFLAGS="-std=gnu++98 -Wno-error -fpermissive" \
    ./configure --prefix=/opt/aplus \
    && make -j"$(nproc)" \
    && make install

FROM ubuntu:22.04 AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libx11-6 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/aplus /opt/aplus

ENV PATH="/opt/aplus/bin:${PATH}"
ENV APLUS_HOME="/opt/aplus"

WORKDIR /workspace

ENTRYPOINT ["/opt/aplus/bin/a+"]
CMD ["--help"]
