from django.contrib import admin
from .models import Candidate, Resume, Education, Experience, Skill, Score
from .workflow import WorkflowEvent

@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'email', 'status', 'years_experience', 
        'get_score', 'ip_address', 'created_at'
    ]
    list_filter = ['status', 'created_at', 'is_verified']
    search_fields = ['name', 'email', 'current_position', 'ip_address']
    list_per_page = 25
    readonly_fields = ['created_at', 'updated_at', 'ip_address', 'file_hash', 'security_flags']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'email', 'phone', 'status')
        }),
        ('Professional Details', {
            'fields': ('current_position', 'years_experience')
        }),
        ('Security & Audit', {
            'fields': ('ip_address', 'file_hash', 'is_verified', 'security_flags'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_score(self, obj):
        if hasattr(obj, 'score'):
            return f"{obj.score.total_score}/100"
        return "Not scored"
    get_score.short_description = 'Score'
    get_score.admin_order_field = 'score__total_score'


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'file_type', 'uploaded_at', 'get_text_preview']
    list_filter = ['file_type', 'uploaded_at']
    search_fields = ['candidate__name', 'parsed_text']
    readonly_fields = ['uploaded_at', 'parsed_text']
    
    def get_text_preview(self, obj):
        if obj.parsed_text:
            return obj.parsed_text[:100] + "..."
        return "No text"
    get_text_preview.short_description = 'Preview'


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = [
        'candidate', 'degree', 'field_of_study', 
        'institution', 'graduation_year', 'has_islamic_finance_cert'
    ]
    list_filter = ['degree', 'has_islamic_finance_cert', 'graduation_year']
    search_fields = ['candidate__name', 'institution', 'field_of_study']


@admin.register(Experience)
class ExperienceAdmin(admin.ModelAdmin):
    list_display = [
        'candidate', 'position', 'company', 
        'start_date', 'is_current', 'is_islamic_finance'
    ]
    list_filter = ['is_current', 'is_islamic_finance', 'start_date']
    search_fields = ['candidate__name', 'company', 'position']


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'skill_name', 'category', 'proficiency_level']
    list_filter = ['category', 'proficiency_level']
    search_fields = ['candidate__name', 'skill_name']


@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = [
        'candidate', 'total_score', 'education_score', 
        'experience_score', 'skills_score', 'islamic_finance_score', 'rank'
    ]
    list_filter = ['rank', 'evaluated_at']
    search_fields = ['candidate__name']
    readonly_fields = ['evaluated_at']
    ordering = ['-total_score']


@admin.register(WorkflowEvent)
class WorkflowEventAdmin(admin.ModelAdmin):
    list_display = [
        'candidate', 'event_type', 'old_status', 
        'new_status', 'created_by', 'created_at'
    ]
    list_filter = ['event_type', 'new_status', 'created_at']
    search_fields = ['candidate__name', 'notes', 'created_by']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
    
    fieldsets = (
        ('Event Information', {
            'fields': ('candidate', 'event_type', 'old_status', 'new_status')
        }),
        ('Details', {
            'fields': ('notes', 'created_by', 'created_at')
        }),
    )