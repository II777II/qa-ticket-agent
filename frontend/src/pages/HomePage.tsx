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
        <span className="pill">工单 · 已接入</span>
        <span className="spacer" />
        <VersionBadge sha={info?.git_sha} date={info?.git_date} />
      </header>

      <main className="home-main">
        <h1>有什么可以帮您？</h1>
        <p className="home-sub">企业智能问答 · 知识库检索与工单处理一体化</p>
        <Composer
          large
          value={value}
          onChange={setValue}
          onSubmit={submit}
          model={info?.model || info?.provider || "Agent"}
          placeholder="描述问题，或直接说「帮我建个工单…」"
        />
        <div className="prompt-row">
          {PROMPTS.map((prompt) => (
            <button type="button" key={prompt} className="prompt-chip" onClick={() => submit(prompt)}>
              {prompt}
            </button>
          ))}
        </div>
      </main>

      <footer className="home-foot">回答将引用企业知识库，并自动关联相关工单</footer>
    </div>
  );
}
