// gpu_backend.cpp — GPU-accelerated backend: libaplus_gpu.so
// Provides OpenMP-parallel matrix multiply, SIMD sigmoid, and vector ops
// for A+ programs via C-linkage FFI.
//
// Build: make -f Makefile.gpu

#include <cstddef>
#include <cmath>
#include <cstring>
#include <algorithm>

#ifdef _OPENMP
#include <omp.h>
#endif

// ─── Internal helpers ────────────────────────────────────────────────────────

static inline float sigmoid_f32(float x) {
    // Numerically stable sigmoid: 1/(1+exp(-x))
    if (x >= 0.0f) {
        return 1.0f / (1.0f + std::exp(-x));
    } else {
        float ex = std::exp(x);
        return ex / (1.0f + ex);
    }
}

static inline double sigmoid_f64(double x) {
    if (x >= 0.0) {
        return 1.0 / (1.0 + std::exp(-x));
    } else {
        double ex = std::exp(x);
        return ex / (1.0 + ex);
    }
}

// ─── Matrix multiply (single precision, OpenMP) ────────────────────────────
//
// C = A * B   —   all stored row-major
// A: M x K, B: K x N, C: M x N
//
extern "C" void matmul_f32(
    const float* A, const float* B, float* C,
    int M, int N, int K)
{
    // Zero output
    std::memset(C, 0, M * N * sizeof(float));

#ifdef _OPENMP
    #pragma omp parallel for collapse(2) schedule(static)
#endif
    for (int i = 0; i < M; ++i) {
        for (int j = 0; j < N; ++j) {
            float sum = 0.0f;
            // Vectorized inner loop — compiler auto-vectorizes
            #pragma omp simd reduction(+:sum)
            for (int k = 0; k < K; ++k) {
                sum += A[i * K + k] * B[k * N + j];
            }
            C[i * N + j] = sum;
        }
    }
}

// ─── Matrix multiply (double precision, OpenMP + SIMD hints) ───────────────
//
extern "C" void matmul_omp(
    const double* A, const double* B, double* C,
    int M, int N, int K)
{
    std::memset(C, 0, M * N * sizeof(double));

#ifdef _OPENMP
    #pragma omp parallel for collapse(2) schedule(static)
#endif
    for (int i = 0; i < M; ++i) {
        for (int j = 0; j < N; ++j) {
            double sum = 0.0;
            #pragma omp simd reduction(+:sum)
            for (int k = 0; k < K; ++k) {
                sum += A[i * K + k] * B[k * N + j];
            }
            C[i * N + j] = sum;
        }
    }
}

// ─── Vector add: out[i] = a[i] + b[i]  (all lengths = n) ──────────────────
//
extern "C" void vec_add(
    const float* a, const float* b, float* out, int n)
{
#ifdef _OPENMP
    #pragma omp parallel for simd schedule(static)
#endif
    for (int i = 0; i < n; ++i) {
        out[i] = a[i] + b[i];
    }
}

// ─── Vector scale: out[i] = alpha * x[i]  ──────────────────────────────────
//
extern "C" void vec_scale(
    const float* x, float alpha, float* out, int n)
{
#ifdef _OPENMP
    #pragma omp parallel for simd schedule(static)
#endif
    for (int i = 0; i < n; ++i) {
        out[i] = alpha * x[i];
    }
}

// ─── Sigmoid (vectorized, single precision) ─────────────────────────────────
//
extern "C" void sigmoid_vec(
    const float* x, float* out, int n)
{
#ifdef _OPENMP
    #pragma omp parallel for simd schedule(static)
#endif
    for (int i = 0; i < n; ++i) {
        out[i] = sigmoid_f32(x[i]);
    }
}
