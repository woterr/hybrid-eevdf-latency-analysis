#!/usr/bin/env bash
# Phase 1.1: Microsecond State Reconstruction via sched_switch Tracing
# Captures sched_switch, sched_wakeup, and sched_migrate_task to verify runqueue state during tail latency spikes.

set -u

if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run as root (sudo ./run_phase1_1_sched_switch.sh)"
    exit 1
fi

SCHBENCH_BIN="./schbench"
if [ ! -x "$SCHBENCH_BIN" ]; then
    if command -v schbench &>/dev/null; then
        SCHBENCH_BIN="schbench"
    else
        echo "Error: schbench binary not found in current directory or PATH."
        exit 1
    fi
fi

DURATION=30
WARMUP=10
OUT_DIR="phase1_1_results_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUT_DIR"

echo "========================================================"
echo " 1. CONFIGURING HARDWARE STATES & GOVERNORS"
echo "========================================================"
if command -v cpupower &>/dev/null; then
    cpupower frequency-set -g performance >/dev/null 2>&1 || true
fi
echo 0 > /proc/sys/kernel/nmi_watchdog 2>/dev/null || true
echo -1 > /proc/sys/kernel/perf_event_paranoid 2>/dev/null || true

echo "========================================================"
echo " 2. RUNNING EXP A (FLOATING 0-17) WITH SCHED_SWITCH TRACING"
echo "========================================================"

echo "    [+] Spawning sysbench on P-cores (0-11)..."
taskset -c 0-11 sysbench cpu --threads=12 --cpu-max-prime=50000000 run >/dev/null 2>&1 &
SYS_PID=$!

echo "    [+] Warming up for ${WARMUP}s..."
sleep "$WARMUP"

echo "    [+] Starting comprehensive perf record (sched_switch, sched_wakeup, sched_migrate_task)..."
perf record -e sched:sched_switch,sched:sched_wakeup,sched:sched_migrate_task \
            -a -o "$OUT_DIR/perf_switch.data" -- sleep "$DURATION" >/dev/null 2>&1 &
PERF_PID=$!

echo "    [+] Running schbench across hybrid domain (0-17)..."
taskset -c 0-17 "$SCHBENCH_BIN" -m 2 -t 4 -r "$DURATION" -s 1000000 > "$OUT_DIR/schbench.log" 2>&1

wait "$PERF_PID" 2>/dev/null || true

if [ -n "$SYS_PID" ]; then
    kill -9 "$SYS_PID" 2>/dev/null || true
    wait "$SYS_PID" 2>/dev/null || true
fi

echo "    [+] Exporting raw perf text stream (this may take a few seconds)..."
perf script -i "$OUT_DIR/perf_switch.data" > "$OUT_DIR/perf_switch_events.raw" 2>/dev/null

echo "========================================================"
echo " 3. GENERATING OUTLIER STATE RECONSTRUCTION REPORT"
echo "========================================================"

REPORT_FILE="$OUT_DIR/OUTLIER_STATE_ANALYSIS.txt"

{
    echo "=========================================================================================="
    echo "                     PHASE 1.1 SCHED_SWITCH OUTLIER ANALYSIS REPORT                       "
    echo "=========================================================================================="
    echo "Schbench Log Summary (Wakeup Latencies):"
    grep -A 6 "Wakeup Latencies" "$OUT_DIR/schbench.log" | tail -n 10
    echo "------------------------------------------------------------------------------------------"
    echo "Checking core occupancy around schbench thread wakeups..."
} > "$REPORT_FILE"

echo "Phase 1.1 capture complete! Results and raw traces stored in: $OUT_DIR"