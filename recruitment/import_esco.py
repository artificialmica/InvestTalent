import csv
import sqlite3
from pathlib import Path

DB_PATH = Path("data/esco.db")
ESCO_PATH = Path("esco_raw")

# Check if esco_raw folder exists
if not ESCO_PATH.exists():
    print(f"❌ ERROR: Folder '{ESCO_PATH}' does not exist!")
    print("Please create 'esco_raw' folder and add CSV files.")
    exit(1)

# Check if required files exist
required_files = ["skills_en.csv", "occupations_en.csv", "occupationSkillRelations_en.csv"]
for file in required_files:
    if not (ESCO_PATH / file).exists():
        print(f"❌ ERROR: Required file '{file}' not found in {ESCO_PATH}")
        exit(1)

print("✅ All required files found")

# Create data folder if it doesn't exist
DB_PATH.parent.mkdir(exist_ok=True)

# Create/connect to database
print(f"Creating database at: {DB_PATH.absolute()}")
conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Create tables
print("Creating tables...")
cur.executescript("""
DROP TABLE IF EXISTS skills;
DROP TABLE IF EXISTS skill_aliases;
DROP TABLE IF EXISTS occupations;
DROP TABLE IF EXISTS occupation_skills;

CREATE TABLE skills (
    skill_id TEXT PRIMARY KEY,
    skill_name TEXT,
    skill_type TEXT
);

CREATE TABLE skill_aliases (
    skill_id TEXT,
    alias TEXT
);

CREATE TABLE occupations (
    occupation_id TEXT PRIMARY KEY,
    occupation_name TEXT
);

CREATE TABLE occupation_skills (
    occupation_id TEXT,
    skill_id TEXT
);
""")

print("✅ Tables created successfully")
print("\nLoading skills from CSV...")

# Load skills
skill_count = 0
alias_count = 0
try:
    with open(ESCO_PATH / "skills_en.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cur.execute(
                "INSERT OR IGNORE INTO skills VALUES (?, ?, ?)",
                (
                    row["conceptUri"],
                    row["preferredLabel"],
                    row.get("skillType", "")
                )
            )
            
            # Add preferred label as alias
            cur.execute(
                "INSERT INTO skill_aliases VALUES (?, ?)",
                (row["conceptUri"], row["preferredLabel"].strip().lower())
            )
            alias_count += 1
            
            # Add alternative labels as aliases
            if row.get("altLabels"):
                alt_labels = row["altLabels"].split("\n")
                for label in alt_labels:
                    if label.strip():
                        cur.execute(
                            "INSERT INTO skill_aliases VALUES (?, ?)",
                            (row["conceptUri"], label.strip().lower())
                        )
                        alias_count += 1
            skill_count += 1
            
            if skill_count % 1000 == 0:
                print(f"  Processed {skill_count} skills...")
                
    print(f"✅ Loaded {skill_count} skills with {alias_count} aliases")
except Exception as e:
    print(f"❌ ERROR loading skills: {e}")
    exit(1)

# Load occupations
print("\nLoading occupations from CSV...")
occ_count = 0
try:
    with open(ESCO_PATH / "occupations_en.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cur.execute(
                "INSERT OR IGNORE INTO occupations VALUES (?, ?)",
                (row["conceptUri"], row["preferredLabel"])
            )
            occ_count += 1
            
            if occ_count % 500 == 0:
                print(f"  Processed {occ_count} occupations...")
                
    print(f"✅ Loaded {occ_count} occupations")
except Exception as e:
    print(f"❌ ERROR loading occupations: {e}")
    exit(1)

# Load occupation-skill relations
print("\nLoading occupation-skill relations from CSV...")
rel_count = 0
try:
    with open(ESCO_PATH / "occupationSkillRelations_en.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cur.execute(
                "INSERT INTO occupation_skills VALUES (?, ?)",
                (row["occupationUri"], row["skillUri"])
            )
            rel_count += 1
            
            if rel_count % 10000 == 0:
                print(f"  Processed {rel_count} relations...")
                
    print(f"✅ Loaded {rel_count} occupation-skill relations")
except Exception as e:
    print(f"❌ ERROR loading relations: {e}")
    exit(1)

print("\nCommitting to database...")
conn.commit()
conn.close()

print("\n" + "=" * 60)
print("✅ ESCO IMPORT COMPLETE!")
print("=" * 60)
print(f"Database location: {DB_PATH.absolute()}")
print(f"Skills: {skill_count}")
print(f"Skill aliases: {alias_count}")
print(f"Occupations: {occ_count}")
print(f"Relations: {rel_count}")
print("=" * 60)
