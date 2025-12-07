from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError

# Candidate Model 
class Candidate(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    current_position = models.CharField(max_length=200, blank=True, null=True)
    years_experience = models.IntegerField(default=0)
    linkedin_url = models.URLField(blank=True, null=True)
    
    # Audit fields
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    file_hash = models.CharField(max_length=64, null=True, blank=True)  # SHA-256 hash
    is_verified = models.BooleanField(default=False)
    security_flags = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    STATUS_CHOICES = [
        ('received', 'Application Received'),
        ('screening', 'Under Screening'),
        ('shortlisted', 'Shortlisted'),
        ('interview', 'Interview Scheduled'),
        ('offer', 'Offer Extended'),
        ('hired', 'Hired'),
        ('rejected', 'Rejected'),
    ]
    
    status = models.CharField(
        max_length=50,
        choices=STATUS_CHOICES,
        default='received'
    )
    
    application_source = models.CharField(
        max_length=100, 
        blank=True,
        choices=[
            ('website', 'Company Website'),
            ('linkedin', 'LinkedIn'),
            ('referral', 'Employee Referral'),
            ('job_board', 'Job Board'),
            ('direct', 'Direct Application'),
            ('other', 'Other')
        ],
        default='direct'
    )
    
    def __str__(self):
        return self.name
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Candidate'
        verbose_name_plural = 'Candidates'


# Resume Model
class Resume(models.Model):
    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name='resume')
    file = models.FileField(upload_to='resumes/')
    file_type = models.CharField(max_length=10)
    parsed_text = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Resume for {self.candidate.name}"
    
    class Meta:
        verbose_name = 'Resume'
        verbose_name_plural = 'Resumes'


# Education Model
class Education(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='education')
    degree = models.CharField(max_length=100)
    institution = models.CharField(max_length=200)
    field_of_study = models.CharField(max_length=100)
    graduation_year = models.IntegerField(blank=True, null=True)
    has_islamic_finance_cert = models.BooleanField(default=False)
    certification_names = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.degree} - {self.institution}"
    
    class Meta:
        verbose_name = 'Education'
        verbose_name_plural = 'Education Records'
        ordering = ['-graduation_year']


# Experience Model
class Experience(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='experience')
    company = models.CharField(max_length=200)
    position = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    is_current = models.BooleanField(default=False)
    description = models.TextField(blank=True, null=True)
    is_islamic_finance = models.BooleanField(default=False)
    
    def __str__(self):
        return f"{self.position} at {self.company}"
    
    class Meta:
        verbose_name = 'Work Experience'
        verbose_name_plural = 'Work Experience Records'
        ordering = ['-start_date']


# Skill Model
class Skill(models.Model):
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='skills')
    skill_name = models.CharField(max_length=100)
    
    PROFICIENCY_LEVELS = [
        ('beginner', 'Beginner'),
        ('intermediate', 'Intermediate'),
        ('advanced', 'Advanced'),
        ('expert', 'Expert'),
    ]
    
    proficiency_level = models.CharField(max_length=20, choices=PROFICIENCY_LEVELS, default='intermediate')
    
    SKILL_CATEGORIES = [
        ('technical', 'Technical'),
        ('finance', 'Finance'),
        ('islamic_finance', 'Islamic Finance'),
        ('soft_skill', 'Soft Skill'),
        ('language', 'Language'),
    ]
    
    category = models.CharField(max_length=20, choices=SKILL_CATEGORIES, default='technical')
    is_hard_skill = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.skill_name} ({self.proficiency_level})"
    
    class Meta:
        verbose_name = 'Skill'
        verbose_name_plural = 'Skills'


# Score Model
class Score(models.Model):
    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name='score')
    education_score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    experience_score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    skills_score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    islamic_finance_score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    total_score = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    rank = models.IntegerField(blank=True, null=True)
    evaluated_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Score for {self.candidate.name}: {self.total_score}/100"
    
    class Meta:
        verbose_name = 'Score'
        verbose_name_plural = 'Scores'
        ordering = ['-total_score']


# WorkflowEvent Model
class WorkflowEvent(models.Model):
    """
    Tracks individual events in the recruitment workflow
    """
    candidate = models.ForeignKey(
        Candidate,
        on_delete=models.CASCADE,
        related_name='workflow_events'
    )
    event_type = models.CharField(max_length=50)
    old_status = models.CharField(max_length=20, null=True, blank=True)
    new_status = models.CharField(max_length=20)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=100, default='System')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Workflow Event'
        verbose_name_plural = 'Workflow Events'
    
    def __str__(self):
        return f"{self.candidate.name} - {self.event_type} - {self.created_at}"


# JobRoleProfile Model - NEW! Pre-configured weight templates
class JobRoleProfile(models.Model):
    """
    Pre-configured weight templates for different job types
    Allows HR to quickly select appropriate scoring criteria
    """
    PROFILE_TYPES = [
        ('IF_SENIOR', 'Islamic Finance Professional (Senior)'),
        ('IF_JUNIOR', 'Islamic Finance Analyst (Entry-Level)'),
        ('TECH_DEV', 'Technology/Software Developer'),
        ('TECH_ANALYST', 'Data/Business Analyst'),
        ('HR_MANAGER', 'HR Manager'),
        ('ADMIN', 'Administrative/Support Staff'),
        ('EXEC_SENIOR', 'Senior Executive'),
        ('ENTRY_LEVEL', 'Entry-Level (General)'),
        ('CUSTOM', 'Custom Profile'),
    ]
    
    name = models.CharField(max_length=100)
    profile_type = models.CharField(max_length=20, choices=PROFILE_TYPES)
    description = models.TextField()
    
    # Weight defaults (must sum to 1.0)
    education_weight = models.FloatField(default=0.25, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    experience_weight = models.FloatField(default=0.30, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    skills_weight = models.FloatField(default=0.25, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    islamic_finance_weight = models.FloatField(default=0.20, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    
    # Additional metadata
    is_active = models.BooleanField(default=True)
    is_system_default = models.BooleanField(default=True)  # System vs user-created
    created_at = models.DateTimeField(auto_now_add=True)
    
    def clean(self):
        """Validate weights sum to 1.0"""
        total = (self.education_weight + self.experience_weight + 
                self.skills_weight + self.islamic_finance_weight)
        if abs(total - 1.0) > 0.01:
            raise ValidationError(f'Weights must sum to 1.0 (currently: {total:.2f})')
    
    def save(self, *args, **kwargs):
        """Run validation before saving"""
        self.clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.name}"
    
    class Meta:
        verbose_name = 'Job Role Profile'
        verbose_name_plural = 'Job Role Profiles'
        ordering = ['profile_type', 'name']


# JobPosting Model - For job requirements and customizable weights
class JobPosting(models.Model):
    """
    Defines job requirements and scoring weights for candidate matching
    """
    title = models.CharField(max_length=200)
    department = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    
    # NEW: Link to role profile
    role_profile = models.ForeignKey(
        JobRoleProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Select a pre-configured role profile (weights can still be customized)"
    )
    
    # Required skills (JSON list)
    required_skills = models.JSONField(default=list, blank=True)
    preferred_skills = models.JSONField(default=list, blank=True)
    
    # Experience requirements
    min_years_experience = models.IntegerField(default=0)
    max_years_experience = models.IntegerField(blank=True, null=True)
    
    # Education requirements
    min_education_level = models.CharField(max_length=50, blank=True)
    required_certifications = models.TextField(blank=True)
    
    # Special requirements (free text)
    special_requirements = models.TextField(blank=True)
    
    # Customizable Scoring Weights (can be copied from profile or customized)
    education_weight = models.FloatField(default=0.25, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    experience_weight = models.FloatField(default=0.30, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    skills_weight = models.FloatField(default=0.25, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    islamic_finance_weight = models.FloatField(default=0.20, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    
    # Hard vs Soft Skills weights
    hard_skills_weight = models.FloatField(default=0.70, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    soft_skills_weight = models.FloatField(default=0.30, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=100, default='HR Manager')
    is_active = models.BooleanField(default=True)
    
    def save(self, *args, **kwargs):
        """Copy weights from profile if profile is selected and this is a new job"""
        if self.role_profile and not self.pk:  # Only on creation
            self.education_weight = self.role_profile.education_weight
            self.experience_weight = self.role_profile.experience_weight
            self.skills_weight = self.role_profile.skills_weight
            self.islamic_finance_weight = self.role_profile.islamic_finance_weight
        
        super().save(*args, **kwargs)
    
    class Meta:
        verbose_name = 'Job Posting'
        verbose_name_plural = 'Job Postings'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.title} - {self.department}"


# Link candidates to job postings
class CandidateJobApplication(models.Model):
    """
    Links candidates to specific job postings for targeted scoring
    """
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='job_applications')
    job_posting = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name='applications')
    applied_at = models.DateTimeField(auto_now_add=True)
    
    # Job-specific score (using job's custom weights)
    job_fit_score = models.FloatField(default=0.0)
    
    class Meta:
        verbose_name = 'Job Application'
        verbose_name_plural = 'Job Applications'
        unique_together = ['candidate', 'job_posting']
    
    def __str__(self):
        return f"{self.candidate.name} → {self.job_posting.title}"