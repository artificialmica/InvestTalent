"""
Skill Classifier Training Script
Optimized version with:
- Enhanced TF-IDF (1500 features, 1–3 ngrams)
- POS-pattern embedding (normalized to [0,1])
- Logistic Regression tuned (C=1.5)
- StratifiedShuffleSplit for stable splits
- Cleaned feature engineering
- Per-class F1 metrics
- Column validation
"""

import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedShuffleSplit, cross_val_score
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
    f1_score
)
import joblib
from pathlib import Path
import argparse
import sys


# ======================================================
# Trainer Class
# ======================================================

class SkillClassifierTrainer:
    def __init__(self):
        self.vectorizer = None
        self.classifier = None
        self.feature_names = None

    # ---------------------------------------------
    def load_data(self, filepath):
        if not Path(filepath).exists():
            print(f"[!] Error: Input file not found: {filepath}")
            sys.exit(1)

        df = pd.read_csv(filepath)

        # Only use labeled rows
        df = df[df['label'].notna()].copy()

        if len(df) == 0:
            print("[!] No labeled data! Run label_tool.py first.")
            sys.exit(1)

        print(f"[i] Loaded {len(df)} labeled chunks\n")

        # Class distribution
        pos = (df['label'] == 1).sum()
        neg = (df['label'] == 0).sum()

        print("Class distribution:")
        print(f"  Skill (1):     {pos} ({pos/len(df)*100:.1f}%)")
        print(f"  Non-skill (0): {neg} ({neg/len(df)*100:.1f}%)\n")

        if pos < 50 or neg < 50:
            print("[!] Warning: Class imbalance. Try labeling more samples.\n")

        return df

    # ---------------------------------------------
    def extract_features(self, df, fit=True):
        # IMPROVEMENT #2: Validate required columns exist
        required_cols = ["text", "word_count", "char_count", "has_digit", 
                         "has_special", "section", "pos_pattern"]
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            print(f"[!] ERROR: Missing columns in dataset: {missing}")
            print(f"    Make sure you're using data from extract_chunks.py")
            sys.exit(1)
        
        texts = df["text"].values

        # TF-IDF vectorizer
        if fit:
            self.vectorizer = TfidfVectorizer(
                max_features=1500,        # Increased for better vocab coverage
                ngram_range=(1, 3),
                min_df=2,
                max_df=0.9,
                strip_accents="unicode",
                lowercase=True,
                token_pattern=r"\b\w+\b"
            )
            X_tfidf = self.vectorizer.fit_transform(texts)
            self.feature_names = self.vectorizer.get_feature_names_out()

        else:
            X_tfidf = self.vectorizer.transform(texts)

        X = X_tfidf.toarray()

        # ---------------------------------------------
        # Additional numeric & categorical engineered features
        # ---------------------------------------------
        extra = []

        for _, row in df.iterrows():

            # Hash POS pattern to 0-999 range, then normalize to [0, 1]
            # Example: "NOUN-NOUN" → 347 → 0.347
            # Captures syntactic structure differences between skills and non-skills
            # Skills tend to be "NOUN" or "NOUN-NOUN", garbage is "ADJ-NOUN-NOUN-VERB"
            # IMPROVEMENT #1: Normalized to [0,1] for better Logistic Regression convergence
            pos_hash = (hash(row["pos_pattern"]) % 1000) / 1000.0

            item = [
                row["word_count"],
                row["char_count"],
                int(row["has_digit"]),
                int(row["has_special"]),
                1 if row["section"] == "skills" else 0,
                1 if row["section"] == "publications" else 0,
                1 if row["section"] == "experience" else 0,
                pos_hash,                        # POS embedding (normalized)
            ]
            extra.append(item)

        extra = np.array(extra)

        # Combine TF-IDF + engineered features
        return np.hstack([X, extra])

    # ---------------------------------------------
    def train(self, X_train, y_train):
        print("Training Logistic Regression (C=1.5)...\n")

        self.classifier = LogisticRegression(
            max_iter=1000,
            C=1.5,                    # Slightly stronger regularization
            class_weight="balanced",  # Handles imbalance
            random_state=42
        )

        self.classifier.fit(X_train, y_train)
        print("✓ Training complete\n")

    # ---------------------------------------------
    def evaluate(self, X_test, y_test):
        y_pred = self.classifier.predict(X_test)

        print("="*70)
        print("TEST SET EVALUATION")
        print("="*70)

        acc = accuracy_score(y_test, y_pred)
        f1 = f1_score(y_test, y_pred)

        print(f"\nAccuracy:  {acc:.3f}")
        print(f"F1 score:  {f1:.3f}\n")

        # Show per-class F1 scores
        f1_skill = f1_score(y_test, y_pred, pos_label=1)
        f1_nonskill = f1_score(y_test, y_pred, pos_label=0)

        print("Per-class F1 scores:")
        print(f"  Skill:     {f1_skill:.3f}")
        print(f"  Non-skill: {f1_nonskill:.3f}")
        print()

        print("Classification Report:")
        print(classification_report(y_test, y_pred, target_names=["Non-skill", "Skill"]))

        print("Confusion Matrix:")
        cm = confusion_matrix(y_test, y_pred)
        print(f"                Predicted")
        print(f"              Non-Skill  Skill")
        print(f"Actual Non-Skill  {cm[0][0]:4d}    {cm[0][1]:4d}")
        print(f"       Skill      {cm[1][0]:4d}    {cm[1][1]:4d}")
        print()

        return acc, f1

    # ---------------------------------------------
    def cross_validate(self, X, y):
        print("5-fold cross-validation…\n")
        scores = cross_val_score(self.classifier, X, y, cv=5, scoring="f1")
        print("F1 scores:", scores)
        print(f"Mean F1: {scores.mean():.3f} (+/- {scores.std()*2:.3f})\n")

    # ---------------------------------------------
    def show_top_features(self, n=20):
        if self.classifier is None:
            return

        coef = self.classifier.coef_[0]

        print(f"Top {n} features predicting SKILL:")
        top_pos = np.argsort(coef)[-n:]
        for i in reversed(top_pos):
            if i < len(self.feature_names):
                print(f"  {self.feature_names[i]:30s} {coef[i]:+.3f}")
        print()

        print(f"Top {n} NON-skill indicators:")
        top_neg = np.argsort(coef)[:n]
        for i in top_neg:
            if i < len(self.feature_names):
                print(f"  {self.feature_names[i]:30s} {coef[i]:+.3f}")
        print()

    # ---------------------------------------------
    def save(self, output_dir):
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True, parents=True)

        model_path = output_dir / "skill_classifier.pkl"
        vec_path = output_dir / "tfidf_vectorizer.pkl"

        joblib.dump(self.classifier, model_path)
        joblib.dump(self.vectorizer, vec_path)

        print(f"✓ Saved classifier → {model_path}")
        print(f"✓ Saved vectorizer → {vec_path}")

        # Save features for inspection
        with open(output_dir / "feature_names.txt", "w") as f:
            for name in self.feature_names:
                f.write(name + "\n")

        print("✓ Saved feature names\n")


# ======================================================
# Main Execution
# ======================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="labeled_chunks.csv")
    parser.add_argument("--output", default="models")
    parser.add_argument("--test_size", type=float, default=0.2)
    args = parser.parse_args()

    print("="*70)
    print(" SKILL CLASSIFIER TRAINING — OPTIMIZED VERSION")
    print("="*70)

    trainer = SkillClassifierTrainer()
    df = trainer.load_data(args.input)

    X = trainer.extract_features(df, fit=True)
    y = df["label"].values

    # ---------------------------------------------
    # Improved and stable dataset split
    # ---------------------------------------------
    sss = StratifiedShuffleSplit(
        n_splits=1,
        test_size=args.test_size,
        random_state=42
    )

    for train_idx, test_idx in sss.split(X, y):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

    print(f"\nTrain samples: {len(X_train)}")
    print(f"Test samples:  {len(X_test)}\n")

    trainer.train(X_train, y_train)
    acc, f1 = trainer.evaluate(X_test, y_test)
    trainer.cross_validate(X, y)

    print("="*70)
    print("FEATURE IMPORTANCE")
    print("="*70)
    trainer.show_top_features(15)

    print("="*70)
    print("SAVING MODEL")
    print("="*70)
    trainer.save(args.output)

    print("="*70)
    print("TRAINING COMPLETE!")
    print("="*70)
    print(f"Final Accuracy: {acc:.1%}")
    print(f"Final F1-Score: {f1:.1%}\n")


if __name__ == "__main__":
    main()