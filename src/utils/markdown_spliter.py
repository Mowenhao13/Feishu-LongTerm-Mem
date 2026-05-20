from langchain_text_splitters import MarkdownHeaderTextSplitter
from typing import List 

# 定义你想依据哪些标题进行章节切分
headers_to_split_on = [
    ("#", "Header 1"),
    ("##", "Header 2"),
    ("###", "Header 3"),
]

class MarkdownSplitter:
    def __init__(self):
        self.splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
        
    def page_content(self, document: str) -> List[str]:
        chunks = self.splitter.split_text(document)
        for chunk in chunks:
            return chunk.page_content
        
    def meta_data(self, document: str) -> List[str]:
        chunks = self.splitter.split_text(document)
        for chunk in chunks:
            return chunk.metadata


