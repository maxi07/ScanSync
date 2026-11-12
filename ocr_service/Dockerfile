FROM python:3.15-slim-trixie AS native-build

ENV TZ=Europe/Berlin
ARG GHOSTSCRIPT_VERSION=10.08.0
ARG GHOSTSCRIPT_SHA256=caf199e3f233f1290b27d0972d636f66c303355f2353309b7bfddf1edda06b3d
ARG JBIG2_COMMIT=4553595aa094cad7d55c4efc9657ea31db23c742

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl build-essential automake autoconf libtool pkg-config \
    libleptonica-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp
RUN curl -fsSL "https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs$(echo "$GHOSTSCRIPT_VERSION" | tr -d .)/ghostscript-${GHOSTSCRIPT_VERSION}.tar.gz" -o ghostscript.tar.gz && \
    echo "${GHOSTSCRIPT_SHA256}  ghostscript.tar.gz" | sha256sum -c - && \
    tar -xzf ghostscript.tar.gz && \
    cd "ghostscript-${GHOSTSCRIPT_VERSION}" && \
    ./configure --without-x --disable-cups && \
    make -j"$(nproc)" && make install

RUN curl -fsSL "https://github.com/agl/jbig2enc/archive/${JBIG2_COMMIT}.tar.gz" -o jbig2enc.tar.gz && \
    tar -xzf jbig2enc.tar.gz && cd "jbig2enc-${JBIG2_COMMIT}" && \
    autoreconf -fi && ./configure && make -j"$(nproc)" && make install

FROM python:3.15-slim-trixie AS runtime

ENV TZ=Europe/Berlin \
    CONFIG_PATH=/app/scansynclib/scansynclib/config.json

RUN apt-get update && apt-get install -y --no-install-recommends \
    unpaper qpdf pngquant tesseract-ocr tesseract-ocr-eng tesseract-ocr-deu \
    libleptonica6 libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=native-build /usr/local/bin/gs /usr/local/bin/gs
COPY --from=native-build /usr/local/share/ghostscript/ /usr/local/share/ghostscript/
COPY --from=native-build /usr/local/bin/jbig2 /usr/local/bin/jbig2
RUN gs --version && jbig2 --version

WORKDIR /app
COPY ocr_service/requirements.txt .
COPY requirements-dev.txt /tmp/constraints.txt
COPY scansynclib/ /app/scansynclib/
RUN --mount=type=cache,target=/root/.cache/pip pip install -c /tmp/constraints.txt -r requirements.txt /app/scansynclib && pip check
COPY ocr_service/ /app/

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
CMD ["python", "main.py"]