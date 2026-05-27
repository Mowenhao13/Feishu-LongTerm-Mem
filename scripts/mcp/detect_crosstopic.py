from _common import detect_crosstopic, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid")
args = parser.parse_args()
print(detect_crosstopic(sid=args.sid))