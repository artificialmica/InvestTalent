from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from recruitment import views
from recruitment import ml_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.dashboard, name='dashboard'),
    path('upload/', views.upload_resume, name='upload_resume'),
    path('candidate/<int:pk>/', views.candidate_detail, name='candidate_detail'),
     path('ml/train/', ml_views.train_ml_model, name='ml_train'),
]

# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)