import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider, theme } from 'antd';
import enUS from 'antd/locale/en_US';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import 'antd/dist/reset.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={enUS}
      theme={{
        token: {
          colorPrimary: '#C26118',
          colorLink: '#C26118',
          colorInfo: '#C26118',
          borderRadius: 6,
          fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        },
        components: {
          Layout: {
            siderBg: '#1a1a2e',
            headerBg: '#fff',
          },
          Menu: {
            darkItemBg: '#1a1a2e',
            darkSubMenuItemBg: '#16162a',
            darkItemSelectedBg: 'rgba(194, 97, 24, 0.35)',
            darkItemColor: 'rgba(255,255,255,0.72)',
            darkItemHoverColor: '#F09527',
            darkItemSelectedColor: '#F09527',
          },
        },
      }}
    >
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </ConfigProvider>
  </React.StrictMode>,
);
