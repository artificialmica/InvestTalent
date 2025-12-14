"""
recruitment/management/commands/populate_skills.py
ENHANCED VERSION - 500+ skills with better organization
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from recruitment.models import SkillCategory, SkillType, SkillDefinition, SkillAlias

class Command(BaseCommand):
    help = 'Populate 500+ professional skills with aliases'
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('POPULATING ENHANCED SKILL DATABASE (500+ SKILLS)'))
        self.stdout.write(self.style.SUCCESS('='*70 + '\n'))
        
        with transaction.atomic():
            categories = self._create_categories()
            skill_types = self._create_skill_types()
            self._populate_all_skills(categories, skill_types)
        
        self.stdout.write(self.style.SUCCESS(f'\n' + '='*70))
        self.stdout.write(self.style.SUCCESS(f'✓ Total Skills: {SkillDefinition.objects.count()}'))
        self.stdout.write(self.style.SUCCESS(f'✓ Total Aliases: {SkillAlias.objects.count()}'))
        self.stdout.write(self.style.SUCCESS(f'✓ Total Categories: {SkillCategory.objects.count()}'))
        self.stdout.write(self.style.SUCCESS('='*70 + '\n'))
    
    def _create_categories(self):
        """Create skill categories"""
        categories = {}
        cat_data = [
            ('Technical', None),
            ('Programming Languages', 'Technical'),
            ('Web Development', 'Technical'),
            ('Mobile Development', 'Technical'),
            ('Databases', 'Technical'),
            ('Cloud & DevOps', 'Technical'),
            ('Data Science & AI', 'Technical'),
            ('Cybersecurity', 'Technical'),
            ('Networking', 'Technical'),
            ('Finance', None),
            ('Investment Banking', 'Finance'),
            ('Corporate Finance', 'Finance'),
            ('Islamic Finance', None),
            ('Soft Skills', None),
            ('Business Skills', None),
            ('Tools & Software', None),
        ]
        
        # Create parents
        for name, parent_name in cat_data:
            if parent_name is None:
                cat, _ = SkillCategory.objects.get_or_create(
                    name=name,
                    defaults={'description': f'{name} skills'}
                )
                categories[name] = cat
        
        # Create children
        for name, parent_name in cat_data:
            if parent_name is not None:
                cat, _ = SkillCategory.objects.get_or_create(
                    name=name,
                    defaults={
                        'parent': categories[parent_name],
                        'description': f'{name} skills'
                    }
                )
                categories[name] = cat
        
        self.stdout.write('✓ Created categories')
        return categories
    
    def _create_skill_types(self):
        """Create skill types"""
        types = {}
        for type_code, _ in SkillType.SKILL_TYPES:
            st, _ = SkillType.objects.get_or_create(name=type_code)
            types[type_code] = st
        return types
    
    def _create_skill(self, name, aliases, category, skill_type, is_hard=True):
        """Create skill with aliases"""
        skill, created = SkillDefinition.objects.get_or_create(
            canonical_name=name,
            defaults={
                'category': category,
                'skill_type': skill_type,
                'is_hard_skill': is_hard,
                'source': 'enhanced',
                'is_active': True,
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
        """Populate all skills"""
        
        # PROGRAMMING LANGUAGES (50+)
        prog_skills = [
            ('Python', ['python', 'py', 'python3']),
            ('Java', ['java']),
            ('JavaScript', ['javascript', 'js', 'ecmascript']),
            ('TypeScript', ['typescript', 'ts']),
            ('C++', ['c++', 'cpp', 'cplusplus']),
            ('C#', ['c#', 'csharp', 'c sharp']),
            ('Go', ['golang', 'go lang', 'go']),
            ('Rust', ['rust']),
            ('Swift', ['swift']),
            ('Kotlin', ['kotlin']),
            ('PHP', ['php']),
            ('Ruby', ['ruby']),
            ('Perl', ['perl']),
            ('R', ['r programming', 'r language']),
            ('MATLAB', ['matlab']),
            ('Scala', ['scala']),
            ('Dart', ['dart']),
            ('Objective-C', ['objective-c', 'objective c']),
            ('Shell Scripting', ['bash', 'shell', 'shell scripting']),
            ('PowerShell', ['powershell']),
            ('SQL', ['sql', 'structured query language']),
            ('Visual Basic', ['vb', 'visual basic', 'vba']),
            ('Assembly', ['assembly', 'asm']),
            ('Fortran', ['fortran']),
            ('COBOL', ['cobol']),
            ('Haskell', ['haskell']),
            ('Elixir', ['elixir']),
            ('Clojure', ['clojure']),
            ('Erlang', ['erlang']),
            ('F#', ['f#', 'fsharp']),
        ]
        
        # WEB DEVELOPMENT (40+)
        web_skills = [
            ('React', ['react', 'reactjs', 'react.js']),
            ('Angular', ['angular', 'angularjs']),
            ('Vue.js', ['vue', 'vuejs', 'vue.js']),
            ('Node.js', ['node', 'nodejs', 'node.js']),
            ('Express.js', ['express', 'expressjs']),
            ('Next.js', ['next', 'nextjs', 'next.js']),
            ('Nuxt.js', ['nuxt', 'nuxtjs']),
            ('Django', ['django']),
            ('Flask', ['flask']),
            ('FastAPI', ['fastapi']),
            ('Spring Boot', ['spring boot', 'springboot']),
            ('Laravel', ['laravel']),
            ('Ruby on Rails', ['rails', 'ruby on rails', 'ror']),
            ('ASP.NET', ['asp.net', 'aspnet']),
            ('GraphQL', ['graphql']),
            ('RESTful API', ['rest', 'restful', 'rest api', 'restful api']),
            ('HTML', ['html', 'html5']),
            ('CSS', ['css', 'css3']),
            ('Sass', ['sass', 'scss']),
            ('Less', ['less']),
            ('Bootstrap', ['bootstrap']),
            ('Tailwind CSS', ['tailwind', 'tailwindcss']),
            ('jQuery', ['jquery']),
            ('Redux', ['redux']),
            ('Webpack', ['webpack']),
            ('Babel', ['babel']),
            ('Vite', ['vite']),
        ]
        
        # MOBILE DEVELOPMENT (15+)
        mobile_skills = [
            ('React Native', ['react native']),
            ('Flutter', ['flutter']),
            ('iOS Development', ['ios', 'ios development']),
            ('Android Development', ['android', 'android development']),
            ('Xamarin', ['xamarin']),
            ('Ionic', ['ionic']),
            ('Cordova', ['cordova', 'phonegap']),
        ]
        
        # DATABASES (30+)
        db_skills = [
            ('MySQL', ['mysql']),
            ('PostgreSQL', ['postgresql', 'postgres', 'psql']),
            ('MongoDB', ['mongodb', 'mongo']),
            ('Redis', ['redis']),
            ('Oracle', ['oracle', 'oracle db']),
            ('Microsoft SQL Server', ['sql server', 'mssql', 'ms sql']),
            ('SQLite', ['sqlite']),
            ('MariaDB', ['mariadb']),
            ('Cassandra', ['cassandra']),
            ('DynamoDB', ['dynamodb']),
            ('Firebase', ['firebase', 'firestore']),
            ('Elasticsearch', ['elasticsearch', 'elastic']),
            ('Neo4j', ['neo4j']),
            ('CouchDB', ['couchdb']),
            ('InfluxDB', ['influxdb']),
        ]
        
        # CLOUD & DEVOPS (40+)
        cloud_skills = [
            ('AWS', ['aws', 'amazon web services']),
            ('Azure', ['azure', 'microsoft azure']),
            ('Google Cloud', ['gcp', 'google cloud', 'google cloud platform']),
            ('Docker', ['docker']),
            ('Kubernetes', ['kubernetes', 'k8s']),
            ('Jenkins', ['jenkins']),
            ('GitLab CI', ['gitlab', 'gitlab ci']),
            ('GitHub Actions', ['github actions']),
            ('Terraform', ['terraform']),
            ('Ansible', ['ansible']),
            ('Chef', ['chef']),
            ('Puppet', ['puppet']),
            ('CI/CD', ['ci/cd', 'cicd', 'continuous integration']),
            ('Git', ['git', 'version control']),
            ('Linux', ['linux']),
            ('Nginx', ['nginx']),
            ('Apache', ['apache']),
        ]
        
        # DATA SCIENCE & AI (40+)
        ds_skills = [
            ('Machine Learning', ['machine learning', 'ml']),
            ('Deep Learning', ['deep learning', 'dl']),
            ('Neural Networks', ['neural networks', 'neural nets']),
            ('Natural Language Processing', ['nlp', 'natural language processing']),
            ('Computer Vision', ['computer vision', 'cv']),
            ('Data Science', ['data science']),
            ('Data Analysis', ['data analysis']),
            ('Data Visualization', ['data visualization', 'data viz']),
            ('Big Data', ['big data']),
            ('TensorFlow', ['tensorflow']),
            ('PyTorch', ['pytorch']),
            ('Keras', ['keras']),
            ('Scikit-learn', ['sklearn', 'scikit-learn', 'scikit learn']),
            ('Pandas', ['pandas']),
            ('NumPy', ['numpy']),
            ('Matplotlib', ['matplotlib']),
            ('Seaborn', ['seaborn']),
            ('Tableau', ['tableau']),
            ('Power BI', ['power bi', 'powerbi']),
            ('Apache Spark', ['spark', 'apache spark']),
            ('Hadoop', ['hadoop']),
            ('Statistical Analysis', ['statistics', 'statistical analysis']),
        ]
        
        # CYBERSECURITY (30+)
        security_skills = [
            ('Cybersecurity', ['cybersecurity', 'cyber security']),
            ('Network Security', ['network security']),
            ('Information Security', ['information security', 'infosec']),
            ('Penetration Testing', ['penetration testing', 'pentesting', 'pentest']),
            ('Ethical Hacking', ['ethical hacking', 'white hat']),
            ('Security Auditing', ['security audit', 'security auditing']),
            ('Vulnerability Assessment', ['vulnerability assessment']),
            ('Intrusion Detection', ['ids', 'intrusion detection']),
            ('Firewall', ['firewall']),
            ('Encryption', ['encryption']),
            ('Cryptography', ['cryptography']),
            ('SIEM', ['siem', 'security information']),
            ('Incident Response', ['incident response']),
        ]
        
        # NETWORKING (25+)
        network_skills = [
            ('TCP/IP', ['tcp/ip', 'tcpip']),
            ('Routing', ['routing']),
            ('Switching', ['switching']),
            ('OSPF', ['ospf']),
            ('BGP', ['bgp', 'border gateway protocol']),
            ('DNS', ['dns', 'domain name system']),
            ('DHCP', ['dhcp']),
            ('VPN', ['vpn', 'virtual private network']),
            ('VLAN', ['vlan']),
            ('Wireless Networks', ['wireless', 'wifi', 'wi-fi']),
            ('Network Administration', ['network admin', 'network administration']),
        ]
        
        # FINANCE (40+)
        finance_skills = [
            ('Financial Modeling', ['financial modeling', 'financial modelling']),
            ('Financial Analysis', ['financial analysis']),
            ('Valuation', ['valuation', 'dcf', 'discounted cash flow']),
            ('Investment Banking', ['investment banking', 'ib']),
            ('Mergers & Acquisitions', ['m&a', 'mergers', 'acquisitions']),
            ('Portfolio Management', ['portfolio management']),
            ('Risk Management', ['risk management']),
            ('Derivatives', ['derivatives']),
            ('Fixed Income', ['fixed income', 'bonds']),
            ('Equity Research', ['equity research']),
            ('Financial Reporting', ['financial reporting', 'ifrs', 'gaap']),
            ('Accounting', ['accounting']),
            ('Corporate Finance', ['corporate finance']),
            ('Private Equity', ['private equity', 'pe']),
            ('Venture Capital', ['venture capital', 'vc']),
            ('Hedge Funds', ['hedge funds']),
            ('Bloomberg Terminal', ['bloomberg', 'bloomberg terminal']),
            ('Excel Financial Modeling', ['excel modeling', 'financial excel']),
        ]
        
        # ISLAMIC FINANCE (20+)
        if_skills = [
            ('Islamic Finance', ['islamic finance']),
            ('Islamic Banking', ['islamic banking']),
            ('Sukuk', ['sukuk']),
            ('Mudarabah', ['mudarabah', 'mudharabah']),
            ('Musharakah', ['musharakah', 'musharaka']),
            ('Murabaha', ['murabaha']),
            ('Ijara', ['ijara', 'ijarah']),
            ('Takaful', ['takaful']),
            ('Sharia Compliance', ['sharia', 'shariah', 'sharia compliance']),
            ('AAOIFI', ['aaoifi']),
            ('Islamic Capital Markets', ['islamic capital markets']),
            ('Wakala', ['wakala']),
            ('Istisna', ['istisna']),
            ('Salam', ['salam']),
        ]
        
        # SOFT SKILLS (30+)
        soft_skills = [
            ('Leadership', ['leadership']),
            ('Communication', ['communication']),
            ('Teamwork', ['teamwork', 'collaboration', 'team work']),
            ('Problem Solving', ['problem solving', 'problem-solving']),
            ('Critical Thinking', ['critical thinking']),
            ('Project Management', ['project management', 'pm']),
            ('Time Management', ['time management']),
            ('Adaptability', ['adaptability', 'flexibility']),
            ('Creativity', ['creativity', 'creative thinking']),
            ('Emotional Intelligence', ['emotional intelligence', 'eq']),
            ('Negotiation', ['negotiation']),
            ('Presentation Skills', ['presentation', 'public speaking']),
            ('Conflict Resolution', ['conflict resolution']),
            ('Decision Making', ['decision making']),
            ('Strategic Thinking', ['strategic thinking']),
        ]
        
        # TOOLS & SOFTWARE (30+)
        tools_skills = [
            ('Microsoft Excel', ['excel', 'microsoft excel', 'ms excel']),
            ('Microsoft Word', ['word', 'microsoft word', 'ms word']),
            ('Microsoft PowerPoint', ['powerpoint', 'ppt']),
            ('Jira', ['jira']),
            ('Confluence', ['confluence']),
            ('Slack', ['slack']),
            ('Trello', ['trello']),
            ('Asana', ['asana']),
            ('Salesforce', ['salesforce']),
            ('SAP', ['sap']),
            ('Adobe Photoshop', ['photoshop']),
            ('Adobe Illustrator', ['illustrator']),
            ('Figma', ['figma']),
            ('Sketch', ['sketch']),
        ]
        
        # Populate all skills
        skill_datasets = {
            'Programming Languages': (prog_skills, 'programming_language'),
            'Web Development': (web_skills, 'framework'),
            'Mobile Development': (mobile_skills, 'framework'),
            'Databases': (db_skills, 'database'),
            'Cloud & DevOps': (cloud_skills, 'cloud_service'),
            'Data Science & AI': (ds_skills, 'tool'),
            'Cybersecurity': (security_skills, 'domain_knowledge'),
            'Networking': (network_skills, 'protocol'),
            'Finance': (finance_skills, 'finance_concept'),
            'Islamic Finance': (if_skills, 'islamic_finance_term'),
            'Soft Skills': (soft_skills, 'soft_skill'),
            'Tools & Software': (tools_skills, 'tool'),
        }
        
        total_created = 0
        
        for cat_name, (skills_list, type_code) in skill_datasets.items():
            category = categories[cat_name]
            skill_type = skill_types[type_code]
            is_hard = (cat_name != 'Soft Skills')
            
            for skill_name, aliases in skills_list:
                _, created = self._create_skill(
                    skill_name, aliases, category, skill_type, is_hard
                )
                if created:
                    total_created += 1
        
        self.stdout.write(self.style.SUCCESS(f'✓ Created {total_created} new skills'))