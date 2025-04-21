FROM python:3.13-slim

# Install ocrmypdf requirements
RUN apt-get update && apt-get install -y \
    unpaper \
    libjpeg-dev \
    wget \
    libpng-dev \
    libtiff-dev \
    libffi-dev \
    qpdf \
    pngquant \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-deu \
    curl \
    build-essential \
    automake \
    autoconf \
    libtool \
    pkg-config \
    git \
    && rm -rf /var/lib/apt/lists/*


# Install Ghostscript 10.02.1 from source, as from APT 10.0 to 10.02 is unsupported
WORKDIR /tmp
RUN wget https://github.com/ArtifexSoftware/ghostpdl-downloads/releases/download/gs10050/ghostscript-10.05.0.tar.gz && \
    tar -xzf ghostscript-10.05.0.tar.gz && \
    cd ghostscript-10.05.0 && \
    ./configure && \
    make -j$(nproc) && \
    make install && \
    cd .. && rm -rf ghostscript-10.05.0 ghostscript-10.05.0.tar.gz

# Dependency for JBig2
RUN apt-get update && apt-get install -y \
    libleptonica-dev \
    && rm -rf /var/lib/apt/lists/*

# JBIG2 Encoder
RUN git clone https://github.com/agl/jbig2enc.git && \
    cd jbig2enc && \
    autoreconf -fi && \
    ./configure && \
    make && make install && \
    cd .. && rm -rf jbig2enc

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["python", "main.py"]