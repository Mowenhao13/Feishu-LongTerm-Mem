TABLE_NAME = "决策列表"

FIELD_DECISION_ID  = "决策ID"
FIELD_TOPIC        = "决策主题"
FIELD_VERSION      = "决策版本"
FIELD_STATUS       = "决策状态"
FIELD_TITLE        = "决策标题"
FIELD_CONTENT      = "决策内容"
FIELD_ASSIGNEE     = "决策关联人"
FIELD_CREATED_AT   = "决策提出时间"
FIELD_HOT_SCORE    = "决策热点值"
FIELD_CONFLICT_SID = "冲突关联决策"
FIELD_PARENT = "父决策"

ALL_FIELD_NAMES = [
    FIELD_DECISION_ID, FIELD_TOPIC, FIELD_VERSION,
    FIELD_STATUS, FIELD_TITLE, FIELD_CONTENT,
    FIELD_ASSIGNEE, FIELD_CREATED_AT, FIELD_HOT_SCORE,
    FIELD_CONFLICT_SID, FIELD_PARENT,
]

STATUS_OPTIONS = [
    {"name": "pending",       "color": 2},
    {"name": "in_discussion", "color": 2},
    {"name": "decided",       "color": 0},
    {"name": "executing",     "color": 7},
    {"name": "completed",     "color": 10},
    {"name": "superseded",    "color": 4},
    {"name": "deprecated",    "color": 4},
    {"name": "shelved",       "color": 1},
    {"name": "rejected",      "color": 4},
    {"name": "conflict",      "color": 3},
]