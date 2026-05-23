import { Layout, Menu, Typography } from 'antd';
import { Link, Outlet, useLocation } from 'react-router-dom';
import {
  DashboardOutlined,
  TeamOutlined,
  UnorderedListOutlined,
  SettingOutlined,
  DollarOutlined,
  BookOutlined,
  RadarChartOutlined,
  ReadOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons';
import { Routes, Route, Navigate } from 'react-router-dom';
import Overview from './pages/Overview';
import ClientDetail from './pages/ClientDetail';
import MonitorCenter from './pages/MonitorCenter';
import TaskQueue from './pages/TaskQueue';
import Settings from './pages/Settings';
import UsageCenter from './pages/UsageCenter';
import DocsCenter from './pages/DocsCenter';
import GuidesHub from './pages/GuidesHub';
import GuidePage from './pages/GuidePage';

const { Sider, Content } = Layout;

const PAGE_TITLES: Record<string, string> = {
  '/': '总览',
  '/clients': '总览',
  '/tasks': '任务队列',
  '/usage': 'LLM 用量 / 成本',
  '/settings': '设置',
  '/docs': '文件库',
  '/guides': '教程总览',
};

function getPageTitle(pathname: string): string {
  if (pathname.match(/^\/clients\/\d+\/monitor/)) return '监测中心';
  if (pathname.match(/^\/clients\/\d+/)) return '监测对象详情';
  if (pathname.match(/^\/guides\/[^/]+/)) return '教程';
  return PAGE_TITLES[pathname] || 'CiteScope';
}

function Shell() {
  const location = useLocation();
  const pathname = location.pathname;
  const selected = pathname === '/' || pathname === '/clients' ? 'overview' :
    pathname.startsWith('/tasks') ? 'tasks' :
    pathname.startsWith('/usage') ? 'usage' :
    pathname.startsWith('/settings') ? 'settings' :
    pathname.startsWith('/guides') ? 'guides' :
    pathname.startsWith('/docs') ? 'docs' :
    pathname.startsWith('/clients') ? 'clients' : 'overview';

  const pageTitle = getPageTitle(pathname);

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={240} style={{ overflow: 'auto', height: '100vh', position: 'fixed', left: 0, top: 0, bottom: 0 }}>
        {/* Brand Header */}
        <div style={{ padding: '20px 24px 16px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <RadarChartOutlined style={{ fontSize: 28, color: '#F09527' }} />
            <div>
              <div style={{ color: '#fff', fontSize: 18, fontWeight: 700, letterSpacing: '-0.02em', lineHeight: 1.2 }}>
                CiteScope
              </div>
              <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: 11, letterSpacing: '0.05em' }}>
                GEO 效果监测实验平台
              </div>
            </div>
          </div>
        </div>

        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selected]}
          style={{ borderRight: 0, marginTop: 8 }}
          items={[
            {
              key: 'grp-overview',
              type: 'group',
              label: '',
              children: [
                { key: 'overview', icon: <DashboardOutlined />, label: <Link to="/">总览</Link> },
              ],
            },
            {
              key: 'grp-ops',
              type: 'group',
              label: '监测对象',
              children: [
                { key: 'clients', icon: <TeamOutlined />, label: <Link to="/clients">品牌列表</Link> },
              ],
            },
            {
              key: 'grp-tools',
              type: 'group',
              label: '工具',
              children: [
                { key: 'tasks', icon: <UnorderedListOutlined />, label: <Link to="/tasks">任务队列</Link> },
                { key: 'usage', icon: <DollarOutlined />, label: <Link to="/usage">LLM 用量</Link> },
              ],
            },
            {
              key: 'grp-knowledge',
              type: 'group',
              label: '知识库',
              children: [
                {
                  key: 'guides',
                  icon: <ReadOutlined />,
                  label: <Link to="/guides">教程总览</Link>,
                },
                {
                  key: 'docs',
                  icon: <FolderOpenOutlined />,
                  label: <Link to="/docs">文件库</Link>,
                },
              ],
            },
            {
              key: 'grp-system',
              type: 'group',
              label: '系统',
              children: [
                { key: 'settings', icon: <SettingOutlined />, label: <Link to="/settings">设置</Link> },
              ],
            },
          ]}
        />

        {/* Footer */}
        <div style={{
          position: 'absolute', bottom: 0, width: '100%',
          padding: '12px 24px', borderTop: '1px solid rgba(255,255,255,0.06)',
          color: 'rgba(255,255,255,0.25)', fontSize: 11,
        }}>
          v0.3.0 &middot; 内部使用
        </div>
      </Sider>

      <Layout style={{ marginLeft: 240 }}>
        <div style={{
          background: '#fff', padding: '16px 24px',
          borderBottom: '1px solid #f0f0f0',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <Typography.Title level={4} style={{ margin: 0, fontWeight: 600 }}>
            {pageTitle}
          </Typography.Title>
        </div>
        <Content style={{ margin: 24, padding: 24, background: '#fff', borderRadius: 8, minHeight: 280 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Overview />} />
        <Route path="/clients" element={<Overview />} />
        <Route path="/clients/:id" element={<ClientDetail />} />
        <Route path="/clients/:id/monitor" element={<MonitorCenter />} />
        <Route path="/tasks" element={<TaskQueue />} />
        <Route path="/usage" element={<UsageCenter />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/docs" element={<DocsCenter />} />
        <Route path="/guides" element={<GuidesHub />} />
        <Route path="/guides/:slug" element={<GuidePage />} />
        {/* Backward-compat: 老路径跳到新结构 */}
        <Route
          path="/docs/citation-sources"
          element={<Navigate to="/guides/citation-sources" replace />}
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
