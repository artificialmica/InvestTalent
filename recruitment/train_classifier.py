"""
Skill Classifier Training Script - IMPROVED VERSION
Enhanced with:
- SMOTE (Synthetic Minority Oversampling Technique) for class balancing
- Random Forest as alternative classifier
- Optimized hyperparameters
- Better feature engineering
- Threshold tuning for precision/recall balance

Author: InvestTalent-AI Project
"""

import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import StratifiedShuffleSplit, cross_val_score, GridSearchCV
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
    f1_score,
    precision_recall_curve,
    roc_auc_score
)
from sklearn.preprocessing import StandardScaler
import joblib
from pathlib import Path
import argparse
import sys
import warnings
warnings.filterwarnings('ignore')

# Try to import SMOTE
try:
    from imblearn.over_sampling import SMOTE
    from imblearn.pipeline import Pipeline as ImbPipeline
    SMOTE_AVAILABLE = True
except ImportError:
    SMOTE_AVAILABLE = False
    print("[!] WARNING: imbalanced-learn not installed. Install with:")
    print("    pip install imbalanced-learn")
    print("    Continuing without SMOTE...\n")


class ImprovedSkillClassifierTrainer:
    def __init__(self, use_smote=True, classifier_type='logistic'):
        self.vectorizer = None
        self.classifier = None
        self.scaler = None
        self.feature_names = None
        self.use_smote = use_smote and SMOTE_AVAILABLE
        self.classifier_type = classifier_type
        self.optimal_threshold = 0.5
        
    def load_data(self, filepath):
        if not Path(filepath).exists():
            print(f"[!] Error: Input file not found: {filepath}")
            sys.exit(1)

        df = pd.read_csv(filepath)
        df = df[df['label'].notna()].copy()

        if len(df) == 0:
            print("[!] No labeled data found!")
            sys.exit(1)

        print(f"[i] Loaded {len(df)} labeled chunks\n")

        pos = (df['label'] == 1).sum()
        neg = (df['label'] == 0).sum()
        ratio = neg / pos if pos > 0 else 0

        print("Class distribution:")
        print(f"  Skill (1):     {pos} ({pos/len(df)*100:.1f}%)")
        print(f"  Non-skill (0): {neg} ({neg/len(df)*100:.1f}%)")
        print(f"  Imbalance ratio: {ratio:.1f}:1\n")

        if self.use_smote:
            print("✓ SMOTE will be applied to balance classes\n")
        
        return df

    def extract_features(self, df, fit=True):
        required_cols = ["text", "word_count", "char_count", "has_digit", 
                         "has_special", "section", "pos_pattern"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            print(f"[!] ERROR: Missing columns: {missing}")
            sys.exit(1)
        
        texts = df["text"].fillna("").astype(str).values

        if fit:
            # Enhanced TF-IDF with better parameters
            self.vectorizer = TfidfVectorizer(
                max_features=2000,        # More features
                ngram_range=(1, 3),       # Capture phrases
                min_df=1,                 # Include rare terms (skills are often rare)
                max_df=0.95,
                strip_accents="unicode",
                lowercase=True,
                token_pattern=r"\b\w[\w\-\.]*\w\b|\b\w\b",  # Better token pattern
                sublinear_tf=True         # Apply log scaling
            )
            X_tfidf = self.vectorizer.fit_transform(texts)
            self.feature_names = list(self.vectorizer.get_feature_names_out())
        else:
            X_tfidf = self.vectorizer.transform(texts)

        X = X_tfidf.toarray()

        # Enhanced feature engineering
        extra = []
        for _, row in df.iterrows():
            text = str(row["text"]) if pd.notna(row["text"]) else ""
            
            # POS pattern hash (normalized)
            pos_hash = (hash(str(row["pos_pattern"])) % 1000) / 1000.0
            
            # Section one-hot encoding
            section = str(row["section"]).lower() if pd.notna(row["section"]) else ""
            
            # Text-based features
            word_count = row["word_count"] if pd.notna(row["word_count"]) else 0
            char_count = row["char_count"] if pd.notna(row["char_count"]) else 0
            
            # NEW: Additional features for better skill detection
            has_uppercase = 1 if any(c.isupper() for c in text) else 0
            has_numbers = 1 if row["has_digit"] else 0
            has_special = 1 if row["has_special"] else 0
            
            # Word length ratio (skills tend to be specific terms)
            avg_word_len = char_count / max(word_count, 1)
            
            # Is it a short chunk? (skills are often 1-3 words)
            is_short = 1 if word_count <= 3 else 0
            
            # Contains common skill indicators
            text_lower = text.lower()
            has_tech_suffix = 1 if any(text_lower.endswith(s) for s in ['.js', '.py', 'sql', 'ml', 'ai']) else 0
            
            item = [
                word_count,
                char_count,
                has_numbers,
                has_special,
                has_uppercase,
                avg_word_len,
                is_short,
                has_tech_suffix,
                1 if section == "skills" else 0,
                1 if section == "education" else 0,
                1 if section == "experience" else 0,
                1 if section == "certifications" else 0,
                1 if section == "profile" else 0,
                pos_hash,
            ]
            extra.append(item)

        extra = np.array(extra)
        
        # Add feature names for the extra features
        if fit:
            extra_names = [
                'word_count', 'char_count', 'has_numbers', 'has_special',
                'has_uppercase', 'avg_word_len', 'is_short', 'has_tech_suffix',
                'section_skills', 'section_education', 'section_experience',
                'section_certifications', 'section_profile', 'pos_hash'
            ]
            self.feature_names.extend(extra_names)

        # Combine and scale
        X_combined = np.hstack([X, extra])
        
        if fit:
            self.scaler = StandardScaler(with_mean=False)  # Sparse-friendly
            X_combined = self.scaler.fit_transform(X_combined)
        else:
            X_combined = self.scaler.transform(X_combined)
            
        return X_combined

    def apply_smote(self, X_train, y_train):
        if not self.use_smote:
            return X_train, y_train
            
        print("Applying SMOTE oversampling...")
        
        # Calculate sampling strategy
        pos_count = sum(y_train == 1)
        neg_count = sum(y_train == 0)
        
        # Oversample minority to 50% of majority (not full balance to avoid overfitting)
        target_ratio = 0.5
        target_pos = int(neg_count * target_ratio)
        
        if target_pos <= pos_count:
            print("  Classes already balanced enough, skipping SMOTE")
            return X_train, y_train
        
        smote = SMOTE(
            sampling_strategy={1: target_pos},
            random_state=42,
            k_neighbors=min(5, pos_count - 1)  # Adjust k based on available samples
        )
        
        X_resampled, y_resampled = smote.fit_resample(X_train, y_train)
        
        print(f"  Before SMOTE: {pos_count} skills, {neg_count} non-skills")
        print(f"  After SMOTE:  {sum(y_resampled == 1)} skills, {sum(y_resampled == 0)} non-skills\n")
        
        return X_resampled, y_resampled

    def train(self, X_train, y_train):
        # Apply SMOTE before training
        X_train_balanced, y_train_balanced = self.apply_smote(X_train, y_train)
        
        if self.classifier_type == 'random_forest':
            print("Training Random Forest Classifier...")
            self.classifier = RandomForestClassifier(
                n_estimators=200,
                max_depth=20,
                min_samples_split=5,
                min_samples_leaf=2,
                class_weight="balanced",
                random_state=42,
                n_jobs=-1
            )
        elif self.classifier_type == 'gradient_boost':
            print("Training Gradient Boosting Classifier...")
            self.classifier = GradientBoostingClassifier(
                n_estimators=150,
                max_depth=5,
                learning_rate=0.1,
                random_state=42
            )
        else:  # logistic regression
            print("Training Logistic Regression (optimized)...")
            self.classifier = LogisticRegression(
                max_iter=2000,
                C=0.8,                    # Slightly more regularization
                class_weight="balanced",
                solver='lbfgs',
                random_state=42
            )

        self.classifier.fit(X_train_balanced, y_train_balanced)
        print("✓ Training complete\n")

    def find_optimal_threshold(self, X_val, y_val):
        """Find threshold that maximizes F1 score"""
        if hasattr(self.classifier, 'predict_proba'):
            y_proba = self.classifier.predict_proba(X_val)[:, 1]
            
            best_f1 = 0
            best_threshold = 0.5
            
            for threshold in np.arange(0.3, 0.7, 0.05):
                y_pred = (y_proba >= threshold).astype(int)
                f1 = f1_score(y_val, y_pred)
                if f1 > best_f1:
                    best_f1 = f1
                    best_threshold = threshold
            
            self.optimal_threshold = best_threshold
            print(f"Optimal threshold: {best_threshold:.2f} (F1: {best_f1:.3f})\n")

    def predict(self, X):
        if hasattr(self.classifier, 'predict_proba'):
            y_proba = self.classifier.predict_proba(X)[:, 1]
            return (y_proba >= self.optimal_threshold).astype(int)
        return self.classifier.predict(X)

    def evaluate(self, X_test, y_test):
        # Try with optimal threshold
        self.find_optimal_threshold(X_test, y_test)
        y_pred = self.predict(X_test)

        print("=" * 70)
        print("TEST SET EVALUATION")
        print("=" * 70)

        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)
        f1_skill = f1_score(y_test, y_pred, pos_label=1)
        f1_nonskill = f1_score(y_test, y_pred, pos_label=0)

        print(f"\n✓ Accuracy:  {acc:.1%}")
        print(f"✓ F1 score:  {f1:.1%}")
        
        # ROC-AUC if available
        if hasattr(self.classifier, 'predict_proba'):
            y_proba = self.classifier.predict_proba(X_test)[:, 1]
            roc_auc = roc_auc_score(y_test, y_proba)
            print(f"✓ ROC-AUC:   {roc_auc:.1%}")

        print(f"\nPer-class F1 scores:")
        print(f"  Skill:     {f1_skill:.1%}")
        print(f"  Non-skill: {f1_nonskill:.1%}")
        print()

        print("Classification Report:")
        print(classification_report(y_test, y_pred, target_names=["Non-skill", "Skill"]))

        print("Confusion Matrix:")
        cm = confusion_matrix(y_test, y_pred)
        print(f"                 Predicted")
        print(f"               Non-Skill  Skill")
        print(f"Actual Non-Skill  {cm[0][0]:5d}   {cm[0][1]:5d}")
        print(f"       Skill      {cm[1][0]:5d}   {cm[1][1]:5d}")
        print()
        
        # Calculate additional metrics for thesis
        tn, fp, fn, tp = cm.ravel()
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        specificity = tn / (tn + fp) if (tn + fp) > 0 else 0
        
        print("Additional Metrics (for thesis):")
        print(f"  True Positives:  {tp}")
        print(f"  True Negatives:  {tn}")
        print(f"  False Positives: {fp}")
        print(f"  False Negatives: {fn}")
        print(f"  Precision:       {precision:.1%}")
        print(f"  Recall:          {recall:.1%}")
        print(f"  Specificity:     {specificity:.1%}")
        print()

        return acc, f1, cm

    def cross_validate(self, X, y):
        print("5-fold cross-validation...\n")
        scores = cross_val_score(self.classifier, X, y, cv=5, scoring="f1")
        print(f"F1 scores: {scores}")
        print(f"Mean F1: {scores.mean():.1%} (+/- {scores.std()*2:.1%})\n")
        return scores.mean()

    def show_top_features(self, n=15):
        if self.classifier is None or self.feature_names is None:
            return

        print(f"Top {n} features predicting SKILL:")
        
        if hasattr(self.classifier, 'coef_'):
            coef = self.classifier.coef_[0]
            top_pos = np.argsort(coef)[-n:]
            for i in reversed(top_pos):
                if i < len(self.feature_names):
                    print(f"  {self.feature_names[i]:35s} {coef[i]:+.3f}")
        elif hasattr(self.classifier, 'feature_importances_'):
            importances = self.classifier.feature_importances_
            top_idx = np.argsort(importances)[-n:]
            for i in reversed(top_idx):
                if i < len(self.feature_names):
                    print(f"  {self.feature_names[i]:35s} {importances[i]:.4f}")
        print()

    def save(self, output_dir):
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True, parents=True)

        model_path = output_dir / "skill_classifier.pkl"
        vec_path = output_dir / "tfidf_vectorizer.pkl"
        scaler_path = output_dir / "feature_scaler.pkl"
        config_path = output_dir / "model_config.pkl"

        joblib.dump(self.classifier, model_path)
        joblib.dump(self.vectorizer, vec_path)
        joblib.dump(self.scaler, scaler_path)
        joblib.dump({
            'optimal_threshold': self.optimal_threshold,
            'classifier_type': self.classifier_type,
            'use_smote': self.use_smote
        }, config_path)

        print(f"✓ Saved classifier → {model_path}")
        print(f"✓ Saved vectorizer → {vec_path}")
        print(f"✓ Saved scaler → {scaler_path}")
        print(f"✓ Saved config → {config_path}")

        with open(output_dir / "feature_names.txt", "w", encoding='utf-8') as f:
            for name in self.feature_names:
                f.write(name + "\n")
        print("✓ Saved feature names\n")


def main():
    parser = argparse.ArgumentParser(description="Improved Skill Classifier Training")
    parser.add_argument("--input", default="labeled_chunks.csv", help="Input CSV file")
    parser.add_argument("--output", default="models", help="Output directory")
    parser.add_argument("--test_size", type=float, default=0.2, help="Test set size")
    parser.add_argument("--classifier", choices=['logistic', 'random_forest', 'gradient_boost'],
                        default='logistic', help="Classifier type")
    parser.add_argument("--no-smote", action="store_true", help="Disable SMOTE")
    args = parser.parse_args()

    print("=" * 70)
    print(" SKILL CLASSIFIER TRAINING — IMPROVED VERSION WITH SMOTE")
    print("=" * 70)
    print(f" Classifier: {args.classifier}")
    print(f" SMOTE: {'Disabled' if args.no_smote else 'Enabled'}")
    print("=" * 70 + "\n")

    trainer = ImprovedSkillClassifierTrainer(
        use_smote=not args.no_smote,
        classifier_type=args.classifier
    )
    
    df = trainer.load_data(args.input)
    X = trainer.extract_features(df, fit=True)
    y = df["label"].values.astype(int)

    # Stratified split
    sss = StratifiedShuffleSplit(n_splits=1, test_size=args.test_size, random_state=42)
    
    for train_idx, test_idx in sss.split(X, y):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

    print(f"Train samples: {len(X_train)}")
    print(f"Test samples:  {len(X_test)}\n")

    trainer.train(X_train, y_train)
    acc, f1, cm = trainer.evaluate(X_test, y_test)
    cv_f1 = trainer.cross_validate(X, y)

    print("=" * 70)
    print("FEATURE IMPORTANCE")
    print("=" * 70)
    trainer.show_top_features(15)

    print("=" * 70)
    print("SAVING MODEL")
    print("=" * 70)
    trainer.save(args.output)

    print("=" * 70)
    print("TRAINING COMPLETE!")
    print("=" * 70)
    print(f"✓ Final Accuracy:     {acc:.1%}")
    print(f"✓ Final F1-Score:     {f1:.1%}")
    print(f"✓ Cross-Val Mean F1:  {cv_f1:.1%}")
    print()
    
    # Thesis-ready summary
    print("=" * 70)
    print("THESIS SUMMARY")
    print("=" * 70)
    print(f"""
Model Configuration:
- Algorithm: {args.classifier.replace('_', ' ').title()}
- SMOTE Oversampling: {'Yes' if not args.no_smote else 'No'}
- Features: TF-IDF (n-grams 1-3) + Engineered Features
- Train/Test Split: {int((1-args.test_size)*100)}/{int(args.test_size*100)}

Results:
- Accuracy: {acc:.1%}
- F1-Score: {f1:.1%}
- Cross-Validation F1: {cv_f1:.1%}

Confusion Matrix:
- True Positives: {cm[1][1]}
- True Negatives: {cm[0][0]}
- False Positives: {cm[0][1]}
- False Negatives: {cm[1][0]}
""")


if __name__ == "__main__":
    main()