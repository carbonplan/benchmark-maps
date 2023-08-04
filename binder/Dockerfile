# Inherit from an upstream image
FROM jupyter/base-notebook:2023-05-15

# Copy necessary files
COPY binder/environment.yml /tmp/environment.yml
COPY binder/apt.txt /tmp/apt.txt

# Switch to root user to install apt packages
USER root

# Install apt packages and clean up
RUN apt-get update && \
    xargs -a /tmp/apt.txt apt install -y && \
    apt-get autoremove -y && \
    apt-get autoclean && \
    rm -rf /var/lib/apt/lists/* && \
    rm /tmp/apt.txt

# Install conda packages and clean up
USER jovyan
RUN mamba env update --prefix ${CONDA_DIR} --file /tmp/environment.yml && \
    mamba clean --all -f -y && \
    rm /tmp/environment.yml
