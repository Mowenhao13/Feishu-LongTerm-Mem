from _common import timeline, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--top-k", type=int, default=50)
args = parser.parse_args()
print(timeline(top_k=args.top_k))