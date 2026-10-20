import { useState } from "react";
import { RobotOutlined } from "@ant-design/icons";

import Composer from "../components/Composer";
import VersionBadge from "../components/VersionBadge";
import { PENDING_QUESTION_KEY, PROMPTS } from "../prompts";
import { navigate } from "../router";
import type { AgentInfo } from "../types";

/** 第 1 屏：只有对话框的首页。 */
export default function HomePage({ info }: { info: AgentInfo | null }) {
  const [value, setValue] = useState("");

  const submit = (text: string) => {
    const question = text.trim();
    if (!question) return;
    sessionStorage.setItem(PENDING_QUESTION_KEY, question);
    navigate("/chat");
  };

  return (
    <div className="home">
      <header className="home-top">
        <span className="brand-mark">
          <RobotOutlined />
        </span>
        <span className="home-brand">智能问答</span>
        <span className="pill">{info?.mock ? "演示模式" : info?.provider ?? "Agent"}</span>
        <span className="pill">知识库 · 已接入</span>
        <span className="pill">售后工单 · 已接入</span>
        <span className="spacer" />
        <VersionBadge sha={info?.git_sha} date={info?.git_date} />
      </header>

      <main className="home-main">
        <h1>有什么可以帮您？</h1>
        <p className="home-sub">电商智能客服 · 订单查询与知识库问答一体化</p>
        <Composer
          large
          value={value}
          onChange={setValue}
          onSubmit={submit}
          model={info?.model || info?.provider || "Agent"}
          placeholder="描述问题，或直接说「帮我建个售后工单…」"
        />
        <div className="prompt-row">
          {PROMPTS.map((prompt) => (
            <button type="button" key={prompt} className="prompt-chip" onClick={() => submit(prompt)}>
              {prompt}
            </button>
          ))}
        </div>
      </main>

      <footer className="home-foot">回答将引用电商帮助中心，并可创建售后工单</footer>
    </div>
  );
}
