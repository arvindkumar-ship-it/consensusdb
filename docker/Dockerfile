# syntax=docker/dockerfile:1
# Stage 1: mkdb_server Linux pe build (sirf jab MKDB_SRC me CMakeLists.txt ho, warna skip)
FROM gcc:13 AS mkdb-build
COPY --from=mkdb . /src
RUN mkdir -p /out && cd /src && if [ -f CMakeLists.txt ]; then \
      apt-get update && apt-get install -y --no-install-recommends cmake && \
      cmake -S . -B build -DCMAKE_BUILD_TYPE=Release && \
      cmake --build build --target mkdb_server -j"$(nproc)" && \
      cp "$(find build -name mkdb_server -type f | head -1)" /out/mkdb_server; \
    fi

# Stage 2: runtime (python code sirf stdlib use karta hai, pip install nahi)
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends socat && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=mkdb-build /out/ /opt/mkdb/
COPY distributed/ distributed/
COPY optimizer/ optimizer/
COPY workload/ workload/
COPY abtest/ abtest/
COPY bench/ bench/
COPY router.py run_node.py ./
COPY docker/entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh
ENV PYTHONUNBUFFERED=1 MKDB_SERVER=/opt/mkdb/mkdb_server
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]