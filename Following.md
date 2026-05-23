## 1. 模型注册器封装

在src/model/model.py 创建全局模型注册器 ModelProvider

ModelRegister分为LLMProvider, EmbeddingProvider, RerankerProvider



参考ref/lark-adapter里的lark_doc.go 新建doc提取器 使用飞书api进行轮询 加入防抖机制 将轮询频率与防抖机制参数写入.env文件 并加载 在prompts里加入专门针对文档决策管理的prompt 决策管理与lark_im一致 但决策去重，冲突判断，更新逻辑要针对文档结构进行调整（在test里测试） 当前可以先不用飞书api实现 在注释里加入TODO（作为未来拓展）当前阶段先使用读取本地文件的形式来做模拟 每当文档发生变化都进行决策提取 针对多文档和单文档