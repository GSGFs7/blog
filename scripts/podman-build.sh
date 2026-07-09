#!/usr/bin/bash

source .env

podman build -f ./.config/docker/Dockerfile -t django \
    --secret id=hf_token,src=./hf_token.txt \
    --build-arg MODEL_NAME=google/embeddinggemma-300m \
    --build-arg SENTENCE_TRANSFORMERS_HOME=sentence_transformers_models \
    .
