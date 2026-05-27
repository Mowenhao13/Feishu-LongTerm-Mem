from _common import git_history, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--limit", type=int, default=20)
args = parser.parse_args()
print(git_history(limit=args.limit))