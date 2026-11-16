# Zalo AI Challenge 2026 DataMate recommended Blackwell-compatible base image.
# Put the Qwen3-14B checkpoint in models/Qwen3-14B/ before building; Dockerfile.dockerignore
# keeps every other file (datasets, eval, other checkpoints) out of the build context.
# MODEL_PATH, TP_SIZE and MAX_MODEL_LEN below are the single source of the runtime
# config: predict.sh and src/predict.py read them and carry no defaults of their own.
FROM vllm/vllm-openai:v0.10.1.1
ENTRYPOINT []
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PIP_NO_CACHE_DIR=1 NCCL_P2P_DISABLE=1 \
    PYTHONPATH=/code MODEL_PATH=/code/models/Qwen3-14B TP_SIZE=2 MAX_MODEL_LEN=20480
WORKDIR /code
COPY requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir -r /code/requirements.txt
# Guide's NCCL workaround for the reference 2x RTX 5090 machine.
RUN pip install --no-cache-dir --no-deps nvidia-nccl-cu12==2.27.7
COPY models/ /code/models/
COPY training_code/ /code/training_code/
COPY README.md predict.sh /code/
COPY src/ /code/src/
RUN chmod +x /code/predict.sh
CMD ["bash", "/code/predict.sh"]
