# Use the latest Seleniarm standalone Chromium image as the base image
FROM seleniarm/standalone-chromium:latest

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

# Switch to the root user to install dependencies
USER root

# Update package lists and install Python3, pip, and venv.
# --force-overwrite handles file ownership changes during package splits
# (e.g. openssl-provider-legacy taking legacy.so from libssl3t64).
RUN apt-get update && apt-get install -y -o Dpkg::Options::="--force-overwrite" python3 python3-pip python3-venv

# Create a Python virtual environment
RUN python3 -m venv /opt/venv

# Set environment variables for the virtual environment
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Set the working directory to /tests
WORKDIR /tests

# Copy the requirements file and install dependencies
COPY test_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the test files and the library to the container
COPY tests/ ./tests
COPY scansynclib/ ./scansynclib/

# Install the scansynclib package
RUN pip install ./scansynclib

# Set the entry point to run pytest on the tests directory
ENTRYPOINT ["pytest", "tests/"]