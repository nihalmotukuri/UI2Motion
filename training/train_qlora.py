"""
Fine-tune Qwen/Qwen2.5-Coder-7B-Instruct into UI2Motion-8B using 4-bit QLoRA (Unsloth + TRL)
and export directly to Q4_K_M GGUF + Ollama Modelfile.

Run on GPU (Colab / Kaggle / RunPod / local CUDA):
  pip install "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
  pip install --no-deps trl peft accelerate bitsandbytes
  python training/train_qlora.py
"""

from __future__ import annotations

from pathlib import Path

from unsloth import FastLanguageModel, is_bfloat16_supported
from datasets import load_dataset
from trl import SFTConfig, SFTTrainer

BASE_MODEL = "Qwen/Qwen2.5-Coder-7B-Instruct"
DATASET_PATH = "dataset/train.jsonl"
OUTPUT_DIR = "outputs/ui2motion-7b-lora"
GGUF_EXPORT_DIR = "outputs/ui2motion-7b-gguf"
MAX_SEQ_LENGTH = 8192


def main() -> None:
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=32,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=64,
        lora_dropout=0.0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    raw_dataset = load_dataset("json", data_files=DATASET_PATH, split="train")

    def format_chat(example: dict) -> dict:
        text = tokenizer.apply_chat_template(
            example["messages"],
            tokenize=False,
            add_generation_prompt=False,
        )
        return {"text": text}

    dataset = raw_dataset.map(format_chat, remove_columns=raw_dataset.column_names)

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        args=SFTConfig(
            dataset_text_field="text",
            max_length=MAX_SEQ_LENGTH,
            dataset_num_proc=2,
            packing=False,
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            warmup_steps=15,
            num_train_epochs=3,
            learning_rate=2e-4,
            fp16=not is_bfloat16_supported(),
            bf16=is_bfloat16_supported(),
            logging_steps=5,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="cosine",
            seed=3407,
            output_dir=OUTPUT_DIR,
            report_to="none",
        ),
    )

    trainer.train()

    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)

    # Export quantized Q4_K_M GGUF (~5.0 GB) for 16 GB RAM consumer inference in Ollama
    model.save_pretrained_gguf(
        GGUF_EXPORT_DIR,
        tokenizer,
        quantization_method="q4_k_m",
    )

    gguf_files = sorted(Path(GGUF_EXPORT_DIR).glob("*.gguf"))
    gguf_name = gguf_files[0].name if gguf_files else "unsloth.Q4_K_M.gguf"
    modelfile_path = Path(GGUF_EXPORT_DIR) / "Modelfile"
    modelfile_path.write_text(
        f'FROM ./{gguf_name}\n'
        'PARAMETER num_ctx 8192\n'
        'PARAMETER temperature 0.2\n'
        'PARAMETER top_p 0.9\n',
        encoding="utf-8",
    )
    print(f"Export complete. Load into Ollama with:\n  ollama create ui2motion-7b:latest -f {modelfile_path}")


if __name__ == "__main__":
    main()
