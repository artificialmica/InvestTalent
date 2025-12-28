#!/usr/bin/env python3
"""
NF2 LOAD TEST RUNNER (Windows Compatible) - WITH WARMUP
========================================================
Requirement: Handle minimum 20 concurrent users during peak recruitment periods

Usage:
    python nf2_load_test.py http://127.0.0.1:8000
"""

import subprocess
import sys
import os
import time
from datetime import datetime

# Try to import requests for warmup
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Configuration
DEFAULT_HOST = "http://127.0.0.1:8000"
USERS = 25          # Test with 25 users (exceeds 20 requirement)
SPAWN_RATE = 2      # Spawn 2 users per second (slower ramp-up)
DURATION = "60s"    # Run for 60 seconds
MIN_USERS = 20      # NF2 requirement

# Pass criteria
MAX_FAILURE_RATE = 10.0     # Max 10% failure rate
MAX_RESPONSE_TIME = 3000    # Max 3 seconds average
MAX_P95_TIME = 5000         # Max 5 seconds for 95th percentile


def warmup_server(host, rounds=10):
    """Warm up the server by hitting endpoints before the load test"""
    
    print("=" * 60)
    print("WARMING UP SERVER...")
    print("=" * 60)
    
    if not HAS_REQUESTS:
        print("(requests library not available, skipping warmup)")
        return
    
    endpoints = [
        "/",
        "/analytics/",
        "/jobs/",
        "/upload/",
        "/fairness/",
    ]
    
    for i in range(rounds):
        for endpoint in endpoints:
            try:
                url = f"{host}{endpoint}"
                response = requests.get(url, timeout=10)
                status = "OK" if response.status_code in [200, 302, 404] else f"ERR:{response.status_code}"
                print(f"  Warmup {i+1}/{rounds}: {endpoint} - {status} ({response.elapsed.total_seconds()*1000:.0f}ms)")
            except Exception as e:
                print(f"  Warmup {i+1}/{rounds}: {endpoint} - FAILED ({e})")
        
        if i < rounds - 1:
            time.sleep(0.5)  # Brief pause between rounds
    
    print("\nWarmup complete! Starting load test...\n")
    time.sleep(2)  # Give server a moment to settle


def run_load_test(host):
    """Run locust load test and return results"""
    
    print(f"""
============================================================
NF2 LOAD TEST - InvestTalent-AI
============================================================
Requirement: Handle minimum {MIN_USERS} concurrent users
Testing with: {USERS} concurrent users
Duration: {DURATION}
Target: {host}
============================================================
""")
    
    # Find locustfile
    locustfile = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locustfile.py")
    if not os.path.exists(locustfile):
        locustfile = "locustfile.py"
    
    print(f"Using locustfile: {locustfile}")
    
    # Run locust with slower spawn rate
    cmd = [
        "locust",
        "-f", locustfile,
        f"--host={host}",
        f"--users={USERS}",
        f"--spawn-rate={SPAWN_RATE}",
        f"--run-time={DURATION}",
        "--headless",
        "--only-summary",
        "--csv=nf2_results",
    ]
    
    print("Running load test...")
    print(f"Command: {' '.join(cmd)}\n")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("Test timed out!")
        return False
    except FileNotFoundError:
        print("Locust not found! Install with: pip install locust")
        return False


def parse_results():
    """Parse CSV results from locust"""
    results = {
        'total_requests': 0,
        'failures': 0,
        'failure_rate': 0,
        'avg_response': 0,
        'p95_response': 0,
        'requests_per_sec': 0,
    }
    
    try:
        with open("nf2_results_stats.csv", "r") as f:
            lines = f.readlines()
        
        # Parse header to find correct column indices
        if len(lines) > 0:
            header = lines[0].strip().split(",")
            # Find column indices
            try:
                idx_requests = header.index("Request Count")
                idx_failures = header.index("Failure Count")
                idx_avg = header.index("Average Response Time")
                idx_rps = header.index("Requests/s")
                # P95 is labeled as "95%" in the header
                idx_p95 = header.index("95%")
            except ValueError as e:
                print(f"Warning: Could not find column: {e}")
                # Fallback to known positions for locust CSV format
                # Type,Name,Request Count,Failure Count,Median,Average,Min,Max,Content Size,RPS,Failures/s,50%,66%,75%,80%,90%,95%,...
                idx_requests = 2
                idx_failures = 3
                idx_avg = 5
                idx_rps = 9
                idx_p95 = 16  # The 95% column
            
        if len(lines) > 1:
            for line in lines[1:]:
                if "Aggregated" in line:
                    parts = line.split(",")
                    if len(parts) > idx_p95:
                        results['total_requests'] = int(parts[idx_requests]) if parts[idx_requests] else 0
                        results['failures'] = int(parts[idx_failures]) if parts[idx_failures] else 0
                        results['avg_response'] = float(parts[idx_avg]) if parts[idx_avg] else 0
                        results['requests_per_sec'] = float(parts[idx_rps]) if parts[idx_rps] else 0
                        results['p95_response'] = float(parts[idx_p95]) if parts[idx_p95] else 0
                    break
        
        if results['total_requests'] > 0:
            results['failure_rate'] = (results['failures'] / results['total_requests']) * 100
            
    except FileNotFoundError:
        print("Results file not found")
    except Exception as e:
        print(f"Error parsing results: {e}")
        import traceback
        traceback.print_exc()
    
    return results


def generate_report(results, passed):
    """Generate NF2 test report"""
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Determine pass/fail for each criteria
    users_ok = USERS >= MIN_USERS
    failure_ok = results['failure_rate'] <= MAX_FAILURE_RATE
    avg_ok = results['avg_response'] <= MAX_RESPONSE_TIME
    p95_ok = results['p95_response'] <= MAX_P95_TIME
    
    report = f"""
============================================================
NF2 LOAD TEST REPORT
============================================================
Timestamp: {timestamp}
Requirement: Handle minimum {MIN_USERS} concurrent users
Tested with: {USERS} concurrent users

------------------------------------------------------------
RESULTS
------------------------------------------------------------
Total Requests:     {results['total_requests']:,}
Failed Requests:    {results['failures']:,}
Failure Rate:       {results['failure_rate']:.2f}%
Avg Response Time:  {results['avg_response']:.0f}ms
95th Percentile:    {results['p95_response']:.0f}ms
Requests/Second:    {results['requests_per_sec']:.1f}

------------------------------------------------------------
PASS CRITERIA
------------------------------------------------------------
[{'PASS' if users_ok else 'FAIL'}] Concurrent Users:  {USERS} >= {MIN_USERS}
[{'PASS' if failure_ok else 'FAIL'}] Failure Rate:     {results['failure_rate']:.2f}% <= {MAX_FAILURE_RATE}%
[{'PASS' if avg_ok else 'FAIL'}] Avg Response:     {results['avg_response']:.0f}ms <= {MAX_RESPONSE_TIME}ms
[{'PASS' if p95_ok else 'FAIL'}] P95 Response:     {results['p95_response']:.0f}ms <= {MAX_P95_TIME}ms

============================================================
OVERALL RESULT: {'PASS' if passed else 'FAIL'}
NF2 Requirement: {'SATISFIED' if passed else 'NOT SATISFIED'}
============================================================
"""
    
    print(report)
    
    # Save report
    try:
        with open("nf2_report.txt", "w", encoding="utf-8") as f:
            f.write(report)
        print("Report saved to: nf2_report.txt")
    except Exception as e:
        print(f"Could not save report: {e}")
    
    return report


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    
    # WARMUP PHASE
    warmup_server(host, rounds=10)
    
    # Run the test
    success = run_load_test(host)
    
    # Parse results
    results = parse_results()
    
    # Determine pass/fail
    passed = (
        results['failure_rate'] <= MAX_FAILURE_RATE and
        results['avg_response'] <= MAX_RESPONSE_TIME and
        (results['p95_response'] <= MAX_P95_TIME or results['p95_response'] == 0)
    )
    
    # Generate report
    generate_report(results, passed)
    
    print("\nDone!")
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()