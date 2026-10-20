import { useCallback, useEffect, useState } from "react";
import { SearchOutlined } from "@ant-design/icons";
import { Button, Empty, Input, Spin, Tag, Typography } from "antd";

import { listArticles, listCategories, searchKnowledge } from "../api/agent";
import SiteSidebar from "../components/SiteSidebar";
import type { AgentInfo, KnowledgeArticle, KnowledgeCategory, KnowledgeHit } from "../types";

const { Text, Paragraph } = Typography;

/** 电商知识库检索页：分类浏览 + 文章列表 + RAG 命中（HTML 原文链接）。 */
export default function KnowledgePage({ info }: { info: AgentInfo | null }) {
  const [keyword, setKeyword] = useState("");
  const [category, setCategory] = useState("");
  const [categories, setCategories] = useState<KnowledgeCategory[]>([]);
  const [articles, setArticles] = useState<KnowledgeArticle[]>([]);
  const [hits, setHits] = useState<KnowledgeHit[]>([]);
  const [loading, setLoading] = useState(false);

  const search = useCallback(async () => {
    setLoading(true);
    try {
      const query = keyword.trim();
      const [articleList, ragHits] = await Promise.all([
        listArticles({ q: query, category, limit: 50 }),
        query ? searchKnowledge(query, 5) : Promise.resolve([]),
      ]);
      setArticles(articleList);
      setHits(ragHits);
    } catch {
      setArticles([]);
      setHits([]);
    } finally {
      setLoading(false);
    }
  }, [keyword, category]);

  useEffect(() => {
    listCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    void search();
  }, [search]);

  return (
    <div className="shell">
      <SiteSidebar active="kb" info={info} />
      <main className="admin-main">
        <header className="topbar">
          <span className="topbar-title">知识库检索</span>
          <span className="pill">{articles.length} 篇</span>
          <span className="spacer" />
          <a className="nav-link" href="/kb/index.html" target="_blank" rel="noreferrer">
            浏览知识库目录 ↗
          </a>
        </header>

        <div className="kb-body">
          <div className="filter-bar">
            <Input
              allowClear
              prefix={<SearchOutlined />}
              placeholder="搜索标题、摘要、标签，如：退款到账、发票、优惠券"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onPressEnter={() => void search()}
            />
            <Button type="primary" onClick={() => void search()} loading={loading}>
              检索
            </Button>
          </div>

          <div className="category-chips">
            <button type="button" className={!category ? "chip active" : "chip"} onClick={() => setCategory("")}>
              全部
            </button>
            {categories.map((item) => (
              <button
                type="button"
                key={item.code}
                className={category === item.code ? "chip active" : "chip"}
                onClick={() => setCategory(item.code)}
              >
                {item.name}
              </button>
            ))}
          </div>

          {keyword && hits.length > 0 && (
            <section className="rag-panel">
              <div className="chart-head">
                <span>检索命中（RAG 召回）</span>
                <span className="muted">{hits.length} 段</span>
              </div>
              {hits.map((hit) => (
                <div className="rag-hit" key={`${hit.index}-${hit.source}-${hit.title}`}>
                  <span className="hit-index">[{hit.index}]</span>
                  <span className="hit-source">{hit.source}</span>
                  <span className="hit-title">{hit.title}</span>
                  {typeof hit.score === "number" && <span className="hit-score">score {hit.score}</span>}
                  <Paragraph className="hit-snippet" ellipsis={{ rows: 2 }}>{hit.snippet}</Paragraph>
                </div>
              ))}
            </section>
          )}

          {loading && articles.length === 0 ? (
            <Spin />
          ) : articles.length === 0 ? (
            <Empty description="没有匹配的文章" />
          ) : (
            <div className="article-grid">
              {articles.map((article) => (
                <a className="article-card" key={article.article_no} href={article.url} target="_blank" rel="noreferrer">
                  <div className="article-head">
                    <span className="mono muted">{article.article_no}</span>
                    <Tag bordered={false}>{article.category_name}</Tag>
                    <span className="spacer" />
                    <span className="muted">查看 HTML 页面 ↗</span>
                  </div>
                  <div className="article-title">{article.title}</div>
                  <div className="article-summary">{article.summary}</div>
                  <div className="article-tags">
                    {article.tags.map((tag) => (
                      <span className="tag" key={tag}>{tag}</span>
                    ))}
                  </div>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    更新于 {article.updated_at?.slice(0, 10)}
                  </Text>
                </a>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
