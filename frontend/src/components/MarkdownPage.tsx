/**
 * 通用 Markdown 教程页面组件。
 *
 * 传入 markdown 文本 + 可选回退按钮信息,渲染成 Antd 风格的阅读页。
 * /guides/* 路由下所有具体 guide 共用这套。
 */
import { Link } from 'react-router-dom';
import { Button, Card, Space, Typography } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownPageProps {
  content: string;
  backTo?: string;
  backLabel?: string;
}

export default function MarkdownPage({
  content,
  backTo = '/guides',
  backLabel = '返回教程总览',
}: MarkdownPageProps) {
  return (
    <div style={{ maxWidth: 960, margin: '0 auto' }}>
      <Space style={{ marginBottom: 16 }}>
        <Link to={backTo}>
          <Button icon={<ArrowLeftOutlined />}>{backLabel}</Button>
        </Link>
      </Space>

      <Card>
        <div className="markdown-body" style={{ fontSize: 14, lineHeight: 1.75 }}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ children }) => (
                <Typography.Title level={2} style={{ marginTop: 0 }}>
                  {children}
                </Typography.Title>
              ),
              h2: ({ children }) => (
                <Typography.Title level={3} style={{ marginTop: 28 }}>
                  {children}
                </Typography.Title>
              ),
              h3: ({ children }) => (
                <Typography.Title level={4} style={{ marginTop: 20 }}>
                  {children}
                </Typography.Title>
              ),
              p: ({ children }) => <Typography.Paragraph>{children}</Typography.Paragraph>,
              a: ({ href, children }) => {
                // 站内链接走 react-router,避免整页刷新
                if (href && href.startsWith('/')) {
                  return <Link to={href}>{children}</Link>;
                }
                return (
                  <a href={href} target="_blank" rel="noreferrer">
                    {children}
                  </a>
                );
              },
              table: ({ children }) => (
                <div style={{ overflowX: 'auto', margin: '12px 0' }}>
                  <table
                    style={{
                      borderCollapse: 'collapse',
                      width: '100%',
                      fontSize: 13,
                    }}
                  >
                    {children}
                  </table>
                </div>
              ),
              th: ({ children }) => (
                <th
                  style={{
                    border: '1px solid #e8e8e8',
                    background: '#fafafa',
                    padding: '6px 10px',
                    textAlign: 'left',
                  }}
                >
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td style={{ border: '1px solid #e8e8e8', padding: '6px 10px' }}>{children}</td>
              ),
              code: ({ children, className }) => {
                const isBlock = (className || '').startsWith('language-');
                if (isBlock) {
                  return (
                    <pre
                      style={{
                        background: '#f5f5f5',
                        padding: 12,
                        borderRadius: 4,
                        overflow: 'auto',
                        fontSize: 12,
                      }}
                    >
                      <code>{children}</code>
                    </pre>
                  );
                }
                return (
                  <code
                    style={{
                      background: '#f5f5f5',
                      padding: '1px 6px',
                      borderRadius: 3,
                      fontSize: 12,
                    }}
                  >
                    {children}
                  </code>
                );
              },
              blockquote: ({ children }) => (
                <blockquote
                  style={{
                    borderLeft: '3px solid #d9d9d9',
                    paddingLeft: 12,
                    color: '#666',
                    margin: '8px 0',
                  }}
                >
                  {children}
                </blockquote>
              ),
            }}
          >
            {content}
          </ReactMarkdown>
        </div>
      </Card>
    </div>
  );
}
