from _common import recent_decisions, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--hours", type=int, default=24)
parser.add_argument("--top-k", type=int, default=20)
args = parser.parse_args()
print(recent_decisions(hours=args.hours, top_k=args.top_k))