from _common import hot_decisions, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--min-score", type=float, default=50.0)
parser.add_argument("--top-k", type=int, default=10)
args = parser.parse_args()
print(hot_decisions(min_score=args.min_score, top_k=args.top_k))