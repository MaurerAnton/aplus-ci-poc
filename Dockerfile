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

# 5. CRITICAL: sgnl*.c check #if defined(HAVE_SVR4), sgnl.h uses HAVE_SIGACTION.
#    Neither is defined on Linux. Force both to use sigaction.
RUN for f in src/dap/sgnl.h; do \
      (echo '#define HAVE_SIGACTION 1'; echo '#define HAVE_SVR4 1'; cat "$f") \
        > "${f}.tmp" && mv "${f}.tmp" "$f"; \
    done
RUN for f in src/dap/sgnlcatch.c src/dap/sgnldefault.c \
             src/dap/sgnlignore.c src/dap/sgnloriginal.c; do \
      [ -f "$f" ] && sed -i 's/defined(HAVE_SVR4)/1/g' "$f"; \
    done

# 6. Append sigvec() fallback (kept for any remaining references)
RUN cat >> src/dap/error.c << 'SIGVECEOF'

/* Provide sigvec() for linking on systems where libc lacks it */
#include <signal.h>
#ifndef _STRUCT_SIGVEC_DEFINED
#define _STRUCT_SIGVEC_DEFINED
struct sigvec { void (*sv_handler)(int); int sv_mask; int sv_flags; };
#endif
int sigvec(int sig, struct sigvec *v, struct sigvec *ov) {
    struct sigaction n = {0}, o = {0};
    if (v) { n.sa_handler = v->sv_handler; n.sa_flags = v->sv_flags; }
    int r = sigaction(sig, v ? &n : 0, ov ? &o : 0);
    if (r == 0 && ov) { ov->sv_handler = o.sa_handler; ov->sv_flags = o.sa_flags; }
    return r;
}
SIGVECEOF

RUN CFLAGS="-D_GNU_SOURCE" CXXFLAGS="-std=gnu++98" \
    LIBS="-lX11 -lXext" \
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
