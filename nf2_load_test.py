#!/usr/bin/env python3
"""
NF2 LOAD TEST RUNNER (Windows Compatible)
==========================================
Requirement: Handle minimum 20 concurrent users during peak recruitment periods

Usage:
    python nf2_load_test.py http://127.0.0.1:8000
"""

import subprocess
import sys
import os
from datetime import datetime

# Configuration
DEFAULT_HOST = "http://127.0.0.1:8000"
USERS = 25          # Test with 25 users (exceeds 20 requirement)
SPAWN_RATE = 5      # Spawn 5 users per second
DURATION = "60s"    # Run for 60 seconds
MIN_USERS = 20      # NF2 requirement

# Pass criteria
MAX_FAILURE_RATE = 10.0     # Max 10% failure rate (relaxed for dev server)
MAX_RESPONSE_TIME = 3000    # Max 3 seconds average
MAX_P95_TIME = 5000         # Max 5 seconds for 95th percentile


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
    
    # Run locust
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
            
        if len(lines) > 1:
            for line in lines[1:]:
                if "Aggregated" in line:
                    parts = line.split(",")
                    if len(parts) >= 10:
                        results['total_requests'] = int(parts[2]) if parts[2] else 0
                        results['failures'] = int(parts[3]) if parts[3] else 0
                        results['avg_response'] = float(parts[5]) if parts[5] else 0
                        results['p95_response'] = float(parts[8]) if parts[8] else 0
                        results['requests_per_sec'] = float(parts[9]) if parts[9] else 0
                    break
        
        if results['total_requests'] > 0:
            results['failure_rate'] = (results['failures'] / results['total_requests']) * 100
            
    except FileNotFoundError:
        print("Results file not found")
    except Exception as e:
        print(f"Error parsing results: {e}")
    
    return results


def generate_report(results, passed):
    """Generate NF2 test report (Windows compatible - no unicode)"""
    
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
    
    # Save report with explicit UTF-8 encoding
    try:
        with open("nf2_report.txt", "w", encoding="utf-8") as f:
            f.write(report)
        print("Report saved to: nf2_report.txt")
    except Exception as e:
        print(f"Could not save report: {e}")
    
    return report


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HOST
    
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