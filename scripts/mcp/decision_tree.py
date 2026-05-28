from _common import decision_tree, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid")
args = parser.parse_args()
print(decision_tree(sid=args.sid))