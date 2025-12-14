from django.contrib import admin
from .models import (
    Candidate, Resume, Education, Experience, Score, 
    WorkflowEvent, SkillType, SkillCategory, SkillDefinition,
    ExtractedSkill, JobRoleProfile, JobPosting, CandidateJobApplication
)


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'status', 'years_experience', 'get_score', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'email']
    list_per_page = 25
    
    def get_score(self, obj):
        if hasattr(obj, 'score'):
            return f"{obj.score.total_score}/100"
        return "Not scored"
    get_score.short_description = 'Score'


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'file_type', 'uploaded_at']
    list_filter = ['file_type']
    search_fields = ['candidate__name']


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'degree', 'institution', 'graduation_year', 'has_islamic_finance_cert']
    list_filter = ['degree', 'has_islamic_finance_cert']
    search_fields = ['candidate__name', 'institution']


@admin.register(Experience)
class ExperienceAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'position', 'company', 'start_date', 'is_current']
    list_filter = ['is_current', 'is_islamic_finance']
    search_fields = ['candidate__name', 'company']


@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'total_score', 'education_score', 'experience_score', 'skills_score', 'islamic_finance_score']
    search_fields = ['candidate__name']
    ordering = ['-total_score']


@admin.register(WorkflowEvent)
class WorkflowEventAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'event_type', 'old_status', 'new_status', 'created_at']
    list_filter = ['event_type', 'new_status']
    search_fields = ['candidate__name']


@admin.register(SkillType)
class SkillTypeAdmin(admin.ModelAdmin):
    list_display = ['name']
    search_fields = ['name']


@admin.register(SkillCategory)
class SkillCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent']
    search_fields = ['name']


@admin.register(SkillDefinition)
class SkillDefinitionAdmin(admin.ModelAdmin):
    list_display = ['canonical_name', 'category', 'is_hard_skill', 'importance_weight']
    list_filter = ['is_hard_skill', 'category']
    search_fields = ['canonical_name']


@admin.register(ExtractedSkill)
class ExtractedSkillAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'skill', 'source_section', 'frequency', 'confidence_score']
    list_filter = ['source_section', 'matched_via']
    search_fields = ['candidate__name', 'skill__canonical_name']


@admin.register(JobRoleProfile)
class JobRoleProfileAdmin(admin.ModelAdmin):
    list_display = ['name', 'min_experience', 'domain']
    search_fields = ['name', 'domain']


@admin.register(JobPosting)
class JobPostingAdmin(admin.ModelAdmin):
    list_display = ['title', 'department', 'role_profile', 'is_active', 'created_at']
    list_filter = ['is_active', 'department']
    search_fields = ['title', 'department']


@admin.register(CandidateJobApplication)
class CandidateJobApplicationAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'job_posting', 'job_fit_score', 'applied_at']
    list_filter = ['job_posting']
    search_fields = ['candidate__name', 'job_posting__title']