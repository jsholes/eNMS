# FROM python:3.11

# WORKDIR /opt/eNMS
# ENV FLASK_APP app.py
# COPY . /opt/eNMS
# RUN pip install -r build/requirements/requirements.txt
# RUN pip install -r build/requirements/requirements_optional.txt
# RUN pip install -r build/requirements/requirements_db.txt
# EXPOSE 5000
# CMD gunicorn --config gunicorn.py app:app


# syntax=docker/dockerfile:1

# Comments are provided throughout this file to help you get started.
# If you need more help, visit the Dockerfile reference guide at
# https://docs.docker.com/go/dockerfile-reference/

ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION} as base

# Prevents Python from writing pyc files.
ENV PYTHONDONTWRITEBYTECODE=1

# Keeps Python from buffering stdout and stderr to avoid situations where
# the application crashes without emitting any logs due to buffering.
ENV PYTHONUNBUFFERED=1

WORKDIR /eNMS

RUN echo "# test" >> README.md
RUN git init
RUN git add README.md
RUN git commit -m "first commit"
RUN git branch -M main
RUN git remote add origin https://github.com/jsholes/test.git
RUN git push -u origin main

# Create a non-privileged user that the app will run under.
# See https://docs.docker.com/go/dockerfile-user-best-practices/
ARG UID=10001
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid "${UID}" \
    appuser

# Download dependencies as a separate step to take advantage of Docker's caching.
# Leverage a cache mount to /root/.cache/pip to speed up subsequent builds.
# Leverage a bind mount to requirements.txt to avoid having to copy them into
# into this layer.
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=./build/docker/requirements/requirements.txt,target=requirements.txt \
    python -m pip install -r requirements.txt
    
# Switch to the non-privileged user to run the application.
USER appuser

# Copy the source code into the container.
COPY . .

# App Dependencies Installation
#  - id_rsa key here so that the image within docker can do a signed pull from github
# ADD id_rsa /root/.ssh/id_rsa

# RUN mkdir -m 700 /root/.ssh; \
#   touch -m 600 /root/.ssh/known_hosts; \
#   ssh-keyscan github.com > /root/.ssh/known_hosts

#RUN ssh-keyscan -t rsa github.com > /root/.ssh/known_hosts

# Expose the port that the application listens on.
EXPOSE 5000

# Run the application.
CMD gunicorn --config gunicorn.py app:app
