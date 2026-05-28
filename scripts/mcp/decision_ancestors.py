from _common import decision_ancestors, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid")
args = parser.parse_args()
print(decision_ancestors(sid=args.sid))