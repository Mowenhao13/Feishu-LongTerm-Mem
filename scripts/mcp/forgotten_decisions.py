from _common import forgotten_decisions, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--max-score", type=float, default=30.0)
parser.add_argument("--top-k", type=int, default=10)
args = parser.parse_args()
print(forgotten_decisions(max_score=args.max_score, top_k=args.top_k))