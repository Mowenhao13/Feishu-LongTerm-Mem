from _common import get_relations, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid")
args = parser.parse_args()
print(get_relations(sid=args.sid))