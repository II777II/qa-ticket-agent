import { ReloadOutlined } from "@ant-design/icons";
import { Button, Empty, Space, Tag, Typography } from "antd";

import type { KnowledgeHit } from "../types";

const { Text, Paragraph } = Typography;

export interface KnowledgePanelProps {
  question: string;
  hits: KnowledgeHit[];
  loading: boolean;
  onRefresh: () => void;
}

/** 第 3 屏右侧：知识库检索结果（Top-K 命中、来源、相关度、片段）。 */
export default function KnowledgePanel({ question, hits, loading, onRefresh }: KnowledgePanelProps) {
  return (
    <aside className="side-panel">
      <div className="panel-head">
        <span className="panel-title">知识库检索结果</span>
        <Tag variant="filled">本轮 {hits.length} 条</Tag>
        <Button size="small" type="text" icon={<ReloadOutlined />} onClick={onRefresh} loading={loading}>
          重查
        </Button>
      </div>
      <div className="panel-query">
        <Text type="secondary">本轮问题</Text>
        <div className="query-text">{question || "（这一轮还没有提问）"}</div>
      </div>

      {hits.length === 0 ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={loading ? "检索中…" : "本轮没有命中知识库"} />
      ) : (
        <div className="hit-list">
          {hits.map((hit) => (
            <article className="hit-card" key={`${hit.index}-${hit.source}-${hit.title}`}>
              <div className="hit-head">
                <span className="hit-index">[{hit.index}]</span>
                <span className="hit-source">{hit.source}</span>
                {typeof hit.score === "number" && <span className="hit-score">score {hit.score}</span>}
              </div>
              <div className="hit-title">{hit.title}</div>
              <Paragraph className="hit-snippet" ellipsis={{ rows: 4 }}>
                {hit.snippet}
              </Paragraph>
            </article>
          ))}
        </div>
      )}

      <Space orientation="vertical" size={2} className="panel-foot">
        <Text type="secondary" style={{ fontSize: 11 }}>
          检索为关键词命中数与标题加权，top-k 由后端 RAG_TOP_K 控制上限。
        </Text>
      </Space>
    </aside>
  );
}
