# Inherit from an upstream image
FROM jupyter/base-notebook:2023-05-15

COPY binder/environment.yml /tmp/environment.yml
COPY binder/apt.txt /tmp/apt.txt

RUN mamba env update --prefix ${CONDA_DIR} --file /tmp/environment.yml

# Switch to root user to install apt packages
USER root
RUN apt-get update && xargs -a /tmp/apt.txt apt install -y && rm -r /var/lib/apt/lists/*

# Switch back to jovyan user
USER jovyan
