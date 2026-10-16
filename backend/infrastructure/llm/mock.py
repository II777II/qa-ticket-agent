"""演示模式（mock）模型。

存在的意义：没有 API Key、或者现场没有外网时，整条链路（前端 -> SSE -> LangGraph
-> 模型）依然能跑通并演示。它刻意做得很"笨"：只在回答里明确标注这是占位内容，
免得演示时把假数据当成真实模型输出。

阶段二起它还负责模拟工具调用：识别到「建单 / 查进度 / 转人工」的意图就先返回
tool_calls，拿到工具结果后再用自然语言复述结论——没有 Key 也能演示完整闭环。
真实模型换上来时，这段规则判断会被模型自己的意图识别替代，其余代码不用动。

阶段四起它会读系统提示里的【参考资料】块：检索命中时基于资料作答并标出 [1][2]，
这样 RAG 链路（检索 → 注入 → 引用回传）在没有 Key 的演示模式下也是真的。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any, Iterator, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from pydantic import Field

from backend.infrastructure.retrieval.in_memory import CONTEXT_FOOTER, CONTEXT_HEADER

TEMPLATE = """【演示模式】当前没有可用的模型 API Key，这是一段占位回答，用来验证链路是否通畅。

你刚才问的是：{question}

链路检查：前端 -> FastAPI /chat (SSE) -> LangGraph agent 节点 -> 模型。
把 .env 里的 LLM_PROVIDER 改成 deepseek 或 openai 并填好 Key，这里就会替换成真实模型的流式输出。"""

CREATE_HINTS = ("建单", "建个工单", "创建工单", "提交工单", "报修", "提个工单", "开个单", "帮我建", "帮我提")
QUERY_HINTS = ("工单进度", "查询工单", "查工单", "我的工单", "工单状态", "处理到哪", "催单", "催一下", "进度怎么样")
ESCALATE_HINTS = ("转人工", "人工客服", "找人工", "转工程师", "叫工程师")

TICKET_ID_RE = re.compile(r"TK-\d{8}-\d{4}")
CONTACT_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\b[A-Za-z]{1,4}\d{3,6}\b")

DEFAULT_CONTACT = "演示用户"


def _chunks(text: str, size: int = 6) -> Iterator[str]:
    for index in range(0, len(text), size):
        yield text[index : index + size]


def _hit(text: str, hints: Sequence[str]) -> bool:
    return any(hint in text for hint in hints)


def _last_human_text(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return _as_text(message.content)
    return ""


def _called_this_turn(messages: Sequence[BaseMessage], name: str | None = None) -> bool:
    """这一轮（最后一条用户消息之后）是否已经调用过工具。

    只看最近一轮，有两个原因：
    1. 让「再帮我建一张工单」不会被历史里的建单调用挡住；
    2. 一轮只调一个工具，避免「转人工之后又自动追一次查询」这种噪声——
       工具执行完就该让模型组织语言回答用户了。
    """
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return False
        if isinstance(message, ToolMessage) and (name is None or message.name == name):
            return True
        if isinstance(message, AIMessage) and message.tool_calls:
            if name is None or any(call.get("name") == name for call in message.tool_calls):
                return True
    return False


def _guess_category(text: str) -> str:
    """按命中关键词的个数打分取最高，比「先匹配到谁算谁」稳一点。"""
    rules = (
        ("账号与权限", ("密码", "账号", "权限", "锁定", "登录不上", "登不上", "重置")),
        ("网络与VPN", ("vpn", "VPN", "网络", "断网", "连不上", "上不了网", "wifi", "WiFi", "代理", "内网")),
        ("办公设备", ("打印机", "打印不了", "显示屏", "显示器", "键盘", "鼠标", "电脑", "蓝屏", "开机")),
        ("邮件与协作", ("邮箱", "邮件", "outlook", "Outlook", "企业微信", "teams", "Teams", "会议")),
        ("业务系统", ("erp", "ERP", "crm", "CRM", "oa", "OA", "门户", "业务系统")),
    )
    best_category, best_score = "其他", 0
    for category, keywords in rules:
        score = sum(1 for keyword in keywords if keyword in text)
        if score > best_score:
            best_category, best_score = category, score
    return best_category


def _clean_title(text: str) -> str:
    """把「帮我建个工单，整个部门都连不上，联系我 a@b.com」压成一句问题描述。"""
    title = text
    for hint in CREATE_HINTS:
        title = title.replace(hint, "")
    title = CONTACT_RE.sub(" ", title)
    # 联系人被摘掉后常留下「（工号 ）」这类空壳，一并清掉
    title = re.sub(r"[（(]\s*(工号|邮箱|电话|联系人)?\s*[)）]", " ", title)
    title = re.sub(r"(联系我|联系人|我的邮箱是|邮箱是|工号是|电话是|工号|邮箱|电话)", " ", title)
    title = re.sub(r"^\s*(帮我|帮忙|麻烦|请|给我|我要|我想)+[，,。；;、:：\s]*", "", title)
    title = re.sub(r"[，,。；;、！!？?：:\s]+", " ", title).strip()
    return (title or text)[:40]


def _guess_priority(text: str) -> str:
    if _hit(text, ("全部", "全员", "整个部门", "没法办公", "无法办公", "瘫痪", "中断", "紧急", "马上")):
        return "紧急"
    if _hit(text, ("多人", "部门", "同事都", "好几个")):
        return "高"
    if _hit(text, ("咨询", "问问", "优化", "建议")):
        return "低"
    return "中"


def _guess_contact(text: str) -> str:
    match = CONTACT_RE.search(text)
    if not match:
        return DEFAULT_CONTACT
    return match.group(0)


def _tool_call(name: str, args: dict[str, Any]) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_mock_{name}", "type": "tool_call"}])


def _context_documents(messages: Sequence[BaseMessage]) -> list[tuple[str, str]]:
    """从系统提示里抽出【参考资料】块，返回 [(标注行, 正文), ...]。"""
    for message in messages:
        if not isinstance(message, SystemMessage):
            continue
        text = _as_text(message.content)
        if CONTEXT_HEADER not in text:
            continue
        block = text.split(CONTEXT_HEADER, 1)[1].split(CONTEXT_FOOTER, 1)[0]
        documents: list[tuple[str, str]] = []
        head, buffer = "", []
        for line in block.splitlines():
            if line.startswith("[") and "]" in line:
                if head:
                    documents.append((head, "\n".join(buffer).strip()))
                head, buffer = line.strip(), []
            elif line.strip():
                buffer.append(line.strip())
        if head:
            documents.append((head, "\n".join(buffer).strip()))
        return documents
    return []


def _condense(text: str, limit: int = 160) -> str:
    """把命中片段压成几行，模拟模型「读完资料再总结」的效果。"""
    cleaned = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if len(cleaned) <= limit:
        return cleaned
    cut = cleaned[:limit]
    for mark in ("。", "；", "！", ". ", ";"):
        position = cut.rfind(mark)
        if position > limit // 2:
            return cut[: position + 1]
    return cut + "…"


class FakeChatModel(BaseChatModel):
    """零依赖假模型：不做推理，只按关键词模拟「回答 / 调工具」两种行为。"""

    delay: float = Field(default=0.01, description="每个 chunk 之间的间隔，让流式效果可见")
    bound_tools: list[Any] = Field(default_factory=list, description="bind_tools 传进来的工具，用它判断能模拟哪些调用")

    @property
    def _llm_type(self) -> str:
        return "fake-chat-model"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "FakeChatModel":
        """让 mock 也能被 bind_tools 装饰，这样图结构和真实模型完全一致。"""
        return self.model_copy(update={"bound_tools": list(tools or [])})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        plan = self._plan(messages)
        if plan is not None:
            return ChatResult(generations=[ChatGeneration(message=plan)])
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self._compose(messages)))])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        plan = self._plan(messages)
        if plan is not None:
            # 工具调用也走「流式」通道，形状与真实模型一致：只有 tool_call_chunks，没有正文
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "name": plan.tool_calls[0]["name"],
                            "args": json.dumps(plan.tool_calls[0]["args"], ensure_ascii=False),
                            "id": plan.tool_calls[0]["id"],
                            "index": 0,
                            "type": "tool_call_chunk",
                        }
                    ],
                )
            )
            return

        for piece in _chunks(self._compose(messages)):
            if self.delay:
                time.sleep(self.delay)
            yield ChatGenerationChunk(message=AIMessageChunk(content=piece))

    # ---------------- 意图 -> 工具调用 ----------------
    def _plan(self, messages: list[BaseMessage]) -> AIMessage | None:
        """根据用户这句话决定要不要调工具；返回 None 表示直接回答。"""
        available = {getattr(tool, "name", None) for tool in self.bound_tools}
        if not available:
            return None

        question = _last_human_text(messages)
        if not question:
            return None

        if _called_this_turn(messages):
            # 这一轮已经调过工具了，接下来该由模型组织语言回答，而不是继续调工具
            return None

        ticket_id = TICKET_ID_RE.search(question)
        contact = _guess_contact(question)
        if contact == DEFAULT_CONTACT:
            # 本轮没给联系人，就翻历史（这正是多轮记忆的用处之一）
            contact = self._history_contact(messages)

        if "escalate_to_human" in available and _hit(question, ESCALATE_HINTS) and ticket_id:
            return _tool_call("escalate_to_human", {"ticket_id": ticket_id.group(0), "reason": question[:120]})

        if "create_ticket" in available and _hit(question, CREATE_HINTS):
            return _tool_call(
                "create_ticket",
                {
                    "title": _clean_title(question),
                    "description": question,
                    "category": _guess_category(question),
                    "priority": _guess_priority(question),
                    "contact": contact,
                },
            )

        if "query_ticket" in available and (_hit(question, QUERY_HINTS) or ticket_id):
            args: dict[str, Any] = {}
            if ticket_id:
                args["ticket_id"] = ticket_id.group(0)
            else:
                args["contact"] = contact
            if "催" in question:
                args["urge"] = True
            return _tool_call("query_ticket", args)

        return None

    @staticmethod
    def _history_contact(messages: Sequence[BaseMessage]) -> str:
        """本轮没给联系人时，翻一遍历史（多轮记忆的用处之一）。"""
        for message in reversed(messages):
            if isinstance(message, HumanMessage):
                found = CONTACT_RE.search(_as_text(message.content))
                if found:
                    return found.group(0)
        return DEFAULT_CONTACT

    def _compose(self, messages: list[BaseMessage]) -> str:
        last = messages[-1] if messages else None
        if isinstance(last, ToolMessage):
            return self._compose_after_tool(last)

        question = _last_human_text(messages)
        if not question:
            if isinstance(last, SystemMessage):
                return "【演示模式】收到系统提示，但还没有用户问题。"
            return TEMPLATE.format(question="(空)")

        if _hit(question, ESCALATE_HINTS) and not TICKET_ID_RE.search(question):
            return (
                "【演示模式】可以帮你转人工，把工单号发我就行（形如 TK-20261016-0001）；"
                "还没有工单的话，说一声我先帮你建一张。"
            )

        documents = _context_documents(messages)
        if documents:
            return self._compose_from_context(question, documents)

        return TEMPLATE.format(question=question)

    @staticmethod
    def _compose_from_context(question: str, documents: list[tuple[str, str]]) -> str:
        """基于检索到的资料作答——真实模型做的就是这件事。"""
        parts = []
        for head, body in documents:
            label = head.split("]")[0].lstrip("[")
            title = head.split("]", 1)[-1].strip()
            # 用与提示词一致的 [n] 标注，前端和真实模型的输出格式才是同一套
            parts.append(f"[{label}] {title}\n{_condense(body)}")
        return (
            f"【演示模式】我从知识库里检到 {len(documents)} 段参考资料，按资料整理如下"
            f"（问题：{question}）：\n\n"
            + "\n\n".join(parts)
            + "\n\n以上内容来自知识库文档，右侧/下方会列出引用出处。"
            "把 .env 里的 LLM_PROVIDER 换成 deepseek 或 openai 后，这里会换成真实模型组织的回答。"
        )

    @staticmethod
    def _compose_after_tool(tool_message: ToolMessage) -> str:
        """把工具返回的 JSON 复述成人话——真实模型就是干这个的。"""
        try:
            payload = json.loads(tool_message.content)
        except (TypeError, json.JSONDecodeError):
            return f"【演示模式】工具返回（未解析）：{tool_message.content}"

        if not payload.get("ok", True):
            return f"【演示模式】{payload.get('message', '工具执行失败')}"

        ticket = payload.get("ticket")
        if ticket:
            if payload.get("action") == "create_ticket":
                head = "已存在相同问题的未关闭工单，没有重复创建" if payload.get("duplicated") else "工单已创建"
                return (
                    f"【演示模式】{head}：{ticket['id']}\n\n"
                    f"- 标题：{ticket['title']}\n"
                    f"- 分类：{ticket['category']} ／ 优先级：{ticket['priority']}\n"
                    f"- 状态：{ticket['status']}\n"
                    f"- 联系人：{ticket['contact']}\n\n"
                    f"工程师会按 SLA 响应，期间你可以随时问「{ticket['id']} 处理到哪了」。"
                )
            if payload.get("action") == "escalate_to_human":
                return f"【演示模式】工单 {ticket['id']} 已转人工，状态：{ticket['status']}。工程师会尽快接手。"
            return f"【演示模式】工单 {ticket['id']} 当前状态：{ticket['status']}（{ticket['updated_at']} 更新）。"

        tickets = payload.get("tickets")
        if tickets:
            lines = [f"- {item['id']}［{item['status']}］{item['title']}" for item in tickets]
            return "【演示模式】查到这些工单：\n" + "\n".join(lines)
        if tickets == []:
            return "【演示模式】没有查到工单记录。"

        return f"【演示模式】{payload.get('message', '工具已执行')}"


def _as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content)
