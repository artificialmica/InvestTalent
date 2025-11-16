from django.contrib import admin
from .models import Candidate, Resume, Education, Experience, Skill, Score

@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'status', 'years_experience', 'get_score', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['name', 'email', 'current_position']
    list_per_page = 25
    readonly_fields = ['created_at', 'updated_at']
    
    def get_score(self, obj):
        if hasattr(obj, 'score'):
            return f"{obj.score.total_score}/100"
        return "Not scored"
    get_score.short_description = 'Score'

@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'file_type', 'uploaded_at', 'get_text_preview']
    list_filter = ['file_type', 'uploaded_at']
    search_fields = ['candidate__name']
    readonly_fields = ['uploaded_at']
    
    def get_text_preview(self, obj):
        if obj.parsed_text:
            return obj.parsed_text[:100] + "..."
        return "No text"
    get_text_preview.short_description = 'Preview'

@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'degree', 'institution', 'graduation_year', 'has_islamic_finance_cert']
    list_filter = ['degree', 'has_islamic_finance_cert']
    search_fields = ['candidate__name', 'institution']

@admin.register(Experience)
class ExperienceAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'position', 'company', 'start_date', 'is_current', 'is_islamic_finance']
    list_filter = ['is_current', 'is_islamic_finance']
    search_fields = ['candidate__name', 'company', 'position']

@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'skill_name', 'category', 'proficiency_level']
    list_filter = ['category', 'proficiency_level']
    search_fields = ['candidate__name', 'skill_name']

@admin.register(Score)
class ScoreAdmin(admin.ModelAdmin):
    list_display = ['candidate', 'total_score', 'education_score', 'experience_score', 'skills_score', 'islamic_finance_score', 'rank']
    list_filter = ['rank']
    search_fields = ['candidate__name']
    readonly_fields = ['evaluated_at']
    ordering = ['-total_score']