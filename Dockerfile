# Zalo AI Challenge 2026 DataMate recommended Blackwell-compatible base image.
# This is a template. Add local inference weights to models/ before building.
FROM vllm/vllm-openai:v0.10.1.1
ENTRYPOINT []
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PIP_NO_CACHE_DIR=1 NCCL_P2P_DISABLE=1 \
    PYTHONPATH=/code MODEL_PATH=/code/models/Qwen3-8B TP_SIZE=2
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
