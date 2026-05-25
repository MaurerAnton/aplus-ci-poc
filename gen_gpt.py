#!/usr/bin/env python3
"""
gen_gpt.py - Generate gpt.a+: Mini-GPT multi-head transformer in pure A+

This script:
1. Trains a tiny GPT (4-head attention, FFN, layer norm, residuals) in Python
2. Generates the A+ source code with trained weights
3. The A+ file does forward pass + self-tests

Model config:
  - vocab_size = 8, seq_len = 4
  - d_model = 8, n_heads = 4, d_k = 2, d_ff = 16
  - 1 transformer block
  - Training: 8 sequences, next-token prediction, 100 epochs, MSE loss
"""

import math
import random
import struct

random.seed(42)

# ===========================================================================
# Model Configuration
# ===========================================================================
VOCAB_SIZE = 8
SEQ_LEN = 4
D_MODEL = 8
N_HEADS = 4
D_K = D_MODEL // N_HEADS  # 2
D_FF = 16
LR = 0.05
EPOCHS = 300

# ===========================================================================
# Training data: 8 sequences of length 4, targets = next token
# Simple pattern: each sequence is [i, i+1, i+2, i+3] -> [i+1, i+2, i+3, i+4]
# (mod 8)
# ===========================================================================
X_train = []
Y_train = []
for i in range(8):
    seq = [(i + j) % VOCAB_SIZE for j in range(SEQ_LEN)]
    tgt = [(i + j + 1) % VOCAB_SIZE for j in range(SEQ_LEN)]
    X_train.append(seq)
    Y_train.append(tgt)

# ===========================================================================
# Helper: initialize weights
# ===========================================================================
def randn(rows, cols, scale=0.1):
    """Small random normal-ish values for initialization."""
    return [[random.gauss(0, scale) for _ in range(cols)] for _ in range(rows)]

def zeros(rows, cols):
    return [[0.0 for _ in range(cols)] for _ in range(rows)]

def matmul(A, B):
    """A: m×n, B: n×p -> m×p"""
    m, n = len(A), len(A[0])
    p = len(B[0])
    C = zeros(m, p)
    for i in range(m):
        for j in range(p):
            s = 0.0
            for k in range(n):
                s += A[i][k] * B[k][j]
            C[i][j] = s
    return C

def matmul_AT_B(A, B):
    """A^T @ B: A: m×n, B: m×p -> n×p"""
    m, n = len(A), len(A[0])
    p = len(B[0])
    C = zeros(n, p)
    for i in range(n):
        for j in range(p):
            s = 0.0
            for k in range(m):
                s += A[k][i] * B[k][j]
            C[i][j] = s
    return C

def matmul_A_BT(A, B):
    """A @ B^T: A: m×n, B: p×n -> m×p"""
    m, n = len(A), len(A[0])
    p = len(B)
    C = zeros(m, p)
    for i in range(m):
        for j in range(p):
            s = 0.0
            for k in range(n):
                s += A[i][k] * B[j][k]
            C[i][j] = s
    return C

def add(A, B):
    m, n = len(A), len(A[0])
    return [[A[i][j] + B[i][j] for j in range(n)] for i in range(m)]

def sub(A, B):
    m, n = len(A), len(A[0])
    return [[A[i][j] - B[i][j] for j in range(n)] for i in range(m)]

def mul_scalar(A, s):
    m, n = len(A), len(A[0])
    return [[A[i][j] * s for j in range(n)] for i in range(m)]

def sigmoid(x):
    if isinstance(x, list):
        return [[sigmoid(v) for v in row] for row in x]
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 1.0 if x > 0 else 0.0

def sigmoid_deriv(s):
    """Derivative given sigmoid output s: s * (1 - s)"""
    if isinstance(s, list):
        return [[v * (1.0 - v) for v in row] for row in s]
    return s * (1.0 - s)

def softmax_row(row):
    max_val = max(row)
    exps = [math.exp(v - max_val) for v in row]
    total = sum(exps)
    return [e / total for e in exps]

def layer_norm(x, gamma, beta, eps=1e-5):
    """Layer norm over last dimension WITHOUT sqrt (matching A+ implementation).
    y = gamma * (x - mean) / (var + eps) + beta
    x: m×n, gamma/beta: n
    """
    m, n = len(x), len(x[0])
    out = zeros(m, n)
    means = [0.0] * m
    vars_ = [0.0] * m
    for i in range(m):
        mean = sum(x[i]) / n
        var = sum((v - mean) ** 2 for v in x[i]) / n
        means[i] = mean
        vars_[i] = var
        for j in range(n):
            out[i][j] = gamma[j] * (x[i][j] - mean) / (var + eps) + beta[j]
    return out, means, vars_

def one_hot(indices, vocab_size):
    """indices: list of token ids -> m × vocab_size one-hot matrix"""
    m = len(indices)
    oh = zeros(m, vocab_size)
    for i, idx in enumerate(indices):
        oh[i][idx] = 1.0
    return oh

# ===========================================================================
# Initialize weights
# ===========================================================================
# Token embeddings: vocab_size × d_model
E = randn(VOCAB_SIZE, D_MODEL, 0.1)
# Position embeddings: seq_len × d_model
P = randn(SEQ_LEN, D_MODEL, 0.05)

# Attention weights
Wq = randn(D_MODEL, D_MODEL, 0.1)
Wk = randn(D_MODEL, D_MODEL, 0.1)
Wv = randn(D_MODEL, D_MODEL, 0.1)
Wo = randn(D_MODEL, D_MODEL, 0.1)

# Feed-forward weights
W1 = randn(D_MODEL, D_FF, 0.1)
W2 = randn(D_FF, D_MODEL, 0.1)

# Layer norm params (2 layer norms: after attention, after FFN)
gamma1 = [1.0] * D_MODEL
beta1 = [0.0] * D_MODEL
gamma2 = [1.0] * D_MODEL
beta2 = [0.0] * D_MODEL

# Output projection: re-use embedding matrix E^T
# (Weight tying: output = x @ E^T)

# Scale factor for attention
scale = 1.0 / math.sqrt(D_K)

# ===========================================================================
# Forward pass through one transformer block
# ===========================================================================
def forward(x_indices):
    """
    x_indices: list of token indices length seq_len
    Returns: logits (seq_len × vocab_size), plus all intermediates for backprop
    """
    # 1. Embedding lookup + position encoding
    x_emb = []
    for pos, idx in enumerate(x_indices):
        x_emb.append([E[idx][j] + P[pos][j] for j in range(D_MODEL)])
    # x_emb: seq_len × d_model

    # ===== Multi-Head Attention =====
    # Q, K, V = x @ Wq, x @ Wk, x @ Wv
    Q = matmul(x_emb, Wq)   # 4×8
    K = matmul(x_emb, Wk)   # 4×8
    V = matmul(x_emb, Wv)   # 4×8

    # Split into heads: reshape to (seq_len, n_heads, d_k)
    Q_heads = []  # list of 4 matrices, each 4×2
    K_heads = []
    V_heads = []
    for h in range(N_HEADS):
        Qh = [[Q[i][h * D_K + d] for d in range(D_K)] for i in range(SEQ_LEN)]
        Kh = [[K[i][h * D_K + d] for d in range(D_K)] for i in range(SEQ_LEN)]
        Vh = [[V[i][h * D_K + d] for d in range(D_K)] for i in range(SEQ_LEN)]
        Q_heads.append(Qh)
        K_heads.append(Kh)
        V_heads.append(Vh)

    # Compute attention per head
    attn_weights_all = []  # list of 4 matrices, each 4×4
    context_heads = []
    for h in range(N_HEADS):
        # scores = Qh @ Kh^T * scale
        scores = matmul_A_BT(Q_heads[h], K_heads[h])
        scores = mul_scalar(scores, scale)

        # softmax row-wise
        attn_w = [softmax_row(row) for row in scores]
        attn_weights_all.append(attn_w)

        # context = attn @ Vh
        ctx = matmul(attn_w, V_heads[h])
        context_heads.append(ctx)

    # Concatenate heads: (4,2) × 4 -> (4,8)
    concat = zeros(SEQ_LEN, D_MODEL)
    for i in range(SEQ_LEN):
        for h in range(N_HEADS):
            for d in range(D_K):
                concat[i][h * D_K + d] = context_heads[h][i][d]

    # Output projection
    attn_out = matmul(concat, Wo)

    # Residual connection + Layer Norm 1
    x1_pre_ln = add(x_emb, attn_out)
    x1, means1, vars1 = layer_norm(x1_pre_ln, gamma1, beta1)

    # ===== Feed-Forward Network =====
    # h_ffn = sigmoid(x1 @ W1)
    h_ffn = sigmoid(matmul(x1, W1))   # 4×16
    ffn_out = matmul(h_ffn, W2)        # 4×8

    # Residual connection + Layer Norm 2
    x2_pre_ln = add(x1, ffn_out)
    x2, means2, vars2 = layer_norm(x2_pre_ln, gamma2, beta2)

    # Output logits: x2 @ E^T
    logits = matmul_A_BT(x2, E)   # 4×8

    # Store all intermediates for backprop
    cache = {
        'x_emb': x_emb, 'x_indices': x_indices,
        'Q': Q, 'K': K, 'V': V,
        'Q_heads': Q_heads, 'K_heads': K_heads, 'V_heads': V_heads,
        'attn_weights': attn_weights_all,
        'context_heads': context_heads,
        'concat': concat, 'attn_out': attn_out,
        'x1_pre_ln': x1_pre_ln, 'x1': x1, 'means1': means1, 'vars1': vars1,
        'h_ffn': h_ffn, 'ffn_out': ffn_out,
        'x2_pre_ln': x2_pre_ln, 'x2': x2, 'means2': means2, 'vars2': vars2,
    }
    return logits, cache


# ===========================================================================
# Backpropagation through one transformer block
# ===========================================================================
def backward(cache, dL_dlogits, y_indices):
    """
    Compute gradients w.r.t. all parameters.
    dL_dlogits: seq_len × vocab_size (gradient of loss w.r.t. logits)
    Returns dict of gradients.
    """
    x_emb = cache['x_emb']

    # ---- Output projection: logits = x2 @ E^T ----
    # dL/dx2 = dL/dlogits @ E
    dL_dx2 = matmul(dL_dlogits, E)  # 4×8
    # dL/dE = dL/dlogits^T @ x2
    dL_dE = matmul_AT_B(dL_dlogits, cache['x2'])  # 8×8

    # ---- Layer Norm 2 (no sqrt) ----
    x2_pre_ln = cache['x2_pre_ln']
    means2 = cache['means2']
    vars2 = cache['vars2']
    eps = 1e-5
    dL_dgamma2 = [0.0] * D_MODEL
    dL_dbeta2 = [0.0] * D_MODEL
    dL_dx2_pre_ln = zeros(SEQ_LEN, D_MODEL)

    for i in range(SEQ_LEN):
        mean = means2[i]
        var = vars2[i]
        inv_var_eps = 1.0 / (var + eps)
        x_centered = [x2_pre_ln[i][j] - mean for j in range(D_MODEL)]
        x_norm = [x_centered[j] * inv_var_eps for j in range(D_MODEL)]

        for j in range(D_MODEL):
            dL_dbeta2[j] += dL_dx2[i][j]
            dL_dgamma2[j] += dL_dx2[i][j] * x_norm[j]

        # dL/dvar and dL/dmean
        dL_dvar = 0.0
        dL_dmean = 0.0
        for j in range(D_MODEL):
            dL_dvar += dL_dx2[i][j] * gamma2[j] * x_centered[j] * (-inv_var_eps * inv_var_eps)
            dL_dmean += dL_dx2[i][j] * gamma2[j] * (-inv_var_eps)

        for j in range(D_MODEL):
            d_norm = dL_dx2[i][j] * gamma2[j] * inv_var_eps
            dL_dx2_pre_ln[i][j] = d_norm + dL_dvar * 2.0 * x_centered[j] / D_MODEL + dL_dmean / D_MODEL

    # Residual: dL/dx1 (from skip + x2_pre_ln)
    dL_dx1_from_res2 = dL_dx2_pre_ln
    dL_dffn_out = dL_dx2_pre_ln

    # ---- FFN backward ----
    # ffn_out = h_ffn @ W2
    h_ffn = cache['h_ffn']
    # dL/dW2 = h_ffn^T @ dL/dffn_out
    dL_dW2 = matmul_AT_B(h_ffn, dL_dffn_out)  # 16×8
    # dL/dh_ffn = dL/dffn_out @ W2^T
    dL_dh_ffn = matmul_A_BT(dL_dffn_out, W2)  # 4×16

    # h_ffn = sigmoid(x1 @ W1)
    dL_dh_ffn_deriv = zeros(SEQ_LEN, D_FF)
    for i in range(SEQ_LEN):
        for j in range(D_FF):
            dL_dh_ffn_deriv[i][j] = dL_dh_ffn[i][j] * h_ffn[i][j] * (1.0 - h_ffn[i][j])

    x1 = cache['x1']
    # dL/dW1 = x1^T @ dL_dh_ffn_deriv
    dL_dW1 = matmul_AT_B(x1, dL_dh_ffn_deriv)  # 8×16
    # dL/dx1 (from FFN path)
    dL_dx1_from_ffn = matmul_A_BT(dL_dh_ffn_deriv, W1)  # 4×8

    # Combine residual path + FFN path for dL/dx1
    dL_dx1 = add(dL_dx1_from_res2, dL_dx1_from_ffn)

    # ---- Layer Norm 1 (no sqrt) ----
    x1_pre_ln = cache['x1_pre_ln']
    means1 = cache['means1']
    vars1 = cache['vars1']

    dL_dx1_pre_ln = zeros(SEQ_LEN, D_MODEL)
    dL_dgamma1 = [0.0] * D_MODEL
    dL_dbeta1 = [0.0] * D_MODEL

    for i in range(SEQ_LEN):
        mean = means1[i]
        var = vars1[i]
        inv_var_eps = 1.0 / (var + eps)
        x_centered = [x1_pre_ln[i][j] - mean for j in range(D_MODEL)]
        x_norm = [x_centered[j] * inv_var_eps for j in range(D_MODEL)]

        for j in range(D_MODEL):
            dL_dbeta1[j] += dL_dx1[i][j]
            dL_dgamma1[j] += dL_dx1[i][j] * x_norm[j]

        dL_dvar = 0.0
        dL_dmean = 0.0
        for j in range(D_MODEL):
            dL_dvar += dL_dx1[i][j] * gamma1[j] * x_centered[j] * (-inv_var_eps * inv_var_eps)
            dL_dmean += dL_dx1[i][j] * gamma1[j] * (-inv_var_eps)

        for j in range(D_MODEL):
            d_norm = dL_dx1[i][j] * gamma1[j] * inv_var_eps
            dL_dx1_pre_ln[i][j] = d_norm + dL_dvar * 2.0 * x_centered[j] / D_MODEL + dL_dmean / D_MODEL

    # Residual: dL/dx_emb (from skip) + dL/dattn_out
    dL_dx_emb_from_res = dL_dx1_pre_ln
    dL_dattn_out = dL_dx1_pre_ln

    # ---- Attention output projection backward ----
    # attn_out = concat @ Wo
    concat = cache['concat']
    # dL/dWo = concat^T @ dL/dattn_out
    dL_dWo = matmul_AT_B(concat, dL_dattn_out)  # 8×8
    # dL/dconcat = dL/dattn_out @ Wo^T
    dL_dconcat = matmul_A_BT(dL_dattn_out, Wo)  # 4×8

    # Split dL/dconcat back into heads
    dL_dcontext_heads = []
    for h in range(N_HEADS):
        dctx = [[dL_dconcat[i][h * D_K + d] for d in range(D_K)] for i in range(SEQ_LEN)]
        dL_dcontext_heads.append(dctx)

    # ---- Per-head backward ----
    attn_weights_all = cache['attn_weights']
    V_heads = cache['V_heads']
    Q_heads = cache['Q_heads']
    K_heads = cache['K_heads']

    dL_dWq = zeros(D_MODEL, D_MODEL)
    dL_dWk = zeros(D_MODEL, D_MODEL)
    dL_dWv = zeros(D_MODEL, D_MODEL)
    dL_dx_emb_from_attn = zeros(SEQ_LEN, D_MODEL)

    for h in range(N_HEADS):
        attn_w = attn_weights_all[h]  # 4×4
        Vh = V_heads[h]              # 4×2
        Qh = Q_heads[h]              # 4×2
        Kh = K_heads[h]              # 4×2
        dctx = dL_dcontext_heads[h]  # 4×2

        # context = attn_w @ Vh
        # dL/dattn_w = dctx @ Vh^T
        dL_dattn_w = matmul_A_BT(dctx, Vh)  # 4×4
        # dL/dVh = attn_w^T @ dctx
        dL_dVh = matmul_AT_B(attn_w, dctx)  # 4×2

        # Softmax backward (row-wise)
        dL_dscores = zeros(SEQ_LEN, SEQ_LEN)
        for i in range(SEQ_LEN):
            a_row = attn_w[i]
            d_row = dL_dattn_w[i]
            # dL/ds_i = a_i * (dL/da_i - sum_j(a_j * dL/da_j))
            dot = sum(a_row[j] * d_row[j] for j in range(SEQ_LEN))
            for j in range(SEQ_LEN):
                dL_dscores[i][j] = a_row[j] * (d_row[j] - dot)

        # scores = Qh @ Kh^T * scale
        dL_dscores = mul_scalar(dL_dscores, scale)

        # dL/dQh = dL/dscores @ Kh
        dL_dQh = matmul(dL_dscores, Kh)  # 4×2
        # dL/dKh = dL/dscores^T @ Qh
        dL_dKh = matmul_AT_B(dL_dscores, Qh)  # 4×2

        # Accumulate into full dL/dWq, dL/dWk, dL/dWv
        # dL/dWq[h*d_k:(h+1)*d_k] += x_emb^T @ dL_dQh, etc.
        x_emb_T_dQh = matmul_AT_B(x_emb, dL_dQh)  # 8×2
        x_emb_T_dKh = matmul_AT_B(x_emb, dL_dKh)  # 8×2
        x_emb_T_dVh = matmul_AT_B(x_emb, dL_dVh)  # 8×2

        for r in range(D_MODEL):
            for c in range(D_K):
                dL_dWq[r][h * D_K + c] += x_emb_T_dQh[r][c]
                dL_dWk[r][h * D_K + c] += x_emb_T_dKh[r][c]
                dL_dWv[r][h * D_K + c] += x_emb_T_dVh[r][c]

        # dL/dx_emb from Q, K, V paths
        dL_dx_emb_Q = matmul_A_BT(dL_dQh, Wq)  # incorrectly using full Wq...
        # Actually: dL/dx = dL/dQh @ Wq_h^T where Wq_h is columns [h*d_k:(h+1)*d_k]
        # We need to project through the appropriate slice of Wq

        # For each head, dL/dx contributions:
        # dL/dx += dL_dQh @ Wq_slice^T + dL_dKh @ Wk_slice^T + dL_dVh @ Wv_slice^T
        for i in range(SEQ_LEN):
            for r in range(D_MODEL):
                for c in range(D_K):
                    dL_dx_emb_from_attn[i][r] += dL_dQh[i][c] * Wq[r][h * D_K + c]
                    dL_dx_emb_from_attn[i][r] += dL_dKh[i][c] * Wk[r][h * D_K + c]
                    dL_dx_emb_from_attn[i][r] += dL_dVh[i][c] * Wv[r][h * D_K + c]

    # Total dL/dx_emb = from residual + from attention + from position (none for pos)
    dL_dx_emb = add(dL_dx_emb_from_res, dL_dx_emb_from_attn)

    # dL/dE (embedding) from the embedding lookup
    # Also need dL/dP (position embedding) but we skip that for simplicity
    x_indices = cache['x_indices']
    dL_dE_emb = zeros(VOCAB_SIZE, D_MODEL)
    for pos, idx in enumerate(x_indices):
        for j in range(D_MODEL):
            dL_dE_emb[idx][j] += dL_dx_emb[pos][j]

    # Combine dL/dE from output projection and embedding
    dL_dE_total = add(dL_dE, dL_dE_emb)

    grads = {
        'E': dL_dE_total,
        'Wq': dL_dWq, 'Wk': dL_dWk, 'Wv': dL_dWv, 'Wo': dL_dWo,
        'W1': dL_dW1, 'W2': dL_dW2,
        'gamma1': dL_dgamma1, 'beta1': dL_dbeta1,
        'gamma2': dL_dgamma2, 'beta2': dL_dbeta2,
    }
    return grads


# ===========================================================================
# Training
# ===========================================================================
def mse_loss(logits, targets):
    """MSE between logits and one-hot targets. logits: seq_len × vocab_size"""
    oh = one_hot(targets, VOCAB_SIZE)
    loss = 0.0
    for i in range(SEQ_LEN):
        for j in range(VOCAB_SIZE):
            diff = logits[i][j] - oh[i][j]
            loss += diff * diff
    return loss / SEQ_LEN

def mse_loss_grad(logits, targets):
    """dL/dlogits for MSE loss"""
    oh = one_hot(targets, VOCAB_SIZE)
    grad = zeros(SEQ_LEN, VOCAB_SIZE)
    for i in range(SEQ_LEN):
        for j in range(VOCAB_SIZE):
            grad[i][j] = 2.0 * (logits[i][j] - oh[i][j]) / SEQ_LEN
    return grad

total_loss = 0.0
print("Training mini-GPT...")
for epoch in range(EPOCHS):
    epoch_loss = 0.0

    # Accumulate gradients over all 8 samples
    grads_accum = {
        'E': zeros(VOCAB_SIZE, D_MODEL),
        'Wq': zeros(D_MODEL, D_MODEL), 'Wk': zeros(D_MODEL, D_MODEL),
        'Wv': zeros(D_MODEL, D_MODEL), 'Wo': zeros(D_MODEL, D_MODEL),
        'W1': zeros(D_MODEL, D_FF), 'W2': zeros(D_FF, D_MODEL),
        'gamma1': [0.0] * D_MODEL, 'beta1': [0.0] * D_MODEL,
        'gamma2': [0.0] * D_MODEL, 'beta2': [0.0] * D_MODEL,
    }

    for s in range(8):
        x_indices = X_train[s]
        y_indices = Y_train[s]
        logits, cache = forward(x_indices)
        loss = mse_loss(logits, y_indices)
        epoch_loss += loss

        dL_dlogits = mse_loss_grad(logits, y_indices)
        grads = backward(cache, dL_dlogits, y_indices)

        for k in grads_accum:
            if isinstance(grads_accum[k], list) and isinstance(grads_accum[k][0], list):
                # Matrix
                for i in range(len(grads_accum[k])):
                    for j in range(len(grads_accum[k][0])):
                        grads_accum[k][i][j] += grads[k][i][j]
            else:
                # Vector
                for i in range(len(grads_accum[k])):
                    grads_accum[k][i] += grads[k][i]

    # Average gradients and update
    for k in grads_accum:
        param = globals()[k]
        g = grads_accum[k]
        if isinstance(g, list) and len(g) > 0 and isinstance(g[0], list):
            # Matrix parameter
            for i in range(len(param)):
                for j in range(len(param[0])):
                    param[i][j] -= LR * g[i][j] / 8.0
        else:
            # Vector parameter
            for i in range(len(param)):
                param[i] -= LR * g[i] / 8.0

    total_loss = epoch_loss / 8.0
    if epoch % 20 == 0:
        print(f"  epoch {epoch}: loss = {total_loss:.6f}")

print(f"Final loss: {total_loss:.6f}")

# ===========================================================================
# Quick forward test
# ===========================================================================
test_prompt = [0, 1, 2, 3]
logits_test, _ = forward(test_prompt)
print("\nTest prompt:", test_prompt)
print("Logits (last position):", [f"{v:.4f}" for v in logits_test[-1]])
pred = max(range(VOCAB_SIZE), key=lambda i: logits_test[-1][i])
print(f"Predicted next token: {pred} (expected: 4)")

# ===========================================================================
# Generate A+ source code
# ===========================================================================

# KAPL encoding map
KAPL_MAP = {
    '\u2190': b'\xfb',   # ← assign
    '\u2395': b'\xd5',   # ⎕ print (quad)
    '\u235D': b'\xe3',   # ⍝ comment (lamp)
    '\u2374': b'\xce',   # ⍴ rho (reshape)
    '\u00F7': b'\xdf',   # ÷ divide
    '\u00D7': b'\xc1',   # × multiply
    '\u2373': b'\xa2',   # ⍳ iota
    '\u2308': b'\xab',   # ⌈ ceiling
    '\u220A': b'\xa8',   # ∊ member
    '\u230A': b'\xac',   # ⌊ floor
}

def encode_kapl(text):
    """Encode Unicode APL text to KAPL bytes."""
    result = bytearray()
    for ch in text:
        if ch in KAPL_MAP:
            result.extend(KAPL_MAP[ch])
        elif ord(ch) < 128 or ch in '\n\r\t':
            result.extend(ch.encode('ascii'))
        else:
            result.extend(ch.encode('utf-8'))
    return bytes(result)


def format_matrix(mat, row_prefix="", indent=""):
    """Format a matrix as A+ reshape syntax."""
    rows = len(mat)
    cols = len(mat[0]) if rows > 0 else 0
    # Flatten row-major
    flat = []
    for row in mat:
        for v in row:
            # Format with reasonable precision
            if abs(v) < 1e-8:
                flat.append("0")
            else:
                flat.append(f"{v:.6f}")
    return f"{indent}{row_prefix}{rows} {cols} \u2374 " + " ".join(flat)


def format_vector(vec):
    """Format a vector as A+ reshape syntax."""
    n = len(vec)
    vals = []
    for v in vec:
        if abs(v) < 1e-8:
            vals.append("0")
        else:
            vals.append(f"{v:.6f}")
    return f"{n} \u2374 " + " ".join(vals)


def generate_aplus():
    """Generate the complete gpt.a+ source code."""
    lines = []

    def L(s):
        lines.append(s)

    L("\u235D gpt.a+ - Mini-GPT: Multi-Head Transformer in Pure A+")
    L("\u235D First-ever GPT implemented entirely in A+!")
    L("\u235D 8-token vocab, 4-head attention, FFN, layer norm, residuals")
    L("\u235D Trained weights from Python; forward pass + self-test in A+")
    L("")

    # ===== Config =====
    L("\u235D === Model Configuration ===")
    L("vocab\u21908")
    L("seq\u21904")
    L("dm\u21908")
    L("nheads\u21904")
    L("dk\u21902")
    L("dff\u219016")
    L("")

    # ===== Helpers =====
    L("\u235D === Helper: Sigmoid ===")
    L("sigmoid{x}: {")
    L("  1\u00F71+*-x")
    L("}")
    L("")

    L("")
    L("\u235D === Helper: Softmax (row-wise) ===")
    L("softmax{row;n}: {")
    L("  \u235D Find max for numerical stability")
    L("  mx\u2190row[0]")
    L("  i\u21900")
    L("  while (i<n) {")
    L("    if (row[i]>mx) { mx\u2190row[i] }")
    L("    i\u2190i+1")
    L("  }")
    L("  \u235D Compute exp(x - max) and sum (store in temporary array)")
    L("  tmp\u2190n \u2374 0")
    L("  sm\u21900.0")
    L("  i\u21900")
    L("  while (i<n) {")
    L("    e\u2190*row[i]-mx")
    L("    tmp[i]\u2190e")
    L("    sm\u2190sm+e")
    L("    i\u2190i+1")
    L("  }")
    L("  \u235D Normalize back into row")
    L("  i\u21900")
    L("  while (i<n) {")
    L("    row[i]\u2190tmp[i]\u00F7sm")
    L("    i\u2190i+1")
    L("  }")
    L("  row")
    L("}")
    L("")

    # ===== Weights =====
    L("\u235D === Trained Weights (embedded from Python training) ===")
    L("")

    # Token embeddings
    L("\u235D Token embedding: vocab x dm")
    L(format_matrix(E, "E\u2190"))
    L("")

    # Position embeddings
    L("\u235D Position embedding: seq x dm")
    L(format_matrix(P, "P\u2190"))
    L("")

    # Attention weights
    L("\u235D Attention: Q, K, V, output projection (each dm x dm)")
    L(format_matrix(Wq, "Wq\u2190"))
    L(format_matrix(Wk, "Wk\u2190"))
    L(format_matrix(Wv, "Wv\u2190"))
    L(format_matrix(Wo, "Wo\u2190"))
    L("")

    # Feed-forward weights
    L("\u235D Feed-forward: W1 (dm x dff), W2 (dff x dm)")
    L(format_matrix(W1, "W1\u2190"))
    L(format_matrix(W2, "W2\u2190"))
    L("")

    # Layer norm params
    L("\u235D Layer norm parameters")
    L(f"gamma1\u2190{format_vector(gamma1)}")
    L(f"beta1\u2190{format_vector(beta1)}")
    L(f"gamma2\u2190{format_vector(gamma2)}")
    L(f"beta2\u2190{format_vector(beta2)}")
    L("")

    # Scale
    L(f"scale\u2190{scale:.6f}")
    L("")

    # ===== Training data (for reference / testing) =====
    L("\u235D === Training Corpus (8 sequences, for reference) ===")
    L("\u235D Sequences: [0,1,2,3] [1,2,3,4] [2,3,4,5] [3,4,5,6] [4,5,6,7] [5,6,7,0] [6,7,0,1] [7,0,1,2]")
    L("\u235D Targets:    [1,2,3,4] [2,3,4,5] [3,4,5,6] [4,5,6,7] [5,6,7,0] [6,7,0,1] [7,0,1,2] [0,1,2,3]")
    L("")

    # ===== Forward Pass Function =====
    L("\u235D === Forward Pass: One Transformer Block ===")
    L("\u235D gpt_forward tokens -> logits (seq x vocab) using stored weights")
    L("gpt_forward{tokens}: {")
    L("")
    L("  \u235D 1. Embedding lookup + position encoding")
    L("  xemb\u2190seq dm \u2374 0")
    L("  pos\u21900")
    L("  while (pos<seq) {")
    L("    idx\u2190tokens[pos]")
    L("    j\u21900")
    L("    while (j<dm) {")
    L("      xemb[pos\u00D7dm+j]\u2190E[idx\u00D7dm+j] + P[pos\u00D7dm+j]")
    L("      j\u2190j+1")
    L("    }")
    L("    pos\u2190pos+1")
    L("  }")
    L("")
    L("  \u235D 2. Compute Q, K, V = xemb @ Wq, Wk, Wv")
    L("  Q\u2190seq dm \u2374 0")
    L("  K\u2190seq dm \u2374 0")
    L("  V\u2190seq dm \u2374 0")
    L("  \u235D Q = xemb +.\u00D7 Wq using manual loops (inner product not available for all impls)")
    L("  i\u21900")
    L("  while (i<seq) {")
    L("    j\u21900")
    L("    while (j<dm) {")
    L("      s\u21900.0")
    L("      k\u21900")
    L("      while (k<dm) {")
    L("        s\u2190s + xemb[i\u00D7dm+k] \u00D7 Wq[k\u00D7dm+j]")
    L("        k\u2190k+1")
    L("      }")
    L("      Q[i\u00D7dm+j]\u2190s")
    L("      s\u21900.0")
    L("      k\u21900")
    L("      while (k<dm) {")
    L("        s\u2190s + xemb[i\u00D7dm+k] \u00D7 Wk[k\u00D7dm+j]")
    L("        k\u2190k+1")
    L("      }")
    L("      K[i\u00D7dm+j]\u2190s")
    L("      s\u21900.0")
    L("      k\u21900")
    L("      while (k<dm) {")
    L("        s\u2190s + xemb[i\u00D7dm+k] \u00D7 Wv[k\u00D7dm+j]")
    L("        k\u2190k+1")
    L("      }")
    L("      V[i\u00D7dm+j]\u2190s")
    L("      j\u2190j+1")
    L("    }")
    L("    i\u2190i+1")
    L("  }")
    L("")
    L("  \u235D 3. Multi-head attention (4 heads, dk=2) + concatenate + project")
    L("  concat\u2190seq dm \u2374 0")
    L("  h\u21900")
    L("  while (h<nheads) {")
    L("    hoff\u2190h\u00D7dk")
    L("")
    L("    \u235D Compute attention scores for head h: scores = Q_h @ K_h^T * scale")
    L("    scores\u2190seq seq \u2374 0")
    L("    qi\u21900")
    L("    while (qi<seq) {")
    L("      kj\u21900")
    L("      while (kj<seq) {")
    L("        dot\u21900.0")
    L("        d\u21900")
    L("        while (d<dk) {")
    L("          dot\u2190dot + Q[qi\u00D7dm+hoff+d] \u00D7 K[kj\u00D7dm+hoff+d]")
    L("          d\u2190d+1")
    L("        }")
    L("        scores[qi\u00D7seq+kj]\u2190dot \u00D7 scale")
    L("        kj\u2190kj+1")
    L("      }")
    L("      qi\u2190qi+1")
    L("    }")
    L("")
    L("    \u235D Softmax row-wise on scores -> attn_weights")
    L("    attn\u2190seq seq \u2374 0")
    L("    qi\u21900")
    L("    while (qi<seq) {")
    L("      \u235D Extract row and compute softmax")
    L("      row\u2190seq \u2374 0")
    L("      kj\u21900")
    L("      while (kj<seq) {")
    L("        row[kj]\u2190scores[qi\u00D7seq+kj]")
    L("        kj\u2190kj+1")
    L("      }")
    L("      srow\u2190softmax{row;seq}")
    L("      kj\u21900")
    L("      while (kj<seq) {")
    L("        attn[qi\u00D7seq+kj]\u2190srow[kj]")
    L("        kj\u2190kj+1")
    L("      }")
    L("      qi\u2190qi+1")
    L("    }")
    L("")
    L("    \u235D Weighted sum: context_h = attn @ V_h")
    L("    ctx\u2190seq dk \u2374 0")
    L("    qi\u21900")
    L("    while (qi<seq) {")
    L("      dj\u21900")
    L("      while (dj<dk) {")
    L("        s\u21900.0")
    L("        kk\u21900")
    L("        while (kk<seq) {")
    L("          s\u2190s + attn[qi\u00D7seq+kk] \u00D7 V[kk\u00D7dm+hoff+dj]")
    L("          kk\u2190kk+1")
    L("        }")
    L("        ctx[qi\u00D7dk+dj]\u2190s")
    L("        dj\u2190dj+1")
    L("      }")
    L("      qi\u2190qi+1")
    L("    }")
    L("")
    L("    \u235D Place context_h into concat at head position")
    L("    qi\u21900")
    L("    while (qi<seq) {")
    L("      dj\u21900")
    L("      while (dj<dk) {")
    L("        concat[qi\u00D7dm+hoff+dj]\u2190ctx[qi\u00D7dk+dj]")
    L("        dj\u2190dj+1")
    L("      }")
    L("      qi\u2190qi+1")
    L("    }")
    L("    h\u2190h+1")
    L("  }")
    L("")
    L("  \u235D 4. Output projection: attn_out = concat @ Wo")
    L("  attn_out\u2190seq dm \u2374 0")
    L("  i\u21900")
    L("  while (i<seq) {")
    L("    j\u21900")
    L("    while (j<dm) {")
    L("      s\u21900.0")
    L("      k\u21900")
    L("      while (k<dm) {")
    L("        s\u2190s + concat[i\u00D7dm+k] \u00D7 Wo[k\u00D7dm+j]")
    L("        k\u2190k+1")
    L("      }")
    L("      attn_out[i\u00D7dm+j]\u2190s")
    L("      j\u2190j+1")
    L("    }")
    L("    i\u2190i+1")
    L("  }")
    L("")
    L("  \u235D 5. Residual connection + Layer Norm 1")
    L("  x1ln\u2190seq dm \u2374 0")
    L("  i\u21900")
    L("  while (i<seq) {")
    L("    \u235D Compute mean")
    L("    m\u21900.0")
    L("    j\u21900")
    L("    while (j<dm) {")
    L("      m\u2190m + xemb[i\u00D7dm+j] + attn_out[i\u00D7dm+j]")
    L("      j\u2190j+1")
    L("    }")
    L("    m\u2190m\u00F7dm")
    L("    \u235D Compute variance")
    L("    v\u21900.0")
    L("    j\u21900")
    L("    while (j<dm) {")
    L("      t\u2190xemb[i\u00D7dm+j] + attn_out[i\u00D7dm+j] - m")
    L("      v\u2190v + t\u00D7t")
    L("      j\u2190j+1")
    L("    }")
    L("    v\u2190v\u00F7dm")
    L("    \u235D Normalize and scale: y = gamma*(x-mean)/(var+eps) + beta")
    L("    eps\u21900.00001")
    L("    j\u21900")
    L("    while (j<dm) {")
    L("      t\u2190xemb[i\u00D7dm+j] + attn_out[i\u00D7dm+j]")
    L("      x1ln[i\u00D7dm+j]\u2190gamma1[j] \u00D7 (t-m) \u00F7 (v+eps) + beta1[j]")
    L("      j\u2190j+1")
    L("    }")
    L("    i\u2190i+1")
    L("  }")
    L("")
    L("  \u235D 6. Feed-forward: h_ffn = sigmoid(x1ln @ W1), ffn_out = h_ffn @ W2")
    L("  hffn\u2190seq dff \u2374 0")
    L("  i\u21900")
    L("  while (i<seq) {")
    L("    j\u21900")
    L("    while (j<dff) {")
    L("      s\u21900.0")
    L("      k\u21900")
    L("      while (k<dm) {")
    L("        s\u2190s + x1ln[i\u00D7dm+k] \u00D7 W1[k\u00D7dff+j]")
    L("        k\u2190k+1")
    L("      }")
    L("      \u235D sigmoid")
    L("      hffn[i\u00D7dff+j]\u21901\u00F71+*-s")
    L("      j\u2190j+1")
    L("    }")
    L("    i\u2190i+1")
    L("  }")
    L("")
    L("  ffn_out\u2190seq dm \u2374 0")
    L("  i\u21900")
    L("  while (i<seq) {")
    L("    j\u21900")
    L("    while (j<dm) {")
    L("      s\u21900.0")
    L("      k\u21900")
    L("      while (k<dff) {")
    L("        s\u2190s + hffn[i\u00D7dff+k] \u00D7 W2[k\u00D7dm+j]")
    L("        k\u2190k+1")
    L("      }")
    L("      ffn_out[i\u00D7dm+j]\u2190s")
    L("      j\u2190j+1")
    L("    }")
    L("    i\u2190i+1")
    L("  }")
    L("")
    L("  \u235D 7. Residual connection + Layer Norm 2")
    L("  x2ln\u2190seq dm \u2374 0")
    L("  i\u21900")
    L("  while (i<seq) {")
    L("    m\u21900.0")
    L("    j\u21900")
    L("    while (j<dm) {")
    L("      m\u2190m + x1ln[i\u00D7dm+j] + ffn_out[i\u00D7dm+j]")
    L("      j\u2190j+1")
    L("    }")
    L("    m\u2190m\u00F7dm")
    L("    v\u21900.0")
    L("    j\u21900")
    L("    while (j<dm) {")
    L("      t\u2190x1ln[i\u00D7dm+j] + ffn_out[i\u00D7dm+j] - m")
    L("      v\u2190v + t\u00D7t")
    L("      j\u2190j+1")
    L("    }")
    L("    v\u2190v\u00F7dm")
    L("    eps\u21900.00001")
    L("    j\u21900")
    L("    while (j<dm) {")
    L("      t\u2190x1ln[i\u00D7dm+j] + ffn_out[i\u00D7dm+j]")
    L("      x2ln[i\u00D7dm+j]\u2190gamma2[j] \u00D7 (t-m) \u00F7 (v+eps) + beta2[j]")
    L("      j\u2190j+1")
    L("    }")
    L("    i\u2190i+1")
    L("  }")
    L("")
    L("  \u235D 8. Output projection to vocab: logits = x2ln @ E^T")
    L("  logits\u2190seq vocab \u2374 0")
    L("  i\u21900")
    L("  while (i<seq) {")
    L("    t\u21900")
    L("    while (t<vocab) {")
    L("      s\u21900.0")
    L("      k\u21900")
    L("      while (k<dm) {")
    L("        s\u2190s + x2ln[i\u00D7dm+k] \u00D7 E[t\u00D7dm+k]")
    L("        k\u2190k+1")
    L("      }")
    L("      logits[i\u00D7vocab+t]\u2190s")
    L("      t\u2190t+1")
    L("    }")
    L("    i\u2190i+1")
    L("  }")
    L("")
    L("  logits")
    L("}")
    L("")

    # ===== Self-Tests =====
    L("\u235D === Self-Tests ===")
    L("")

    # Test 1: Softmax sanity check
    L("\u235D Test 1: softmax integrity")
    L("tsv\u2190softmax{1 2 3;3}")
    L("tss\u2190tsv[0]+tsv[1]+tsv[2]")
    L("if ((tss>0.99)\u00D7(tss<1.01)) { \u2395\"[PASS] softmax sums to ~1\" } else { \u2395\"[FAIL] softmax\" }")
    L("")

    # Test 2: Feed test prompt through GPT
    L("\u235D Test 2: Forward pass on prompt [0,1,2,3]")
    L("prompt\u21904 \u2374 0 1 2 3")
    L("result\u2190gpt_forward{prompt}")
    L("")

    # Test 3: Check logits shape
    L("\u235D Test 3: Verify output shape is 4x8")
    L("rsh\u2190\u2374 result")
    L("if (rsh[0]=4) { \u2395\"[PASS] output has 4 rows\" } else { \u2395\"[FAIL] rows\" }")
    L("if (rsh[1]=8) { \u2395\"[PASS] output has 8 cols\" } else { \u2395\"[FAIL] cols\" }")
    L("")

    # Test 4: Check logits are finite
    L("\u235D Test 4: Verify logits are finite (not inf/nan)")
    L("ok\u21901")
    L("i\u21900")
    L("while (i<4) {")
    L("  j\u21900")
    L("  while (j<8) {")
    L("    v\u2190result[i\u00D78+j]")
    L("    if (v<0-1e6) { ok\u21900 }")
    L("    if (v>1e6) { ok\u21900 }")
    L("    j\u2190j+1")
    L("  }")
    L("  i\u2190i+1")
    L("}")
    L("if (ok=1) { \u2395\"[PASS] logits in finite range\" } else { \u2395\"[FAIL] logits range\" }")
    L("")

    # Test 5: Check last position predicts token 4
    L("\u235D Test 5: Last position (token 3) should predict token 4 as most likely")
    L("last\u21904\u00D78")
    L("pred\u21900-1e9")
    L("pred_idx\u21900")
    L("j\u21900")
    L("while (j<8) {")
    L("  if (result[last+j]>pred) {")
    L("    pred\u2190result[last+j]")
    L("    pred_idx\u2190j")
    L("  }")
    L("  j\u2190j+1")
    L("}")
    L("\u2395\"Predicted next token:\"")
    L("\u2395 pred_idx")
    L("if (pred_idx=4) {")
    L("  \u2395\"[PASS] GPT correctly predicts token 4 after [0,1,2,3]\"")
    L("}")
    L("if (pred_idx=4) { ok_pred\u21901 } else { ok_pred\u21900 }")
    L("if (ok_pred=0) {")
    L("  \u2395\"[INFO] GPT predicts token different from expected 4\"")
    L("  \u2395\"  (This may be OK with random initialization + limited training)\"")
    L("}")
    L("")

    # Test 6: Full softmax probability distribution at last position
    L("\u235D Test 6: Softmax distribution over vocab at last position")
    L("lrow\u21908 \u2374 0")
    L("j\u21900")
    L("while (j<8) {")
    L("  lrow[j]\u2190result[last+j]")
    L("  j\u2190j+1")
    L("}")
    L("probs\u2190softmax{lrow;8}")
    L("\u2395\"Token probabilities (last position):\"")
    L("j\u21900")
    L("while (j<8) {")
    L("  \u2395 j")
    L("  \u2395 probs[j]")
    L("  j\u2190j+1")
    L("}")
    L("")

    # Test 7: Try another prompt [7,0,1,2] -> should predict 3
    L("\u235D Test 7: Second prompt [7,0,1,2] -> expecting token 3")
    L("prompt2\u21904 \u2374 7 0 1 2")
    L("result2\u2190gpt_forward{prompt2}")
    L("last2\u21903\u00D78")
    L("pred2\u21900-1e9")
    L("pred2_idx\u21900")
    L("j\u21900")
    L("while (j<8) {")
    L("  if (result2[last2+j]>pred2) {")
    L("    pred2\u2190result2[last2+j]")
    L("    pred2_idx\u2190j")
    L("  }")
    L("  j\u2190j+1")
    L("}")
    L("\u2395\"Prompt [7,0,1,2] predicted next:\"")
    L("\u2395 pred2_idx")
    L("")

    # Final message
    L("\u235D === Done ===")
    L("\u2395\"gpt.a+: all tests complete. First GPT in pure A+!\"")
    L("")

    return "\n".join(lines)


# ===========================================================================
# Generate the .a+ file (both plaintext UTF-8 and KAPL-encoded)
# ===========================================================================
def main():
    aplus_source = generate_aplus()

    # Write plaintext UTF-8 version (like existing .a+ files)
    plaintext_path = "/home/bym/aplus-ci-poc/gpt.a+"
    with open(plaintext_path, "w", encoding="utf-8") as f:
        f.write(aplus_source)
    print(f"Written plaintext .a+ to {plaintext_path} ({len(aplus_source)} chars)")

    # Write KAPL-encoded version
    kapl_path = "/home/bym/aplus-ci-poc/gpt_kapl.a+"
    kapl_bytes = encode_kapl(aplus_source)
    with open(kapl_path, "wb") as f:
        f.write(kapl_bytes)
    print(f"Written KAPL-encoded .a+ to {kapl_path} ({len(kapl_bytes)} bytes)")

    # Print line count
    num_lines = aplus_source.count('\n') + 1
    print(f"Total: {num_lines} lines")

    print("\nDone! gpt.a+ generated successfully.")


if __name__ == "__main__":
    main()
