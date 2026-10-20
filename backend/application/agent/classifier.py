"""意图识别节点：优先用 LLM 结构化输出，失败/演示模式退回规则。"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from backend.domain.intent import IntentResult, rule_classify
from backend.infrastructure.config import settings

CLASSIFIER_PROMPT = """你是电商客服系统的意图分类器。把用户消息分到以下四类之一：

- knowledge：帮助中心能回答的规则/流程/政策咨询，例如退款到账时间、发票怎么开、物流规则。
- query：查询具体订单，例如「我的订单到哪了」「查订单 SO202610210001」「帮我查询张三的订单」。
- service：需要对具体订单做售后/业务办理，例如商品损坏要退换、维修、投诉处理、补发。
- fallback：闲聊、问候、明确要求转人工、与电商无关的话题。

只输出 JSON 对象：{"intent": "...", "confidence": 0-1, "reason": "简短依据", "slots": {"order_no": "...", "keyword": "..."}}。
不要输出 Markdown。订单号形如 SO202610210001。"""


def classify_intent(question: str, llm: BaseChatModel) -> IntentResult:
    if settings.mock_mode:
        return rule_classify(question)
    try:
        structured = llm.with_structured_output(IntentResult)
        result = structured.invoke(
            [SystemMessage(content=CLASSIFIER_PROMPT), HumanMessage(content=question)]
        )
        if isinstance(result, IntentResult):
            return result
        if isinstance(result, dict):
            return IntentResult(**result)
        return rule_classify(question)
    except Exception:
        # 分类失败不能卡住整轮对话：用规则兜底
        return rule_classify(question)
