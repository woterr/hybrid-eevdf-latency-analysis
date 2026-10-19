#!/usr/bin/env bash
# Phase 1: Automated Statistical Validation Script
# Runs N iterations of Exp A (Floating) vs Exp B (E-Core Pool) under P-core load,
# captures schbench percentiles, and compiles a clean comparative summary.

set -u

if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run as root (sudo ./run_phase1_validation.sh)"
    exit 1
fi

ITERATIONS=10
DURATION=15
WARMUP=5
BATCH_DIR="phase1_validation_results_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BATCH_DIR/exp_a" "$BATCH_DIR/exp_b"

SCHBENCH_BIN="./schbench"
if [ ! -x "$SCHBENCH_BIN" ]; then
    if command -v schbench &>/dev/null; then
        SCHBENCH_BIN="schbench"
    else
        echo "Error: schbench binary not found in current directory or PATH."
        exit 1
    fi
fi

echo "========================================================"
echo " STARTING PHASE 1 STATISTICAL VALIDATION ($ITERATIONS RUNS)"
echo "========================================================"

for i in $(seq 1 "$ITERATIONS"); do
    echo "--- Progress: Iteration $i / $ITERATIONS ---"

    # --- EXPERIMENT A: Floating (0-17) ---
    echo "    [+] Spawning background sysbench on P-cores (0-11)..."
    taskset -c 0-11 sysbench cpu --threads=12 --cpu-max-prime=50000000 run >/dev/null 2>&1 &
    SYS_PID=$!
    sleep "$WARMUP"

    echo "    [+] Running Exp A (Floating 0-17)..."
    taskset -c 0-17 "$SCHBENCH_BIN" -m 2 -t 4 -r "$DURATION" -s 1000000 > "$BATCH_DIR/exp_a/run_$i.log" 2>&1

    kill -9 "$SYS_PID" 2>/dev/null || true
    wait "$SYS_PID" 2>/dev/null || true
    sleep 2 # Cooldown

    # --- EXPERIMENT B: E-Core Pool Only (12-17) ---
    echo "    [+] Spawning background sysbench on P-cores (0-11)..."
    taskset -c 0-11 sysbench cpu --threads=12 --cpu-max-prime=50000000 run >/dev/null 2>&1 &
    SYS_PID=$!
    sleep "$WARMUP"

    echo "    [+] Running Exp B (E-Core Pool 12-17)..."
    taskset -c 12-17 "$SCHBENCH_BIN" -m 2 -t 4 -r "$DURATION" -s 1000000 > "$BATCH_DIR/exp_b/run_$i.log" 2>&1

    kill -9 "$SYS_PID" 2>/dev/null || true
    wait "$SYS_PID" 2>/dev/null || true
    sleep 2 # Cooldown
done

echo "========================================================"
echo " PARSING RESULTS & GENERATING SUMMARY TABLE"
echo "========================================================"

SUMMARY_FILE="$BATCH_DIR/STATISTICAL_SUMMARY.txt"
{
    echo "=========================================================================================="
    echo "                 PHASE 1 STATISTICAL VALIDATION SUMMARY ($ITERATIONS RUNS)                 "
    echo "=========================================================================================="
    printf "%-10s | %-28s | %-28s\n" "Run ID" "Exp A (Floating 0-17) [us]" "Exp B (E-Pool 12-17) [us]"
    printf "%s\n" "------------------------------------------------------------------------------------------"
} > "$SUMMARY_FILE"

for i in $(seq 1 "$ITERATIONS"); do
    # Extract final 99.9th percentile line from each log file
    p999_a=$(grep "99.9th:" "$BATCH_DIR/exp_a/run_$i.log" | tail -n 1 | awk '{print $2}')
    p999_b=$(grep "99.9th:" "$BATCH_DIR/exp_b/run_$i.log" | tail -n 1 | awk '{print $2}')
    
    line=$(printf "Run %-6s | p99.9: %-20s | p99.9: %-20s" "$i" "${p999_a:-N/A}" "${p999_b:-N/A}")
    echo "    $line"
    printf "%-10s | p99.9: %-20s | p99.9: %-20s\n" "Run $i" "${p999_a:-N/A}" "${p999_b:-N/A}" >> "$SUMMARY_FILE"
done

{
    echo "=========================================================================================="
    echo "Validation Complete. Compare Exp A tail spikes against Exp B to prove statistical variance."
} >> "$SUMMARY_FILE"

echo "========================================================"
echo " Batch complete! Results saved in directory: $BATCH_DIR"
echo " Summary report generated at: $SUMMARY_FILE"
echo "========================================================"