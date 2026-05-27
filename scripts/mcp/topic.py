from _common import topic, json
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--topic-id", default="")
parser.add_argument("--top-k", type=int, default=50)
args = parser.parse_args()
print(topic(topic_id=args.topic_id, top_k=args.top_k))