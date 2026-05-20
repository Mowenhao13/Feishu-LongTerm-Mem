from dataclasses import dataclass
from typing import List 
import json

import lark_oapi as lark
from lark_oapi.api.im.v1 import *

@dataclass
class AdapterConfig:
    app_id: str 
    app_secret: str 
    card_chat_ids: List[str]
    group_chat_ids: List[str]
    user_id: str 

    def is_configured(self) -> bool:
        return self.app_id != "" and self.app_secret != ""
    
@dataclass
class AdapterClient:
    def __init__(self, config: AdapterConfig):
        self.log_level = lark.LogLevel.DEBUG 
        self.config = config 
        self.client = lark.Client.builder() \
            .app_id(self.config.app_id) \
            .app_secret(self.config.app_secret) \
            .log_level(self.log_level) \
            .build()
    