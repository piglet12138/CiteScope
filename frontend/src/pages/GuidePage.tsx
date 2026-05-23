/**
 * 单个 guide 动态路由 — 从 useParams 读 slug,manifest 里查内容,丢给 MarkdownPage。
 * 路由:/guides/:slug
 * 找不到 slug 时显示 404 + 回退按钮。
 */
import { useParams, Navigate } from 'react-router-dom';
import { Button, Card, Typography } from 'antd';
import { Link } from 'react-router-dom';
import { ArrowLeftOutlined } from '@ant-design/icons';
import MarkdownPage from '../components/MarkdownPage';
import { GUIDES } from '../docs/guides';

export default function GuidePage() {
  const { slug } = useParams<{ slug: string }>();
  if (!slug) return <Navigate to="/guides" replace />;
  const guide = GUIDES[slug];
  if (!guide) {
    return (
      <div style={{ maxWidth: 720, margin: '40px auto' }}>
        <Card>
          <Typography.Title level={4}>教程不存在</Typography.Title>
          <Typography.Paragraph>
            找不到 slug 为 <code>{slug}</code> 的教程。
          </Typography.Paragraph>
          <Link to="/guides">
            <Button type="primary" icon={<ArrowLeftOutlined />}>
              回到教程总览
            </Button>
          </Link>
        </Card>
      </div>
    );
  }
  return <MarkdownPage content={guide.content} />;
}
