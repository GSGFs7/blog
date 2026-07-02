FROM archlinux:latest AS builder

WORKDIR /app

# emscripten needs nvm
RUN pacman -Syu --noconfirm base-devel python git curl && \
    git clone --depth 1 --branch v3.15.0b3 https://github.com/python/cpython.git && \
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.5/install.sh | bash

WORKDIR /app/cpython

# patch it. the 'test_module.patch' is not necessary
COPY test_module.patch python_worker.patch /tmp/

RUN git checkout v3.15.0b3 && \
    git apply /tmp/test_module.patch /tmp/python_worker.patch

# static build the module
RUN python Platforms/emscripten install-emscripten --emsdk-cache cross-build/emsdk-cache && \
    python Platforms/emscripten configure-build-python --emsdk-cache cross-build/emsdk-cache && \
    python Platforms/emscripten make-build-python --emsdk-cache cross-build/emsdk-cache && \
    python Platforms/emscripten make-dependencies --emsdk-cache cross-build/emsdk-cache && \
    python Platforms/emscripten configure-host --emsdk-cache cross-build/emsdk-cache && \
    printf "\n*static*\ntest_module test_module.c\n" >> cross-build/wasm32-emscripten/build/python/Modules/Setup.local && \
    python Platforms/emscripten make-host --emsdk-cache cross-build/emsdk-cache

# core assets files
RUN mkdir -p /out && \
    cp cross-build/wasm32-emscripten/build/python/web_example/python.mjs /out/ && \
    cp cross-build/wasm32-emscripten/build/python/web_example/python.wasm /out/ && \
    cp cross-build/wasm32-emscripten/build/python/web_example/python.worker.mjs /out/ && \
    cp cross-build/wasm32-emscripten/build/python/web_example/python*.zip /out/

# Export artifacts with `podman build --target exporter -o type=local,dest=./dist .`
FROM scratch AS exporter

COPY --from=builder /out/ /
