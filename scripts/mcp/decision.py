from _common import decision, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid")
args = parser.parse_args()
print(decision(sid=args.sid))