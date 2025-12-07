from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from recruitment import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Main pages
    path('', views.dashboard, name='dashboard'),
    path('upload/', views.upload_resume, name='upload_resume'),
    path('candidate/<int:candidate_id>/', views.candidate_detail, name='candidate_detail'),
    
    # Job Postings
    path('jobs/create/', views.create_job_posting, name='create_job_posting'),
    path('jobs/<int:job_id>/', views.job_posting_detail, name='job_posting_detail'),
    path('candidate/<int:candidate_id>/apply/<int:job_id>/', views.apply_candidate_to_job, name='apply_to_job'),
    path('api/skill-variations/', views.skill_variations, name='skill_variations'),
    
    # Analytics & Reports
    path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),
    path('fairness/', views.fairness_report, name='fairness_report'),
    path('system-health/', views.system_health, name='system_health'),
    path('export-report/', views.export_analytics_report, name='export_report'),
    
    # Actions
    path('candidate/<int:candidate_id>/update-status/', views.update_candidate_status, name='update_status'),
    path('compare/', views.compare_candidates, name='compare_candidates'),
    
    # API Endpoints
    path('api/analytics/', views.api_analytics_summary, name='api_analytics'),
    path('api/fairness/', views.api_fairness_report, name='api_fairness'),
    path('api/workflow/', views.api_workflow_report, name='api_workflow'),
    path('api/health/', views.api_system_health, name='api_health'),
    path('api/candidate/<int:candidate_id>/timeline/', views.api_candidate_timeline, name='api_timeline'),
    path('debug/<int:candidate_id>/', views.debug_resume, name='debug_resume'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)