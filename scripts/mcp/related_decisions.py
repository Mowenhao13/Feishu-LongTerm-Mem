from _common import related_decisions, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid")
args = parser.parse_args()
print(related_decisions(sid=args.sid))