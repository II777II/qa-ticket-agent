"""工厂层：按配置创建可替换的实现。

每个工厂都只做「读配置 -> 返回抽象接口」，业务代码拿到的是
BaseChatModel / BaseCheckpointSaver / BaseRetriever 这些标准接口，
所以把 MemorySaver 换成 PostgresSaver 不需要动业务代码。
"""
