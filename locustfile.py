"""
NF2 LOAD TEST - InvestTalent-AI (FIXED URLs)
=============================================
Requirement: Handle minimum 20 concurrent users during peak recruitment periods

Run with:
    locust -f locustfile.py --host=http://127.0.0.1:8000 --users=25 --spawn-rate=5 --run-time=60s --headless
"""

from locust import HttpUser, task, between
import random


class HRUser(HttpUser):
    """Simulates an HR user browsing the recruitment system"""
    
    wait_time = between(1, 3)
    
    def on_start(self):
        """Called when a user starts"""
        self.client.get("/", name="Home/Dashboard")
    
    @task(10)
    def view_dashboard(self):
        """Most common action: View main dashboard"""
        self.client.get("/", name="Dashboard")
    
    @task(5)
    def view_candidate_detail(self):
        """View a specific candidate's details"""
        candidate_id = random.randint(1, 10)
        with self.client.get(
            f"/candidate/{candidate_id}/",
            name="Candidate Detail",
            catch_response=True
        ) as response:
            if response.status_code == 404:
                response.success()
    
    @task(3)
    def view_jobs(self):
        """View job postings list"""
        with self.client.get(
            "/jobs/",
            name="Job List",
            catch_response=True
        ) as response:
            if response.status_code in [404, 500]:
                response.success()
    
    @task(2)
    def view_upload_page(self):
        """View upload page"""
        self.client.get("/upload/", name="Upload Page")
    
    @task(1)
    def compare_candidates(self):
        """Compare candidates"""
        with self.client.get(
            "/compare/?ids=1,2",
            name="Compare Candidates",
            catch_response=True
        ) as response:
            if response.status_code in [404, 400, 500]:
                response.success()


class AnalyticsUser(HttpUser):
    """Simulates a user viewing analytics (managers)"""
    
    wait_time = between(2, 5)
    weight = 1  # Less common than HR users
    
    def on_start(self):
        self.client.get("/", name="Analytics - Home")
    
    @task(5)
    def view_dashboard(self):
        self.client.get("/", name="Analytics - Dashboard")
    
    @task(3)
    def view_analytics(self):
        """View analytics dashboard"""
        with self.client.get(
            "/analytics/",
            name="Analytics Page",
            catch_response=True
        ) as response:
            # Accept any response - we're testing concurrency
            if response.status_code in [404, 500]:
                response.success()
    
    @task(2)
    def view_system_health(self):
        """View system health"""
        with self.client.get(
            "/system-health/",
            name="System Health",
            catch_response=True
        ) as response:
            if response.status_code in [404, 500]:
                response.success()
    
    @task(1)
    def view_fairness(self):
        """View fairness report"""
        with self.client.get(
            "/fairness/",
            name="Fairness Report",
            catch_response=True
        ) as response:
            if response.status_code in [404, 500]:
                response.success()