from _common import conflict_list, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--top-k", type=int, default=20)
args = parser.parse_args()
print(conflict_list(top_k=args.top_k))