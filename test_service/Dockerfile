FROM selenium/standalone-chromium:155.0.8059.39

# Switch to the root user to install dependencies
USER root

# Update package lists and install Python3, pip, and venv
# Note: --force-overwrite works around a Debian trixie transition conflict between
# libssl3t64 (shipped in the base image) and openssl-provider-legacy, which both
# claim /usr/lib/*/ossl-modules/legacy.so.
RUN apt-get update && \
    apt-get install -y -o Dpkg::Options::="--force-overwrite" \
        python3 python3-pip python3-venv && \
    rm -rf /var/lib/apt/lists/*

# Create a Python virtual environment
RUN python3 -m venv /opt/venv

# Set environment variables for the virtual environment
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Set the working directory to /tests
WORKDIR /tests

# Copy the requirements file and install dependencies
COPY test_service/requirements.txt .
COPY requirements-dev.txt /tmp/constraints.txt
COPY scansynclib/ ./scansynclib/
RUN --mount=type=cache,target=/root/.cache/pip pip install -c /tmp/constraints.txt -r requirements.txt ./scansynclib && pip check

# Copy the test files and the library to the container
COPY tests/ ./tests

# Set the entry point to run pytest on the tests directory
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
ENTRYPOINT ["pytest", "tests/"]