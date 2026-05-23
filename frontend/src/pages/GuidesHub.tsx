/**
 * 教程总览 hub 页:按分类显示所有 guide 卡片。
 * 路由:/guides
 */
import { useMemo } from 'react';
import { Card, Col, Row, Space, Tag, Typography } from 'antd';
import { Link } from 'react-router-dom';
import { RightOutlined } from '@ant-design/icons';
import { CATEGORY_LABELS, GUIDE_LIST, GuideMeta } from '../docs/guides';

export default function GuidesHub() {
  // 按 category 分组
  const groups = useMemo(() => {
    const m = new Map<GuideMeta['category'], GuideMeta[]>();
    for (const g of GUIDE_LIST) {
      const list = m.get(g.category) ?? [];
      list.push(g);
      m.set(g.category, list);
    }
    return Array.from(m.entries());
  }, []);

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      <Card style={{ marginBottom: 20 }} bodyStyle={{ padding: 24 }}>
        <Typography.Title level={3} style={{ marginTop: 0 }}>
          📘 教程总览
        </Typography.Title>
        <Typography.Paragraph style={{ marginBottom: 0 }}>
          CiteScope 是一个 GEO (Generative Engine Optimization) 监测平台。
          下面是按模块整理的使用手册,每条都是独立的指南页。
          新人推荐从 <Link to="/guides/getting-started">5 步上手</Link> 开始。
        </Typography.Paragraph>
      </Card>

      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        {groups.map(([cat, items]) => (
          <div key={cat}>
            <Typography.Title level={5} style={{ marginBottom: 12 }}>
              {CATEGORY_LABELS[cat]}
            </Typography.Title>
            <Row gutter={[16, 16]}>
              {items.map((g) => (
                <Col key={g.slug} xs={24} sm={12} lg={8}>
                  <Link to={`/guides/${g.slug}`}>
                    <Card
                      hoverable
                      size="small"
                      style={{ height: '100%' }}
                      bodyStyle={{ padding: 16 }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                        <Typography.Text strong style={{ fontSize: 15 }}>
                          {g.title}
                        </Typography.Text>
                        <RightOutlined style={{ color: '#999', fontSize: 12, marginTop: 4 }} />
                      </div>
                      <Tag style={{ marginBottom: 8 }}>{`#${g.order}`}</Tag>
                      <Typography.Paragraph
                        type="secondary"
                        style={{ fontSize: 13, marginBottom: 0 }}
                        ellipsis={{ rows: 3 }}
                      >
                        {g.summary}
                      </Typography.Paragraph>
                    </Card>
                  </Link>
                </Col>
              ))}
            </Row>
          </div>
        ))}
      </Space>
    </div>
  );
}
