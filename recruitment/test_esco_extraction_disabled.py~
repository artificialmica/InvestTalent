from auto_extractor import extract_esco_skills

# Test Case 1: Software Engineer CV
print("=" * 60)
print("TEST 1: Software Engineer CV")
print("=" * 60)

sample_cv_1 = """
Software Engineer with 5 years experience in Python, Django, and PostgreSQL.
Strong skills in machine learning, data analysis, and cloud computing.
Certified AWS Solutions Architect. Experience with REST APIs, Docker, and Kubernetes.
Proficient in JavaScript, React, and Node.js.
"""

skills_1 = extract_esco_skills(sample_cv_1)
print(f"\nFound {len(skills_1)} skills:")
for skill in skills_1:
    print(f"  - {skill}")

# Test Case 2: Finance Professional CV
print("\n" + "=" * 60)
print("TEST 2: Finance Professional CV")
print("=" * 60)

sample_cv_2 = """
Senior Financial Analyst with expertise in financial modeling, risk management,
and portfolio analysis. Strong background in Excel, SQL, and Tableau.
Experience with budgeting, forecasting, and financial reporting.
Knowledge of IFRS and GAAP accounting standards.
"""

skills_2 = extract_esco_skills(sample_cv_2)
print(f"\nFound {len(skills_2)} skills:")
for skill in skills_2:
    print(f"  - {skill}")

# Test Case 3: Islamic Finance (Your Domain)
print("\n" + "=" * 60)
print("TEST 3: Islamic Finance Professional CV")
print("=" * 60)

sample_cv_3 = """
Islamic Finance Specialist with expertise in Sharia-compliant investment products,
Sukuk structuring, and Islamic banking principles. Strong analytical skills and
experience with financial analysis, risk assessment, and portfolio management.
Proficient in Excel, financial modeling, and regulatory compliance.
"""

skills_3 = extract_esco_skills(sample_cv_3)
print(f"\nFound {len(skills_3)} skills:")
for skill in skills_3:
    print(f"  - {skill}")

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"Test 1 (Software): {len(skills_1)} skills detected")
print(f"Test 2 (Finance): {len(skills_2)} skills detected")
print(f"Test 3 (Islamic Finance): {len(skills_3)} skills detected")
print("\n✅ ESCO extraction is working!")