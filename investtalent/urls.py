from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from recruitment import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # Main pages
    path('', views.upload_resume, name='upload_resume'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('candidate/<int:pk>/', views.candidate_detail, name='candidate_detail'),
    
    # Analytics & Reports
    path('analytics/', views.analytics_dashboard, name='analytics_dashboard'),
    path('fairness/', views.fairness_report, name='fairness_report'),
    path('system-health/', views.system_health, name='system_health'),
    path('export-report/', views.export_analytics_report, name='export_report'),
    
    # Actions
    path('candidate/<int:pk>/update-status/', views.update_candidate_status, name='update_status'),
    
    # API Endpoints
    path('api/analytics/', views.api_analytics_summary, name='api_analytics'),
    path('api/fairness/', views.api_fairness_report, name='api_fairness'),
    path('api/workflow/', views.api_workflow_report, name='api_workflow'),
    path('api/health/', views.api_system_health, name='api_health'),
    path('api/candidate/<int:pk>/timeline/', views.api_candidate_timeline, name='api_timeline'),
    path('debug/<int:pk>/', views.debug_resume, name='debug_resume'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)