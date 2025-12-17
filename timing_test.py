"""
NF1 TIMING TEST - CV Processing Speed
Requirement: System shall process CV parsing within 10 seconds per document
"""

import os
import sys
import time
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'investtalent.settings')
django.setup()

from recruitment.models import Candidate, Resume
from recruitment.scoring import analyze_resume

def run_timing_test():
    """Test CV processing time for all candidates with resumes."""
    
    print("=" * 60)
    print("NF1 TIMING TEST - CV Processing Speed")
    print("Requirement: Process CV within 10 seconds per document")
    print("=" * 60)
    print()
    
    # Get all candidates with resumes
    candidates = Candidate.objects.filter(resume__isnull=False)
    
    if not candidates.exists():
        print("ERROR: No candidates with resumes found!")
        print("Please upload at least one CV first.")
        return
    
    results = []
    total_time = 0
    passed = 0
    failed = 0
    
    print(f"Testing {candidates.count()} candidate(s)...\n")
    print("-" * 60)
    
    for candidate in candidates:
        try:
            # Get resume text
            resume = candidate.resume
            if not resume.parsed_text:
                print(f"SKIP: {candidate.name} - No parsed text")
                continue
            
            # Time the analysis
            start_time = time.time()
            analyze_resume(candidate, job_posting=None, use_ml=True)
            end_time = time.time()
            
            processing_time = end_time - start_time
            total_time += processing_time
            
            # Check pass/fail
            status = "PASS" if processing_time < 10 else "FAIL"
            if status == "PASS":
                passed += 1
            else:
                failed += 1
            
            results.append({
                'name': candidate.name,
                'time': processing_time,
                'status': status
            })
            
            print(f"{status}: {candidate.name[:30]:<30} - {processing_time:.2f}s")
            
        except Exception as e:
            print(f"ERROR: {candidate.name} - {str(e)}")
            failed += 1
    
    # Summary
    print("-" * 60)
    print()
    print("=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    
    total_tests = passed + failed
    if total_tests > 0:
        avg_time = total_time / len(results) if results else 0
        pass_rate = (passed / total_tests) * 100
        
        print(f"Total CVs Tested:    {total_tests}")
        print(f"Passed (<10s):       {passed}")
        print(f"Failed (>=10s):      {failed}")
        print(f"Pass Rate:           {pass_rate:.1f}%")
        print(f"Average Time:        {avg_time:.2f}s")
        print(f"Total Time:          {total_time:.2f}s")
        print()
        
        if pass_rate == 100:
            print("OVERALL RESULT: PASS ✓")
            print("NF1 Requirement SATISFIED")
        else:
            print("OVERALL RESULT: FAIL ✗")
            print("NF1 Requirement NOT SATISFIED")
    else:
        print("No tests completed.")
    
    print("=" * 60)
    
    # Return results for documentation
    return {
        'total_tests': total_tests,
        'passed': passed,
        'failed': failed,
        'pass_rate': pass_rate if total_tests > 0 else 0,
        'avg_time': avg_time if results else 0,
        'results': results
    }

if __name__ == "__main__":
    run_timing_test()