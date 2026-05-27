from _common import git_search, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("query")
args = parser.parse_args()
print(git_search(query=args.query))