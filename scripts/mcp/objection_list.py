from _common import objection_list, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--topic-id", default="general")
args = parser.parse_args()
print(objection_list(topic_id=args.topic_id))