#!/usr/bin/env bash
# run_stress.sh — MCP Guardian v3 压力测试执行脚本
# 用法：
#   ./run_stress.sh              # 全量运行
#   ./run_stress.sh concurrent   # 只跑并发测试
#   ./run_stress.sh bench        # 只跑性能基准
#   ./run_stress.sh fast         # 跳过慢测试（< 5s 完成）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEST_FILE="${PROJECT_ROOT}/tests/test_stress_v3.py"
RESULTS_DIR="${PROJECT_ROOT}/tests/results"
PYTHON="${PROJECT_ROOT}/.venv/bin/python"
if [ ! -x "${PYTHON}" ]; then
  PYTHON="$(command -v python3 || command -v python)"
fi
PYTEST_ARGS=()
if "${PYTHON}" -c "import pytest_timeout" >/dev/null 2>&1; then
  PYTEST_ARGS+=(--timeout=30)
fi
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT="${RESULTS_DIR}/stress_${TIMESTAMP}.txt"

mkdir -p "${RESULTS_DIR}"

# ── 依赖检查 ──────────────────────────────────────────────────────────────────
echo "=== 依赖检查 ==="
"${PYTHON}" -c "import pytest, pytest_asyncio; print(f'pytest {pytest.__version__}, pytest-asyncio {pytest_asyncio.__version__}')" \
  || { echo "❌ 缺少依赖：${PYTHON} -m pip install pytest pytest-asyncio pytest-timeout"; exit 1; }

# ── 参数解析 ──────────────────────────────────────────────────────────────────
MODE="${1:-all}"
case "${MODE}" in
  concurrent)
    FILTER="-k TestConcurrentLock"
    LABEL="并发竞态测试"
    ;;
  circuit)
    FILTER="-k TestCircuitBreakerStress"
    LABEL="熔断器压力测试"
    ;;
  budget)
    FILTER="-k TestBudgetEnforcement"
    LABEL="预算边界测试"
    ;;
  bash)
    FILTER="-k TestBashValidatorCorpus"
    LABEL="Bash validator 语料测试"
    ;;
  sig)
    FILTER="-k TestSignatureDistinctness"
    LABEL="签名区分度测试"
    ;;
  persist)
    FILTER="-k TestPersistStress"
    LABEL="持久化并发测试"
    ;;
  bench)
    FILTER="-k TestPerformanceBenchmark"
    LABEL="性能基准测试"
    ;;
  regression)
    FILTER="-k TestRegressionGuard"
    LABEL="I1-I9 回归保护"
    ;;
  fast)
    FILTER="-k 'not (high_concurrency_stress or stress_random_inputs or rapid_flush)'"
    LABEL="快速测试集（跳过慢测试）"
    ;;
  all|*)
    FILTER=""
    LABEL="全量压力测试"
    ;;
esac

echo ""
echo "=== MCP Guardian v3 压力测试 ==="
echo "模式：${LABEL}"
echo "报告：${REPORT}"
echo ""

# ── 执行 ──────────────────────────────────────────────────────────────────────
cd "${PROJECT_ROOT}"

"${PYTHON}" -m pytest "${TEST_FILE}" \
  ${FILTER} \
  -v \
  --tb=short \
  "${PYTEST_ARGS[@]}" \
  -p no:warnings \
  --durations=15 \
  --asyncio-mode=auto \
  -s \
  2>&1 | tee "${REPORT}"

EXIT_CODE=${PIPESTATUS[0]}

# ── 统计摘要 ──────────────────────────────────────────────────────────────────
echo ""
echo "=== 测试摘要 ==="
grep -E "^(PASSED|FAILED|ERROR|tests/)" "${REPORT}" | tail -5 || true
grep -E "passed|failed|error" "${REPORT}" | tail -3 || true

if [ "${EXIT_CODE}" -eq 0 ]; then
  echo ""
  echo "✅ 全部通过  报告已保存：${REPORT}"
else
  echo ""
  echo "❌ 有测试失败  详情：${REPORT}"
  # 打印失败列表
  echo ""
  echo "--- 失败测试 ---"
  grep "^FAILED" "${REPORT}" || true
fi

exit "${EXIT_CODE}"
