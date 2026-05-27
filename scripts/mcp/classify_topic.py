from _common import classify_topic, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("sid")
parser.add_argument("topic_id")
args = parser.parse_args()
print(classify_topic(sid=args.sid, topic_id=args.topic_id))