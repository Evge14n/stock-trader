from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import orjson

from agents.python import paper_broker
from config.settings import settings

SYSTEM_PROMPT = """You are a disciplined swing trader. Based on technical, fundamental, news, sector, momentum, and volatility analyses, decide whether to buy, sell, or hold.
Output: action (buy/sell/pass), stop_loss_pct, take_profit_pct, one-sentence reasoning."""


def _format_trade_as_training_example(trade: dict, context_analyses: list[dict] | None = None) -> dict:
    symbol = trade["symbol"]
    entry = trade["entry_price"]
    pnl = trade.get("pnl", 0)
    reason = trade.get("close_reason", "")

    user_input = f"Symbol: {symbol}\nEntry: ${entry:.2f}\n"
    if context_analyses:
        user_input += "\nAgent analyses:\n"
        for a in context_analyses[:6]:
            user_input += f"- {a.get('agent', '?')}: {a.get('signal', '?')} (conf {a.get('confidence', 0):.2f})\n"

    outcome = "profitable" if pnl > 0 else "loss" if pnl < 0 else "breakeven"
    reasoning = f"Trade resulted in {outcome} of ${pnl:+.2f}, closed via {reason}"

    if pnl > 0:
        assistant = f"action: buy\nstop_loss_pct: 0.03\ntake_profit_pct: 0.06\nreasoning: {reasoning}"
    elif pnl < 0:
        assistant = f"action: pass\nreasoning: {reasoning}, stop loss hit - would avoid similar setup"
    else:
        assistant = f"action: pass\nreasoning: {reasoning}"

    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_input.strip()},
            {"role": "assistant", "content": assistant},
        ],
        "metadata": {
            "symbol": symbol,
            "pnl": pnl,
            "outcome": outcome,
            "closed_at": trade.get("closed_at"),
        },
    }


def export_training_dataset(output_path: Path | None = None) -> Path:
    output_path = output_path or (settings.data_dir / "fine_tune_dataset.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(paper_broker._db_path()) as conn:
        conn.row_factory = sqlite3.Row
        trades = conn.execute("SELECT * FROM trades WHERE closed_at IS NOT NULL ORDER BY id ASC").fetchall()

    count = 0
    with open(output_path, "wb") as f:
        for t in trades:
            example = _format_trade_as_training_example(dict(t))
            f.write(orjson.dumps(example) + b"\n")
            count += 1

    with open(settings.data_dir / "fine_tune_manifest.json", "wb") as f:
        f.write(
            orjson.dumps(
                {
                    "exported_at": datetime.now().isoformat(),
                    "dataset_path": str(output_path),
                    "example_count": count,
                    "system_prompt": SYSTEM_PROMPT,
                    "base_model": "google/gemma-2b-it",
                    "recommended_lora": {
                        "r": 16,
                        "alpha": 32,
                        "dropout": 0.05,
                        "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
                    },
                    "training_recipe": {
                        "epochs": 3,
                        "learning_rate": 2e-4,
                        "batch_size": 4,
                        "gradient_accumulation_steps": 4,
                        "max_seq_length": 1024,
                        "use_4bit_quantization": True,
                    },
                },
                option=orjson.OPT_INDENT_2,
            )
        )

    return output_path


def generate_kaggle_notebook(output_path: Path | None = None) -> Path:
    output_path = output_path or (settings.data_dir / "stock_trader_finetune.ipynb")

    cells = [
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": [
                "# Fine-tune Gemma on your own trading decisions\n",
                "\n",
                "Upload `fine_tune_dataset.jsonl` to Kaggle as a dataset input, then run this notebook.\n",
                "Uses Unsloth + QLoRA for efficient training on free T4 GPU.",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "!pip install -q unsloth bitsandbytes accelerate peft trl datasets\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "from unsloth import FastLanguageModel\n",
                "\n",
                "model, tokenizer = FastLanguageModel.from_pretrained(\n",
                "    model_name='unsloth/gemma-2-2b-it-bnb-4bit',\n",
                "    max_seq_length=1024,\n",
                "    load_in_4bit=True,\n",
                ")\n",
                "\n",
                "model = FastLanguageModel.get_peft_model(\n",
                "    model,\n",
                "    r=16,\n",
                "    target_modules=['q_proj','k_proj','v_proj','o_proj'],\n",
                "    lora_alpha=32,\n",
                "    lora_dropout=0.05,\n",
                ")\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "import json\n",
                "from datasets import Dataset\n",
                "\n",
                "with open('/kaggle/input/stock-trader-dataset/fine_tune_dataset.jsonl') as f:\n",
                "    rows = [json.loads(line) for line in f if line.strip()]\n",
                "\n",
                "def to_text(row):\n",
                "    msgs = row['messages']\n",
                "    return tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)\n",
                "\n",
                "dataset = Dataset.from_list([{'text': to_text(r)} for r in rows])\n",
                "print(f'Examples: {len(dataset)}')\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "from trl import SFTTrainer\n",
                "from transformers import TrainingArguments\n",
                "\n",
                "trainer = SFTTrainer(\n",
                "    model=model, tokenizer=tokenizer,\n",
                "    train_dataset=dataset, dataset_text_field='text',\n",
                "    max_seq_length=1024,\n",
                "    args=TrainingArguments(\n",
                "        per_device_train_batch_size=4, gradient_accumulation_steps=4,\n",
                "        warmup_steps=10, num_train_epochs=3, learning_rate=2e-4,\n",
                "        fp16=False, bf16=True, logging_steps=5,\n",
                "        output_dir='outputs', optim='adamw_8bit',\n",
                "    ),\n",
                ")\n",
                "trainer.train()\n",
            ],
        },
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                "model.save_pretrained_gguf('gemma_stock_trader', tokenizer, quantization_method='q4_k_m')\n",
                "print('GGUF saved. Download and import into Ollama:')\n",
                "print('ollama create gemma-stock-trader -f Modelfile')\n",
            ],
        },
    ]

    nb = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.10"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(orjson.dumps(nb, option=orjson.OPT_INDENT_2))

    return output_path
