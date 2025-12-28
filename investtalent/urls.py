"""
InvestTalent-AI URL Configuration
"""

from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from django.contrib.auth import views as auth_views
from recruitment import views

urlpatterns = [
    # ADMIN
    path('admin/', admin.site.urls),
    
    # AUTHENTICATION (RBAC)
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # MAIN PAGES
    path('', views.dashboard, name='dashboard'),
    path('upload/', views.upload_resume, name='upload_resume'),
    
    # CANDIDATE PAGES
    path('candidates/', views.candidate_list, name='candidate_list'),  # ADDED - was missing!
    path('candidate/<int:pk>/', views.candidate_detail, name='candidate_detail'),
    path('candidate/<int:pk>/update-status/', views.update_candidate_status, name='update_status'),
    path('compare/', views.compare_candidates, name='compare_candidates'),
    
    # JOB POSTINGS
    path('jobs/', views.job_list, name='job_list'),
    path('jobs/create/', views.job_create, name='job_create'),
    path('jobs/<int:job_id>/', views.job_detail, name='job_detail'),
    path('jobs/<int:job_id>/match/', views.job_match, name='job_match'),
    
    # ANALYTICS & REPORTS
    # Both names work - 'analytics' for old templates, 'analytics_dashboard' for new templates
    path('analytics/', views.analytics_dashboard, name='analytics'),
    path('fairness/', views.fairness_report, name='fairness_report'),
    path('system-health/', views.system_health, name='system_health'),
    path('export-report/', views.export_analytics_report, name='export_report'),
    
    # API ENDPOINTS
    path('api/analytics/', views.api_analytics_summary, name='api_analytics'),
    path('api/fairness/', views.api_fairness_report, name='api_fairness'),
    path('api/workflow/', views.api_workflow_report, name='api_workflow'),
    path('api/health/', views.api_system_health, name='api_health'),
    path('api/candidate/<int:pk>/timeline/', views.api_candidate_timeline, name='api_timeline'),
    path('api/candidate/<int:pk>/status/', views.update_candidate_status, name='api_update_status'),
    path('api/skill-variations/', views.skill_variations, name='skill_variations'),
    
    # DEBUG
    path('debug/<int:pk>/', views.debug_resume, name='debug_resume'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)