// bench_gpu.cpp — Standalone GFLOPS benchmark: naive vs GPU-accelerated
//
// Compares naive scalar implementations against the OpenMP+SIMD routines
// in libaplus_gpu.so for:
//   - Matrix multiply (100×100, 500×500)
//   - Sigmoid over large vectors
//
// Build:  make -f Makefile.gpu bench
// Run:    LD_LIBRARY_PATH=. ./bench_gpu

#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <chrono>
#include <cstring>

#ifdef _OPENMP
#include <omp.h>
#endif

// ─── libaplus_gpu routines (C linkage) ──────────────────────────────────────

extern "C" {
    void matmul_f32(const float* A, const float* B, float* C, int M, int N, int K);
    void sigmoid_vec(const float* x, float* out, int n);
}

// ─── Naive reference implementations ─────────────────────────────────────────

static void matmul_naive(
    const float* A, const float* B, float* C,
    int M, int N, int K)
{
    std::memset(C, 0, M * N * sizeof(float));
    for (int i = 0; i < M; ++i)
        for (int j = 0; j < N; ++j)
            for (int k = 0; k < K; ++k)
                C[i * N + j] += A[i * K + k] * B[k * N + j];
}

static void sigmoid_naive(const float* x, float* out, int n) {
    for (int i = 0; i < n; ++i) {
        float v = x[i];
        if (v >= 0.0f)
            out[i] = 1.0f / (1.0f + std::exp(-v));
        else {
            float ex = std::exp(v);
            out[i] = ex / (1.0f + ex);
        }
    }
}

// ─── Timer helper ────────────────────────────────────────────────────────────

using Clock = std::chrono::high_resolution_clock;
using Ms    = std::chrono::duration<double, std::milli>;

// ─── Matrix helpers ──────────────────────────────────────────────────────────

static void fill_rand(float* p, int n) {
    for (int i = 0; i < n; ++i)
        p[i] = (float)rand() / (float)RAND_MAX - 0.5f;
}

static bool allclose(const float* a, const float* b, int n, float tol = 1e-3f) {
    for (int i = 0; i < n; ++i)
        if (std::fabs(a[i] - b[i]) > tol) return false;
    return true;
}

// ─── Benchmark runner ────────────────────────────────────────────────────────

static void bench_matmul(const char* label, int M, int N, int K, int trials)
{
    printf("\n─── %s (%d×%d × %d×%d) ───\n", label, M, K, K, N);

    int sizeA = M * K, sizeB = K * N, sizeC = M * N;
    float *A = new float[sizeA];
    float *B = new float[sizeB];
    float *C_naive = new float[sizeC];
    float *C_accel = new float[sizeC];

    fill_rand(A, sizeA);
    fill_rand(B, sizeB);

    // Naive
    auto t0 = Clock::now();
    for (int t = 0; t < trials; ++t)
        matmul_naive(A, B, C_naive, M, N, K);
    double ms_naive = Ms(Clock::now() - t0).count() / trials;

    // Accelerated
    auto t1 = Clock::now();
    for (int t = 0; t < trials; ++t)
        matmul_f32(A, B, C_accel, M, N, K);
    double ms_accel = Ms(Clock::now() - t1).count() / trials;

    // Correctness
    bool ok = allclose(C_naive, C_accel, sizeC);

    // GFLOPS  (2*M*N*K ops per multiply)
    double ops = 2.0 * M * N * K;
    double gflops_naive = ops / (ms_naive / 1000.0) / 1e9;
    double gflops_accel = ops / (ms_accel / 1000.0) / 1e9;
    double speedup = ms_naive / ms_accel;

    printf("  Naive:      %8.2f ms  (%7.2f GFLOPS)\n", ms_naive, gflops_naive);
    printf("  Accelerated:%8.2f ms  (%7.2f GFLOPS)\n", ms_accel, gflops_accel);
    printf("  Speedup:    %8.2f×\n", speedup);
    printf("  Correctness: %s\n", ok ? "✓ PASS" : "✗ FAIL");

    delete[] A; delete[] B; delete[] C_naive; delete[] C_accel;
}

static void bench_sigmoid(int n, int trials)
{
    printf("\n─── Sigmoid (size=%d) ───\n", n);

    float *x  = new float[n];
    float *y1 = new float[n];
    float *y2 = new float[n];

    fill_rand(x, n);

    // Naive
    auto t0 = Clock::now();
    for (int t = 0; t < trials; ++t)
        sigmoid_naive(x, y1, n);
    double ms_naive = Ms(Clock::now() - t0).count() / trials;

    // Accelerated
    auto t1 = Clock::now();
    for (int t = 0; t < trials; ++t)
        sigmoid_vec(x, y2, n);
    double ms_accel = Ms(Clock::now() - t1).count() / trials;

    bool ok = allclose(y1, y2, n);
    double speedup = ms_naive / ms_accel;

    printf("  Naive:      %8.2f ms\n", ms_naive);
    printf("  Accelerated:%8.2f ms\n", ms_accel);
    printf("  Speedup:    %8.2f×\n", speedup);
    printf("  Correctness: %s\n", ok ? "✓ PASS" : "✗ FAIL");

    delete[] x; delete[] y1; delete[] y2;
}

// ─── main ────────────────────────────────────────────────────────────────────

int main() {
#ifdef _OPENMP
    printf("OpenMP enabled — %d threads\n", omp_get_max_threads());
#else
    printf("OpenMP NOT enabled\n");
#endif
    printf("==========================================\n");
    printf("  A+ GPU Backend — GFLOPS Benchmark\n");
    printf("==========================================\n");

    bench_matmul("MatMul f32", 100, 100, 100, 20);
    bench_matmul("MatMul f32", 500, 500, 500, 5);
    bench_sigmoid(1'000'000, 50);

    printf("\nDone.\n");
    return 0;
}
