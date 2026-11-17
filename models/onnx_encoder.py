"""Run the existing MiniLM model without shipping PyTorch to Vercel."""

import os
from pathlib import Path

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer


class MiniLMEncoder:
    def __init__(self):
        directory = Path(__file__).resolve().parent.parent / ".model"
        options = ort.SessionOptions()
        options.intra_op_num_threads = min(4, os.cpu_count() or 1)
        options.inter_op_num_threads = 1
        self.model = ort.InferenceSession(str(directory / "model.onnx"), sess_options=options, providers=["CPUExecutionProvider"])
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=256)

    def encode(self, text, show_progress_bar=False):
        tokens = self.tokenizer.encode(text)
        inputs = {
            "input_ids": np.array([tokens.ids], dtype=np.int64),
            "attention_mask": np.array([tokens.attention_mask], dtype=np.int64),
            "token_type_ids": np.array([tokens.type_ids], dtype=np.int64),
        }
        output = self.model.run(None, {item.name: inputs[item.name] for item in self.model.get_inputs()})[0]
        # MiniLM uses attention-masked mean pooling and L2 normalization.
        mask = inputs["attention_mask"][..., None]
        embedding = (output * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1e-9)
        embedding /= np.maximum(np.linalg.norm(embedding, axis=1, keepdims=True), 1e-12)
        return embedding[0]
