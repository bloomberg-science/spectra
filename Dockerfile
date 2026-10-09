FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TESTSUITE_ROOT=/app/testsuite

# Uncomment and set appropriate proxy values if building behind a proxy:
# ARG HTTP_PROXY=http://your-proxy:port
# ARG HTTPS_PROXY=http://your-proxy:port
# ARG NO_PROXY=localhost,127.0.0.0/8
# ENV http_proxy=${HTTP_PROXY}
# ENV https_proxy=${HTTPS_PROXY}
# ENV no_proxy=${NO_PROXY}

# ─── System Dependencies ───────────────────────────────────────────────────────

RUN apt-get update && apt-get install -y ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Uncomment if using a proxy with custom CA certs:
# COPY certs/ /usr/local/share/ca-certificates/
# RUN update-ca-certificates
# ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt
# ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

RUN apt-get update && apt-get install -y \
    build-essential gcc g++ make pkg-config wget curl git ca-certificates \
    lcov strace auditd \
    python3 python3-venv python3-pip python3-dev python3-pytest \
    ocaml camlp4-extra camlp4 exuberant-ctags libcapstone-dev \
    openjdk-21-jdk-headless \
    perl libtest-harness-perl libtest-unit-perl \
    autoconf automake libtool meson ninja-build \
    libpcre2-dev zlib1g-dev libcrypt-dev \
    libssl-dev libapr1-dev libaprutil1-dev \
    libevent-dev \
    libuv1-dev liburcu-dev libcap-dev libxml2-dev libmaxminddb-dev \
    libjemalloc-dev libkrb5-dev \
    liblz4-dev libzstd-dev libpam0g-dev libsystemd-dev libicu-dev libnuma-dev \
    libprotobuf-dev protobuf-compiler libaio-dev \
    flex bison \
    libnghttp2-dev libprotobuf-c-dev libidn2-dev libedit-dev iproute2 \
    libbenchmark-dev libgmock-dev libgtest-dev nlohmann-json3-dev \
    binutils-dev libseccomp-dev \
    libunwind-dev uuid-dev libreadline-dev libsqlite3-dev tcl protobuf-c-compiler \
    nghttp2-client \
    time bsdmainutils unzip vim \
    && rm -rf /var/lib/apt/lists/*

# Ghidra 11.4 requires Java 21
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64

# bmq requires cmake >= 3.23; Ubuntu 22.04 ships 3.22
RUN wget -q https://github.com/Kitware/CMake/releases/download/v3.28.3/cmake-3.28.3-linux-x86_64.tar.gz \
    && tar xzf cmake-3.28.3-linux-x86_64.tar.gz --strip-components=1 -C /usr/local \
    && rm cmake-3.28.3-linux-x86_64.tar.gz

WORKDIR /app

# ─── Copy SPECTRA ──────────────────────────────────────────────────────

# Build context is the repository checkout; submodules must already be populated
# (git clone --recurse-submodules, or git submodule update --init --recursive).
COPY . /app

RUN for d in bin_analysis_tools/safer testsuite/bind testsuite/bmq testsuite/comdb2 \
             testsuite/lighttpd testsuite/memcached testsuite/mysql testsuite/nginx \
             testsuite/postgresql testsuite/proftpd testsuite/redis; do \
        if [ -z "$(ls -A "/app/$d" 2>/dev/null)" ]; then \
            echo "ERROR: submodule $d is empty. Run 'git submodule update --init --recursive' before 'docker build'."; \
            exit 1; \
        fi; \
    done

# ─── Run install.sh (venv, SAFER, Apache download, Ghidra) ────────────────────

WORKDIR /app
RUN bash /app/install.sh

# ─── Build All Packages ───────────────────────────────────────────────────────

WORKDIR /app/testsuite

# Build all evaluation packages at the optimization levels used in the evaluation,
# then collect the ELF binaries into subset_binaries/gcc/<opt>/{fulldbg,symonly,stripped}/.
# Override with e.g. --build-arg OPT_LEVELS=O2 for a faster, O2-only build.
ARG OPT_LEVELS="O0 O1 O2"
RUN OPT_LEVELS="${OPT_LEVELS}" ./build_all.sh no \
    && ./collect_binary.sh ${OPT_LEVELS}

# ─── Default ───────────────────────────────────────────────────────────────────

WORKDIR /app
ENV PATH="/app/analysisenv/bin:${PATH}"

# Fix libsdata: deduplicate and resolve stale dlopen paths
RUN python3 /app/fix_libsdata.py

CMD ["/bin/bash"]
