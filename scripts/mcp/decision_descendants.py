from _common import decision_descendants, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid")
args = parser.parse_args()
print(decision_descendants(sid=args.sid))