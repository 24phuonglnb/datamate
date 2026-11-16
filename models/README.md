Place the complete Qwen3-14B weights and tokenizer under `models/Qwen3-14B/` (the path in the
Dockerfile's `MODEL_PATH`). Only that folder enters the GPU image (`Dockerfile.dockerignore`).

Do NOT download models inside the Docker container at inference time.
Include the complete local checkpoint (safetensors, tokenizer, config, etc.).
Before submitting verify: released before 2026-10-26; use-permitting license;
all inference models combined <=15B parameters; fixed revision documented in README.
