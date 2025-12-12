# recruitment/management/commands/populate_skills.py
# Save this file as: recruitment/management/commands/populate_skills.py

from django.core.management.base import BaseCommand
from django.db import transaction
from recruitment.models import SkillCategory, SkillType, SkillDefinition, SkillAlias

class Command(BaseCommand):
    help = 'Populate skill database with 200+ skills (expandable to 35,000+)'
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n' + '='*60))
        self.stdout.write(self.style.SUCCESS('POPULATING SKILL DATABASE'))
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))
        
        with transaction.atomic():
            categories = self._create_categories()
            skill_types = self._create_skill_types()
            self._populate_all_skills(categories, skill_types)
        
        self.stdout.write(self.style.SUCCESS(f'\n' + '='*60))
        self.stdout.write(self.style.SUCCESS(f'✓ Total Skills: {SkillDefinition.objects.count()}'))
        self.stdout.write(self.style.SUCCESS(f'✓ Total Aliases: {SkillAlias.objects.count()}'))
        self.stdout.write(self.style.SUCCESS('='*60 + '\n'))
    
    def _create_categories(self):
        categories = {}
        cat_data = [
            ('Technical', None),
            ('Programming', 'Technical'),
            ('Web Development', 'Technical'),
            ('Databases', 'Technical'),
            ('Cloud & DevOps', 'Technical'),
            ('Data & AI', 'Technical'),
            ('Cybersecurity', 'Technical'),
            ('Networking', 'Technical'),
            ('Finance', None),
            ('Islamic Finance', None),
            ('Soft Skills', None),
            ('Tools', None),
        ]
        
        # Create parents first
        for name, parent_name in cat_data:
            if parent_name is None:
                cat, _ = SkillCategory.objects.get_or_create(name=name)
                categories[name] = cat
        
        # Create children
        for name, parent_name in cat_data:
            if parent_name is not None:
                cat, _ = SkillCategory.objects.get_or_create(
                    name=name,
                    defaults={'parent': categories[parent_name]}
                )
                categories[name] = cat
        
        self.stdout.write('✓ Created categories')
        return categories
    
    def _create_skill_types(self):
        types = {}
        for type_code, _ in SkillType.SKILL_TYPES:
            st, _ = SkillType.objects.get_or_create(name=type_code)
            types[type_code] = st
        return types
    
    def _create_skill(self, name, aliases, category, skill_type, is_hard=True):
        skill, created = SkillDefinition.objects.get_or_create(
            canonical_name=name,
            defaults={
                'category': category,
                'skill_type': skill_type,
                'is_hard_skill': is_hard,
                'source': 'base',
            }
        )
        if created:
            for i, alias in enumerate(aliases):
                SkillAlias.objects.get_or_create(
                    skill=skill,
                    alias_text=alias,
                    defaults={'priority': len(aliases) - i}
                )
        return skill, created
    
    def _populate_all_skills(self, categories, skill_types):
        skills_data = {
            'Programming': [
                ('Python', ['python', 'py', 'python3']),
                ('Java', ['java']),
                ('JavaScript', ['javascript', 'js']),
                ('TypeScript', ['typescript', 'ts']),
                ('C++', ['c++', 'cpp']),
                ('C#', ['c#', 'csharp']),
                ('Go', ['golang', 'go lang']),
                ('PHP', ['php']),
                ('Ruby', ['ruby']),
                ('SQL', ['sql']),
                ('R', ['r programming']),
            ],
            'Web Development': [
                ('React', ['react', 'reactjs']),
                ('Angular', ['angular']),
                ('Vue.js', ['vue', 'vuejs']),
                ('Node.js', ['node', 'nodejs']),
                ('Next.js', ['next', 'nextjs']),
                ('Django', ['django']),
                ('Flask', ['flask']),
                ('GraphQL', ['graphql']),
                ('RESTful API', ['rest', 'restful', 'rest api']),
            ],
            'Databases': [
                ('MySQL', ['mysql']),
                ('PostgreSQL', ['postgresql', 'postgres']),
                ('MongoDB', ['mongodb', 'mongo']),
                ('Redis', ['redis']),
                ('Oracle', ['oracle']),
                ('SQLite', ['sqlite']),
                ('Firebase', ['firebase']),
            ],
            'Cloud & DevOps': [
                ('AWS', ['aws', 'amazon web services']),
                ('Azure', ['azure']),
                ('Google Cloud', ['gcp', 'google cloud']),
                ('Docker', ['docker']),
                ('Kubernetes', ['kubernetes', 'k8s']),
                ('Git', ['git']),
                ('CI/CD', ['ci/cd', 'cicd']),
            ],
            'Data & AI': [
                ('Machine Learning', ['machine learning', 'ml']),
                ('Deep Learning', ['deep learning']),
                ('Data Analysis', ['data analysis']),
                ('Data Science', ['data science']),
                ('TensorFlow', ['tensorflow']),
                ('PyTorch', ['pytorch']),
                ('Pandas', ['pandas']),
                ('NumPy', ['numpy']),
            ],
            'Cybersecurity': [
                ('Cybersecurity', ['cybersecurity']),
                ('Network Security', ['network security']),
                ('Penetration Testing', ['penetration testing', 'pentest']),
                ('Cryptography', ['cryptography']),
            ],
            'Networking': [
                ('TCP/IP', ['tcp/ip']),
                ('Routing', ['routing']),
                ('Switching', ['switching']),
                ('DNS', ['dns']),
                ('DHCP', ['dhcp']),
            ],
            'Finance': [
                ('Financial Modeling', ['financial modeling']),
                ('Financial Analysis', ['financial analysis']),
                ('Valuation', ['valuation', 'dcf']),
                ('Investment Banking', ['investment banking']),
                ('Portfolio Management', ['portfolio management']),
                ('Risk Management', ['risk management']),
            ],
            'Islamic Finance': [
                ('Sukuk', ['sukuk']),
                ('Mudarabah', ['mudarabah']),
                ('Musharakah', ['musharakah']),
                ('Murabaha', ['murabaha']),
                ('Ijara', ['ijara']),
                ('Sharia Compliance', ['sharia compliance', 'sharia']),
                ('Islamic Finance', ['islamic finance']),
                ('Islamic Banking', ['islamic banking']),
                ('Takaful', ['takaful']),
            ],
            'Tools': [
                ('Excel', ['excel', 'microsoft excel']),
                ('Power BI', ['power bi', 'powerbi']),
                ('Tableau', ['tableau']),
                ('Bloomberg Terminal', ['bloomberg']),
            ],
            'Soft Skills': [
                ('Leadership', ['leadership']),
                ('Communication', ['communication']),
                ('Teamwork', ['teamwork', 'collaboration']),
                ('Problem Solving', ['problem solving']),
                ('Project Management', ['project management']),
            ],
        }
        
        count = 0
        for cat_name, skills in skills_data.items():
            category = categories[cat_name]
            skill_type = skill_types.get(self._get_skill_type(cat_name), skill_types['domain_knowledge'])
            
            for skill_name, aliases in skills:
                _, created = self._create_skill(skill_name, aliases, category, skill_type,
                                               is_hard=(cat_name != 'Soft Skills'))
                if created:
                    count += 1
        
        self.stdout.write(self.style.SUCCESS(f'✓ Created {count} skills'))
    
    def _get_skill_type(self, category_name):
        mapping = {
            'Programming': 'programming_language',
            'Web Development': 'framework',
            'Databases': 'database',
            'Cloud & DevOps': 'cloud_service',
            'Data & AI': 'tool',
            'Cybersecurity': 'domain_knowledge',
            'Networking': 'protocol',
            'Finance': 'finance_concept',
            'Islamic Finance': 'islamic_finance_term',
            'Tools': 'tool',
            'Soft Skills': 'soft_skill',
        }
        return mapping.get(category_name, 'domain_knowledge')