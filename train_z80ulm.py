#!/usr/bin/env python3
"""
train_z80ulm.py — Train a tiny YES/NO/MAYBE model for Z80-μLM on A+

Trains a 2-bit quantized autoregressive character model with the same
architecture as HarryR/z80ai, and exports weights as packed A+ arrays.
Pure Python + NumPy, no PyTorch needed for this tiny model.
"""

import numpy as np
import sys, os

# ── Architecture ──
INPUT_SIZE = 128    # trigram hash buckets
HIDDEN_SIZES = [64, 48, 32]
OUTPUT_SIZE = 4     # Y, N, M, ? (YES, NO, MAYBE, UNKNOWN)
WEIGHT_VALUES = [-2, -1, 0, 1]  # 2-bit quantization grid

# ── Training data ──
TRAINING_DATA = [
    ("hello", "Y"), ("hi", "Y"), ("hey", "Y"), ("yo", "Y"),
    ("are you a robot", "Y"), ("are you real", "Y"),
    ("do you dream", "M"), ("do you sleep", "M"),
    ("can you think", "M"), ("are you conscious", "M"),
    ("bye", "N"), ("goodbye", "N"), ("no", "N"),
    ("are you human", "N"), ("are you alive", "N"),
    ("what is 2+2", "Y"), ("is sky blue", "Y"),
    ("will it rain", "M"), ("is it cold", "M"),
    ("do you eat", "N"), ("do you drink", "N"),
    ("thanks", "Y"), ("thank you", "Y"),
    ("are you smart", "Y"), ("you are dumb", "N"),
    ("do you like me", "M"), ("tell me a joke", "M"),
    ("help", "Y"), ("error", "N"),
    ("random stuff here", "?"), ("xyzzy", "?"),
]

CHAR_TO_IDX = {'Y': 0, 'N': 1, 'M': 2, '?': 3}
IDX_TO_CHAR = {0: 'YES', 1: 'NO', 2: 'MAYBE', 3: '?'}

def trigram_hash(text, num_buckets=128):
    """Hash input text into bucket array using trigrams."""
    buckets = np.zeros(num_buckets, dtype=np.float32)
    text = text.lower()
    codes = [ord(c) for c in text if c.isalpha() or c == ' ']
    n = len(codes)
    if n < 3:
        return buckets
    for i in range(n - 2):
        h = (codes[i] * 31 + codes[i+1] * 37 + codes[i+2] * 41) % num_buckets
        buckets[h] += 1
    return buckets

def quantize_weights(w, grid=WEIGHT_VALUES):
    """Quantize float weights to nearest value in {-2,-1,0,1}."""
    w_flat = w.flatten()
    result = np.zeros_like(w_flat, dtype=np.int8)
    for i, val in enumerate(w_flat):
        dists = [abs(val - g) for g in grid]
        result[i] = grid[np.argmin(dists)]
    return result.reshape(w.shape)

def pack_weights_2bit(w_flat):
    """Pack quantized weights into bytes (4 weights per byte).
    Mapping: -2->2, -1->3, 0->0, 1->1 (in 2-bit representation)."""
    mapping = {-2: 2, -1: 3, 0: 0, 1: 1}
    packed = []
    for i in range(0, len(w_flat), 4):
        byte_val = 0
        for j in range(4):
            if i + j < len(w_flat):
                val = mapping.get(int(w_flat[i + j]), 0)
                byte_val |= (val << (2 * (3 - j)))
        packed.append(byte_val)
    return packed

def train():
    """Train a simple 3-layer model and export A+ weights."""
    np.random.seed(42)

    # Initialize weights as float
    layers = []
    prev_size = INPUT_SIZE
    for h in HIDDEN_SIZES:
        w = np.random.randn(h, prev_size) * 0.1
        layers.append(w)
        prev_size = h
    w_out = np.random.randn(OUTPUT_SIZE, prev_size) * 0.1
    layers.append(w_out)

    # Simple SGD training
    lr = 0.01
    epochs = 500
    char_to_idx = CHAR_TO_IDX

    print(f"Training on {len(TRAINING_DATA)} examples, {epochs} epochs...")
    best_acc = 0

    for epoch in range(epochs):
        total_loss = 0
        correct = 0

        for text, target_char in TRAINING_DATA:
            # Forward pass
            x = trigram_hash(text)
            target = char_to_idx[target_char]

            activations = [x]
            pre_acts = []
            for w in layers[:-1]:
                z = w @ x
                pre_acts.append(z)
                x = np.maximum(0, z)  # ReLU
                activations.append(x)
            z_out = layers[-1] @ x
            logits = z_out

            # Softmax + cross-entropy
            logits_stable = logits - np.max(logits)
            probs = np.exp(logits_stable) / np.sum(np.exp(logits_stable))
            loss = -np.log(probs[target] + 1e-9)
            total_loss += loss

            if np.argmax(probs) == target:
                correct += 1

            # Backward pass
            dlogits = probs.copy()
            dlogits[target] -= 1

            # Gradient for output layer
            dw_out = np.outer(dlogits, x)
            dx = layers[-1].T @ dlogits

            # Backprop through hidden layers
            for i in range(len(layers) - 2, -1, -1):
                dz = dx * (pre_acts[i] > 0)  # ReLU gradient
                dw = np.outer(dz, activations[i])
                layers[i] -= lr * dw
                if i > 0:
                    dx = layers[i].T @ dz

            layers[-1] -= lr * dw_out

        acc = correct / len(TRAINING_DATA)
        if acc > best_acc:
            best_acc = acc
            best_layers = [w.copy() for w in layers]

        if epoch % 50 == 0:
            print(f"  Epoch {epoch:3d}: loss={total_loss/len(TRAINING_DATA):.3f} acc={acc:.1%}")

    print(f"Best accuracy: {best_acc:.1%}")

    # Quantize weights
    print("\nQuantizing weights to {-2,-1,0,+1}...")
    quantized = [quantize_weights(w) for w in best_layers]

    # Pack into 2-bit format
    sizes = []
    packed_layers = []
    for w in quantized:
        w_flat = w.flatten()
        sizes.append(w.shape)
        packed = pack_weights_2bit(w_flat)
        packed_layers.append(packed)

    # Export as A+ array literals
    print("\n=== A+ Weight Arrays (paste into z80ulm.a+) ===")
    for i, (p, s) in enumerate(zip(packed_layers, sizes)):
        name = f"W{i+1}"
        in_dim = s[1]
        out_dim = s[0]
        packed_str = ' '.join(str(b) for b in p)
        print(f"\n{name} {in_dim}->{out_dim} ({len(p)} bytes packed):")
        print(f"{name} = {len(p)} rho {packed_str[:200]}...")

    # Compute test accuracy
    print("\n=== Test Results ===")
    for text, target in TRAINING_DATA[:10]:
        x = trigram_hash(text)
        for w in quantized[:-1]:
            x = np.maximum(0, w @ x)
        logits = quantized[-1] @ x
        pred = np.argmax(logits)
        print(f"  '{text}' -> {IDX_TO_CHAR.get(pred, '?')} (expected {target})")

    print("\nDone. Copy the weight arrays into z80ulm.a+ to run inference on A+.")

if __name__ == '__main__':
    train()
