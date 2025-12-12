"""
Interactive Labeling Tool for Skill Classification
Enhanced terminal interface with:
- Undo
- Jump-to-index
- Skipped-chunk handling
- Shuffling
- Safer unicode handling
- Faster saving
- Balance warnings
- ENTER to repeat last action
- Fuzzy chunk_id matching
"""

import pandas as pd
import sys
from pathlib import Path
import argparse
import os
import random

class LabelingTool:
    def __init__(self, input_file, output_file):
        self.input_file = input_file
        self.output_file = output_file
        self.df = None
        self.history = []      # Stack for undo
        self.row_order = []    # Random shuffled index list
        self.current_pos = 0   # Pointer inside shuffled order
        self.last_action = None  # Track last label for repeat

    # ---------------------------------------------------------
    # Loading & Setup
    # ---------------------------------------------------------
    def load_data(self):
        if not Path(self.input_file).exists():
            print(f"[!] Input file not found: {self.input_file}")
            sys.exit(1)

        df = pd.read_csv(self.input_file)

        # If output exists, merge previous labels
        if Path(self.output_file).exists():
            print("[i] Resuming existing labeling...")
            labeled_df = pd.read_csv(self.output_file)

            df = df.merge(
                labeled_df[['chunk_id', 'label']],
                on='chunk_id',
                how='left',
                suffixes=('', '_saved')
            )

            df['label'] = df['label_saved'].combine_first(df['label'])
            df = df.drop(columns=['label_saved'])

        # Shuffle once
        self.row_order = list(df.index)
        random.shuffle(self.row_order)

        self.df = df
        print(f"[i] Loaded {len(df)} chunks")
        
        # IMPROVEMENT #1: Check balance
        self.check_balance()
        print()

    # ---------------------------------------------------------
    def check_balance(self):
        """Warn if dataset is imbalanced"""
        labeled = self.df[self.df['label'].notna()]
        if len(labeled) == 0:
            return
        
        pos = (labeled['label'] == 1).sum()
        neg = (labeled['label'] == 0).sum()
        
        print()
        print(f"Current balance: {pos} skills, {neg} non-skills")
        
        if pos < 50 or neg < 50:
            print("[!] WARNING: Dataset is imbalanced!")
            print("    Recommend at least 100 of each class for good training.")
        elif pos < 100 or neg < 100:
            print("[i] Balance is OK, but more labels would improve accuracy.")
        else:
            print("✓ Good balance!")

    # ---------------------------------------------------------
    def clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    # ---------------------------------------------------------
    def show_progress(self):
        total = len(self.df)
        labeled = self.df['label'].notna().sum()
        pct = (labeled / total) * 100 if total else 0

        print("="*70)
        print(f"LABELING PROGRESS: {labeled}/{total} ({pct:.1f}%)")
        print("="*70)
        print()

    # ---------------------------------------------------------
    def show_chunk(self, idx):
        row = self.df.loc[idx]

        print(f"Chunk: {row['chunk_id']}   | Source: {row['source_file']}")
        print(f"Section: {row['section']} | Words: {row['word_count']} | Chars: {row['char_count']}")
        print("-"*70)
        print(row['text'])
        print("-"*70)
        print()

        # Helpful contextual hints
        if row['section'] == 'skills':
            print("💡 Likely a skill (comes from SKILLS section).")
        elif row['section'] in ["publications", "research"]:
            print("💡 Publications are almost never skills.")
        elif row['section'] == "education":
            print("💡 Education section usually contains degrees, not skills.")
        elif row['section'] == "unknown":
            print("💡 Review carefully — could be skill OR garbage.")

        # IMPROVEMENT #2: Show repeat hint
        if self.last_action is not None:
            action_name = "SKILL" if self.last_action == 1 else "NON-SKILL"
            print(f"[↵ Press ENTER to repeat: {action_name}]")

        print()

    # ---------------------------------------------------------
    def save(self):
        """Lightweight save — only writes relevant columns."""
        out_df = self.df[['chunk_id', 'text', 'section', 'pos_pattern',
                          'word_count', 'char_count', 'has_digit',
                          'has_special', 'label']]

        out_df.to_csv(self.output_file, index=False)
        print(f"[✓] Saved to {self.output_file}")

    # ---------------------------------------------------------
    def undo_last(self):
        if not self.history:
            print("[!] Nothing to undo.")
            return

        idx, old_label = self.history.pop()
        self.df.at[idx, 'label'] = old_label
        self.current_pos -= 1  # Move back one position
        self.last_action = None  # Clear repeat action
        print("↺ Undid last label.")

    # ---------------------------------------------------------
    def jump_to(self):
        """IMPROVEMENT #3: Fuzzy matching for chunk_id"""
        try:
            target = input("Enter chunk_id to jump to: ").strip()
            row = self.df[self.df['chunk_id'] == target]
            
            if row.empty:
                # Try fuzzy match
                all_ids = self.df['chunk_id'].tolist()
                matches = [cid for cid in all_ids if target in str(cid)]
                
                if matches:
                    print(f"[!] No exact match. Did you mean one of these?")
                    for m in matches[:5]:
                        print(f"    - {m}")
                else:
                    print("[!] No such chunk_id found.")
                return

            new_idx = row.index[0]
            
            # Move pointer to this position in shuffled order
            self.current_pos = self.row_order.index(new_idx)
            print(f"→ Jumped to {target}")
        except Exception as e:
            print(f"[!] Jump failed: {e}")

    # ---------------------------------------------------------
    def run(self):
        print("="*70)
        print(" SKILL LABELING TOOL — Enhanced Version")
        print("="*70)
        print("Commands:")
        print("  1 = Yes (skill)")
        print("  0 = No (not skill)")
        print("  ENTER = Repeat last action")
        print("  s = Skip")
        print("  u = Undo")
        print("  j = Jump to chunk")
        print("  h = Help")
        print("  q = Quit")
        print("="*70)
        input("Press Enter to begin...")

        while self.current_pos < len(self.row_order):
            idx = self.row_order[self.current_pos]
            row = self.df.loc[idx]

            if pd.notna(row['label']):
                self.current_pos += 1
                continue

            self.clear_screen()
            self.show_progress()
            self.show_chunk(idx)

            cmd = input("Label? ").strip().lower()

            # IMPROVEMENT #2: ENTER repeats last action
            if cmd == '' and self.last_action is not None:
                self.history.append((idx, row['label']))
                self.df.at[idx, 'label'] = self.last_action
                self.current_pos += 1
                continue

            if cmd in ['1', 'y', 'yes']:
                self.history.append((idx, row['label']))
                self.df.at[idx, 'label'] = 1
                self.last_action = 1
                self.current_pos += 1

            elif cmd in ['0', 'n', 'no']:
                self.history.append((idx, row['label']))
                self.df.at[idx, 'label'] = 0
                self.last_action = 0
                self.current_pos += 1

            elif cmd == 's':
                # Don't store "skip" as string - leave as NaN
                self.current_pos += 1

            elif cmd == 'u':
                self.undo_last()
                input("Press Enter...")

            elif cmd == 'j':
                self.jump_to()
                input("Press Enter...")

            elif cmd == 'h':
                self.show_help()
                input("Press Enter...")

            elif cmd == 'q':
                self.save()
                print("\nExiting…")
                return

            # Auto-save every 25 chunks processed
            if self.current_pos > 0 and self.current_pos % 25 == 0:
                self.save()
                self.check_balance()  # Show updated balance
                print("[i] Auto-saved progress.")
                input("Press Enter...")

        # End of loop: save everything
        self.save()
        self.check_balance()
        print("\n✓ Labeling complete!")

    # ---------------------------------------------------------
    def show_help(self):
        self.clear_screen()
        print("="*70)
        print("HELP — HOW TO LABEL")
        print("="*70)
        print("What IS a skill:")
        print("  ✓ Python, Java, SQL")
        print("  ✓ Machine Learning")
        print("  ✓ Data Analysis")
        print("  ✓ Network Security")
        print("  ✓ Communication, Teamwork")
        print()
        print("What is NOT a skill:")
        print("  ✗ Journal titles")
        print("  ✗ Research topics")
        print("  ✗ Job titles")
        print("  ✗ Course titles")
        print("  ✗ Broken text fragments")
        print()
        print("Commands:")
        print("  1 / yes    = skill")
        print("  0 / no     = not skill")
        print("  ENTER      = repeat last label")
        print("  s          = skip this chunk")
        print("  u          = undo last label")
        print("  j          = jump to chunk ID")
        print("  q          = save & quit")
        print("  h          = this help menu")
        print("="*70)
        print()


# ---------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='chunks_dataset.csv')
    parser.add_argument('--output', default='labeled_chunks.csv')

    args = parser.parse_args()
    tool = LabelingTool(args.input, args.output)
    tool.load_data()
    tool.run()


if __name__ == "__main__":
    main()