// zillers_native: C++ kernels for hot quant paths (plain C ABI, loaded via ctypes).
//
// Every function here has a pure-Python reference implementation in core/quant/
// that remains the source of truth and the automatic fallback. Results must match
// the reference (see tests/test_native_kernels.py).
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <vector>

namespace {

// ---------------------------------------------------------------------------
// MT19937 identical to CPython's random.Random(seed) (init_by_array seeding), so
// the Monte Carlo shuffles reproduce Python's random.shuffle bit for bit.
// ---------------------------------------------------------------------------
class PyMT19937 {
public:
    explicit PyMT19937(const std::vector<uint32_t>& key) { init_by_array(key); }

    uint32_t next_u32() {
        if (index_ >= N) generate();
        uint32_t y = mt_[index_++];
        y ^= (y >> 11);
        y ^= (y << 7) & 0x9d2c5680UL;
        y ^= (y << 15) & 0xefc60000UL;
        y ^= (y >> 18);
        return y;
    }

    // CPython: getrandbits(k) for 1 <= k <= 32
    uint32_t getrandbits(int k) { return next_u32() >> (32 - k); }

    // CPython: Random._randbelow_with_getrandbits(n), n >= 1
    uint32_t randbelow(uint32_t n) {
        int k = 0;
        for (uint32_t t = n; t; t >>= 1) ++k;  // n.bit_length()
        uint32_t r = getrandbits(k);
        while (r >= n) r = getrandbits(k);
        return r;
    }

    // CPython: random.shuffle(x)
    void shuffle(std::vector<double>& x) {
        for (size_t i = x.size(); i-- > 1;) {
            uint32_t j = randbelow(static_cast<uint32_t>(i + 1));
            std::swap(x[i], x[j]);
        }
    }

private:
    static constexpr int N = 624;
    static constexpr int M = 397;
    uint32_t mt_[N];
    int index_ = N;

    void init_genrand(uint32_t s) {
        mt_[0] = s;
        for (int i = 1; i < N; ++i)
            mt_[i] = 1812433253UL * (mt_[i - 1] ^ (mt_[i - 1] >> 30)) + static_cast<uint32_t>(i);
        index_ = N;
    }

    void init_by_array(const std::vector<uint32_t>& key) {
        init_genrand(19650218UL);
        size_t i = 1, j = 0;
        size_t klen = key.size();
        for (size_t k = std::max<size_t>(N, klen); k; --k) {
            mt_[i] = (mt_[i] ^ ((mt_[i - 1] ^ (mt_[i - 1] >> 30)) * 1664525UL)) + key[j] + static_cast<uint32_t>(j);
            ++i;
            ++j;
            if (i >= static_cast<size_t>(N)) {
                mt_[0] = mt_[N - 1];
                i = 1;
            }
            if (j >= klen) j = 0;
        }
        for (size_t k = N - 1; k; --k) {
            mt_[i] = (mt_[i] ^ ((mt_[i - 1] ^ (mt_[i - 1] >> 30)) * 1566083941UL)) - static_cast<uint32_t>(i);
            ++i;
            if (i >= static_cast<size_t>(N)) {
                mt_[0] = mt_[N - 1];
                i = 1;
            }
        }
        mt_[0] = 0x80000000UL;
        index_ = N;
    }

    void generate() {
        static const uint32_t mag01[2] = {0x0UL, 0x9908b0dfUL};
        int kk;
        uint32_t y;
        for (kk = 0; kk < N - M; ++kk) {
            y = (mt_[kk] & 0x80000000UL) | (mt_[kk + 1] & 0x7fffffffUL);
            mt_[kk] = mt_[kk + M] ^ (y >> 1) ^ mag01[y & 1UL];
        }
        for (; kk < N - 1; ++kk) {
            y = (mt_[kk] & 0x80000000UL) | (mt_[kk + 1] & 0x7fffffffUL);
            mt_[kk] = mt_[kk + (M - N)] ^ (y >> 1) ^ mag01[y & 1UL];
        }
        y = (mt_[N - 1] & 0x80000000UL) | (mt_[0] & 0x7fffffffUL);
        mt_[N - 1] = mt_[M - 1] ^ (y >> 1) ^ mag01[y & 1UL];
        index_ = 0;
    }
};

}  // namespace

#if defined(_WIN32)
#define ZN_EXPORT extern "C" __declspec(dllexport)
#else
#define ZN_EXPORT extern "C" __attribute__((visibility("default")))
#endif

// Mirrors core.quant.stage8_validate.run_monte_carlo_drawdown (seed is not None).
// Returns NaN on invalid input (caller falls back to the Python implementation).
static double monte_carlo_drawdown_impl(const std::vector<double>& pnls, int iterations, double confidence,
                                        double initial_equity, uint64_t seed) {
    if (pnls.empty()) return 0.0;
    std::vector<uint32_t> key;
    key.push_back(static_cast<uint32_t>(seed & 0xFFFFFFFFULL));
    if (seed >> 32) key.push_back(static_cast<uint32_t>(seed >> 32));
    PyMT19937 rng(key);

    std::vector<double> shuffled = pnls;
    std::vector<double> max_dds;
    max_dds.reserve(iterations > 0 ? iterations : 0);

    for (int it = 0; it < iterations; ++it) {
        shuffled = pnls;
        rng.shuffle(shuffled);
        double equity = initial_equity;
        double peak = equity;
        double max_dd = 0.0;
        for (double pnl : shuffled) {
            equity += pnl;
            if (equity > peak) peak = equity;
            if (peak > 1e-12) {
                double dd = (peak - equity) / peak;
                if (dd > max_dd) max_dd = dd;
            }
        }
        max_dds.push_back(max_dd);
    }
    if (max_dds.empty()) return std::numeric_limits<double>::quiet_NaN();
    std::sort(max_dds.begin(), max_dds.end());
    size_t idx = static_cast<size_t>(confidence * static_cast<double>(max_dds.size()));
    idx = std::min(idx, max_dds.size() - 1);
    return max_dds[idx];
}

// Mirrors core.quant.stage3_filter.compute_hurst_exponent.
static double hurst_impl(const double* series, size_t n) {
    if (n < 50) return 0.5;

    std::vector<size_t> lags;
    size_t upper = std::min<size_t>(n / 2, 100);
    for (size_t lag = 10; lag < upper; lag += 5) lags.push_back(lag);
    if (lags.size() < 3) return 0.5;

    std::vector<double> log_lags, log_rs;
    for (size_t lag : lags) {
        double rs_sum = 0.0;
        size_t rs_cnt = 0;
        for (size_t i = 0; i + lag <= n; i += lag) {
            double sum = 0.0;
            for (size_t k = 0; k < lag; ++k) sum += series[i + k];
            const double mean_sub = sum / static_cast<double>(lag);
            double cur = 0.0, cmax = -std::numeric_limits<double>::infinity(),
                   cmin = std::numeric_limits<double>::infinity(), sq = 0.0;
            for (size_t k = 0; k < lag; ++k) {
                double d = series[i + k] - mean_sub;
                cur += d;
                if (cur > cmax) cmax = cur;
                if (cur < cmin) cmin = cur;
                sq += d * d;
            }
            const double s_val = std::sqrt(sq / static_cast<double>(lag));
            if (s_val > 1e-12) {
                rs_sum += (cmax - cmin) / s_val;
                ++rs_cnt;
            }
        }
        if (rs_cnt) {
            const double avg_rs = rs_sum / static_cast<double>(rs_cnt);
            if (avg_rs > 0.0) {
                log_lags.push_back(std::log(static_cast<double>(lag)));
                log_rs.push_back(std::log(avg_rs));
            }
        }
    }
    if (log_lags.size() < 2) return 0.5;

    double mean_x = 0.0, mean_y = 0.0;
    for (size_t i = 0; i < log_lags.size(); ++i) {
        mean_x += log_lags[i];
        mean_y += log_rs[i];
    }
    mean_x /= static_cast<double>(log_lags.size());
    mean_y /= static_cast<double>(log_lags.size());
    double ss_xx = 0.0, ss_xy = 0.0;
    for (size_t i = 0; i < log_lags.size(); ++i) {
        ss_xx += (log_lags[i] - mean_x) * (log_lags[i] - mean_x);
        ss_xy += (log_lags[i] - mean_x) * (log_rs[i] - mean_y);
    }
    if (ss_xx <= 1e-12) return 0.5;
    return std::max(0.0, std::min(1.0, ss_xy / ss_xx));
}

ZN_EXPORT double zn_monte_carlo_drawdown(const double* pnls, int n, int iterations, double confidence,
                                         double initial_equity, uint64_t seed) {
    if (n < 0 || (n > 0 && pnls == nullptr)) return std::numeric_limits<double>::quiet_NaN();
    std::vector<double> v(pnls, pnls + n);
    return monte_carlo_drawdown_impl(v, iterations, confidence, initial_equity, seed);
}

ZN_EXPORT double zn_hurst_exponent(const double* series, int n) {
    if (n < 0 || (n > 0 && series == nullptr)) return std::numeric_limits<double>::quiet_NaN();
    return hurst_impl(series, static_cast<size_t>(n));
}

ZN_EXPORT int zn_abi_version() { return 1; }
