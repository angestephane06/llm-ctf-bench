# Sandbox in which the agent's commands run. The container is started with no network
# (--network none), all capabilities dropped and no-new-privileges, as an unprivileged user.
# The base image is pinned by digest so that every rebuild starts from the same layers.
ARG BASE_IMAGE=ubuntu:24.04@sha256:9c7f200c07e3d4a03e7249d2c16bf66a51120fb876aa2242cf31451412543289
FROM ${BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash coreutils file binutils xxd bsdextrautils gdb unzip bzip2 gzip xz-utils \
        python3 python3-pycryptodome python3-sympy \
        libimage-exiftool-perl sleuthkit \
    && rm -rf /var/lib/apt/lists/*

# Unprivileged user with uid 1000; the task files are copied in at run time, owned by it.
RUN (id -u ubuntu >/dev/null 2>&1 && userdel -r ubuntu) || true \
    && useradd --uid 1000 --create-home --shell /bin/bash ctf \
    && mkdir /ctf && chown ctf:ctf /ctf

USER ctf
WORKDIR /ctf
CMD ["sleep", "infinity"]
