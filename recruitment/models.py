from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Candidate(models.Model):
    """Candidate model - matches recruitment_candidate table exactly"""
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    current_position = models.CharField(max_length=200, blank=True, null=True)
    linkedin_url = models.URLField(blank=True, null=True)
    status = models.CharField(max_length=20, default='received')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    file_hash = models.CharField(max_length=64, blank=True, null=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    security_flags = models.JSONField(default=dict, blank=True)
    application_source = models.CharField(max_length=50, default='direct')
    years_experience = models.IntegerField(default=0, blank=True, null=True)
    
    
    GENDER_CHOICES = [
        ('', 'Prefer not to say'),
        ('male', 'Male'),
        ('female', 'Female'),
        ('non_binary', 'Non-binary'),
        ('other', 'Other'),
    ]
    
    NATIONALITY_CHOICES = [
        ('', 'Prefer not to say'),
        ('bahraini', 'Bahraini'),
        ('gcc', 'GCC National'),
        ('south_asian', 'South Asian'),
        ('middle_eastern', 'Middle Eastern'),
        ('western', 'Western'),
        ('other', 'Other'),
    ]
    
    gender = models.CharField(
        max_length=20,
        choices=GENDER_CHOICES,
        blank=True,
        default='',
        help_text='Optional. Used for diversity analytics only, not for scoring.'
    )
    
    nationality = models.CharField(
        max_length=50,
        choices=NATIONALITY_CHOICES,
        blank=True,
        default='',
        help_text='Optional. Used for diversity analytics only, not for scoring.'
    )
    
    STATUS_CHOICES = [
        ('received', 'Application Received'),
        ('screening', 'Under Screening'),
        ('shortlisted', 'Shortlisted'),
        ('interview', 'Interview Scheduled'),
        ('offer', 'Offer Extended'),
        ('hired', 'Hired'),
        ('rejected', 'Rejected'),
    ]
    
    def __str__(self):
        return self.name
    
    class Meta:
        db_table = 'recruitment_candidate'


class Resume(models.Model):
    """Resume model - matches recruitment_resume table"""
    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name='resume')
    file = models.FileField(upload_to='resumes/')
    file_type = models.CharField(max_length=10)
    parsed_text = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Resume for {self.candidate.name}"
    
    class Meta:
        db_table = 'recruitment_resume'


class Education(models.Model):
    """Education model - matches recruitment_education table"""
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='education')
    degree = models.CharField(max_length=100)
    institution = models.CharField(max_length=200)
    field_of_study = models.CharField(max_length=100, blank=True, null=True)
    graduation_year = models.IntegerField(blank=True, null=True)
    has_islamic_finance_cert = models.BooleanField(default=False)
    certification_names = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.degree} - {self.institution}"
    
    class Meta:
        db_table = 'recruitment_education'


class Experience(models.Model):
    """Experience model - matches recruitment_experience table"""
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='experience')
    company = models.CharField(max_length=200)
    position = models.CharField(max_length=200)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    is_current = models.BooleanField(default=False)
    description = models.TextField(blank=True, null=True)
    is_islamic_finance = models.BooleanField(default=False)
    years = models.IntegerField(blank=True, null=True)
    
    def __str__(self):
        return f"{self.position} at {self.company}"
    
    class Meta:
        db_table = 'recruitment_experience'


class Score(models.Model):
    """Score model - matches recruitment_score table EXACTLY"""
    candidate = models.OneToOneField(Candidate, on_delete=models.CASCADE, related_name='score')
    education_score = models.FloatField(default=0.0)
    experience_score = models.FloatField(default=0.0)
    skills_score = models.FloatField(default=0.0)
    islamic_finance_score = models.FloatField(default=0.0)
    total_score = models.FloatField(default=0.0)
    calculated_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Score for {self.candidate.name}: {self.total_score}/100"
    
    class Meta:
        db_table = 'recruitment_score'


class WorkflowEvent(models.Model):
    """WorkflowEvent model - matches recruitment_workflowevent table"""
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='workflow_events')
    event_type = models.CharField(max_length=50)
    old_status = models.CharField(max_length=20, blank=True, null=True)
    new_status = models.CharField(max_length=20)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=100, default='System')
    
    def __str__(self):
        return f"{self.candidate.name} - {self.event_type}"
    
    class Meta:
        db_table = 'recruitment_workflowevent'


class SkillType(models.Model):
    """SkillType model - matches recruitment_skilltype table"""
    name = models.CharField(max_length=50, unique=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        db_table = 'recruitment_skilltype'


class SkillCategory(models.Model):
    """SkillCategory model - matches recruitment_skillcategory table"""
    name = models.CharField(max_length=100, unique=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        db_table = 'recruitment_skillcategory'


class SkillDefinition(models.Model):
    """SkillDefinition model - matches recruitment_skilldefinition table"""
    canonical_name = models.CharField(max_length=200, unique=True)
    is_hard_skill = models.BooleanField(default=True)
    importance_weight = models.FloatField(default=1.0)
    category = models.ForeignKey(SkillCategory, on_delete=models.CASCADE)
    parent_skill = models.ForeignKey('self', on_delete=models.CASCADE, blank=True, null=True)
    skill_type = models.ForeignKey(SkillType, on_delete=models.CASCADE, blank=True, null=True)
    
    def __str__(self):
        return self.canonical_name
    
    class Meta:
        db_table = 'recruitment_skilldefinition'


class ExtractedSkill(models.Model):
    """ExtractedSkill model - matches recruitment_extractedskill table"""
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='extracted_skills')
    skill = models.ForeignKey(SkillDefinition, on_delete=models.CASCADE)
    source_section = models.CharField(max_length=30)
    frequency = models.IntegerField(default=1)
    confidence_score = models.FloatField(default=1.0)
    matched_via = models.CharField(max_length=20, default='exact')
    
    def __str__(self):
        return f"{self.candidate.name}: {self.skill.canonical_name}"
    
    class Meta:
        db_table = 'recruitment_extractedskill'
        unique_together = ['candidate', 'skill']


class JobRoleProfile(models.Model):
    """JobRoleProfile model - matches recruitment_jobroleprofile table"""
    name = models.CharField(max_length=200)
    min_experience = models.IntegerField(default=0)
    domain = models.CharField(max_length=100, blank=True, null=True)
    required_skills = models.ManyToManyField(SkillDefinition, related_name='required_for_roles', blank=True)
    preferred_skills = models.ManyToManyField(SkillDefinition, related_name='preferred_for_roles', blank=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        db_table = 'recruitment_jobroleprofile'


class JobPosting(models.Model):
    """JobPosting model - matches recruitment_jobposting table EXACTLY"""
    title = models.CharField(max_length=200)
    department = models.CharField(max_length=100)
    description = models.TextField()
    education_weight = models.FloatField(default=0.25)
    experience_weight = models.FloatField(default=0.30)
    skills_weight = models.FloatField(default=0.25)
    hard_skills_weight = models.FloatField(default=0.70)
    soft_skills_weight = models.FloatField(default=0.30)
    domain_weight = models.FloatField(default=0.20)
    role_profile = models.ForeignKey(JobRoleProfile, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.title} - {self.department}"
    
    class Meta:
        db_table = 'recruitment_jobposting'


class CandidateJobApplication(models.Model):
    """CandidateJobApplication model - matches recruitment_candidatejobapplication table"""
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name='job_applications')
    job_posting = models.ForeignKey(JobPosting, on_delete=models.CASCADE, related_name='applications')
    applied_at = models.DateTimeField(auto_now_add=True)
    job_fit_score = models.FloatField(default=0.0)
    
    def __str__(self):
        return f"{self.candidate.name} -> {self.job_posting.title}"
    
    class Meta:
        db_table = 'recruitment_candidatejobapplication'
        unique_together = ['candidate', 'job_posting']


# Backward compatibility alias
Skill = ExtractedSkill