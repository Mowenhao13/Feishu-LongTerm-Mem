from _common import list_decisions, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--top-k", type=int, default=50)
args = parser.parse_args()
print(list_decisions(top_k=args.top_k))