from _common import extract_decision, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--text", required=True)
args = parser.parse_args()
print(extract_decision(text=args.text))