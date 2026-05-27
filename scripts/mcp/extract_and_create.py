from _common import extract_and_create, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--text", required=True)
parser.add_argument("--topic-id", default="general")
args = parser.parse_args()
print(extract_and_create(text=args.text, topic_id=args.topic_id))