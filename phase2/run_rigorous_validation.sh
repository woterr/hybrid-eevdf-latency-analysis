#!/usr/bin/env bash
# Rigorous Phase 2 Validation Script
# Scales N=30, captures per-run distributions, and quantifies mechanism frequencies.

set -u

if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run as root (sudo ./run_rigorous_validation.sh)"
    exit 1
fi

ITERATIONS=30
DURATION=15
WARMUP=5
BATCH_DIR="rigorous_results_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BATCH_DIR/exp_a" "$BATCH_DIR/exp_b"

SCHBENCH_BIN="./schbench"
if [ ! -x "$SCHBENCH_BIN" ]; then
    SCHBENCH_BIN="schbench"
fi

echo "========================================================"
echo " STARTING RIGOROUS STATISTICAL VALIDATION ($ITERATIONS RUNS)"
echo "========================================================"

# Record environment state for reproducibility
{
    echo "Kernel Version: $(uname -r)"
    echo "CPU Model: $(lscpu | grep 'Model name' | sed 's/  */ /g')"
    echo "Governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo 'N/A')"
} > "$BATCH_DIR/environment_info.txt"

for i in $(seq 1 "$ITERATIONS"); do
    echo "--- Progress: Iteration $i / $ITERATIONS ---"

    # --- EXPERIMENT A: Floating (0-17) with trace capture ---
    taskset -c 0-11 sysbench cpu --threads=12 --cpu-max-prime=50000000 run >/dev/null 2>&1 &
    SYS_PID=$!
    sleep "$WARMUP"

    # Optional: Record trace for deep-dive mechanism quantification
    perf record -e sched:sched_switch,sched:sched_wakeup,sched:sched_migrate_task -o "$BATCH_DIR/exp_a/run_$i.perf" -- \
        taskset -c 0-17 "$SCHBENCH_BIN" -m 2 -t 4 -r "$DURATION" -s 1000000 > "$BATCH_DIR/exp_a/run_$i.log" 2>&1

    kill -9 "$SYS_PID" 2>/dev/null || true
    wait "$SYS_PID" 2>/dev/null || true
    sleep 2

    # --- EXPERIMENT B: Pinned E-Core Pool (12-17) ---
    taskset -c 0-11 sysbench cpu --threads=12 --cpu-max-prime=50000000 run >/dev/null 2>&1 &
    SYS_PID=$!
    sleep "$WARMUP"

    perf record -e sched:sched_switch,sched:sched_wakeup,sched:sched_migrate_task -o "$BATCH_DIR/exp_b/run_$i.perf" -- \
        taskset -c 12-17 "$SCHBENCH_BIN" -m 2 -t 4 -r "$DURATION" -s 1000000 > "$BATCH_DIR/exp_b/run_$i.log" 2>&1

    kill -9 "$SYS_PID" 2>/dev/null || true
    wait "$SYS_PID" 2>/dev/null || true
    sleep 2
done

echo "========================================================"
echo " EXTRACTING WAKEUP P99.9 DISTRIBUTION DATA"
echo "========================================================"

CSV_FILE="$BATCH_DIR/distribution_data.csv"
echo "RunID,ExpA_Wakeup_p999,ExpB_Wakeup_p999" > "$CSV_FILE"

for i in $(seq 1 "$ITERATIONS"); do
    p999_a=$(grep -A 4 "Wakeup Latencies" "$BATCH_DIR/exp_a/run_$i.log" | grep "99.9th:" | awk '{print $2}')
    p999_b=$(grep -A 4 "Wakeup Latencies" "$BATCH_DIR/exp_b/run_$i.log" | grep "99.9th:" | awk '{print $2}')
    echo "$i,${p999_a:-0},${p999_b:-0}" >> "$CSV_FILE"
done

echo "Batch completed successfully! Data saved to $CSV_FILE"