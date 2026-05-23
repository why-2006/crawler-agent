import { BrowserRouter, Routes, Route, useNavigate } from "react-router-dom";
import {
  ConfigProvider,
  Layout,
  theme,
  App as AntdApp,
  Drawer,
  Button,
  Space,
} from "antd";
import zhCN from "antd/locale/zh_CN";
import { MenuOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useState } from "react";
import Dashboard from "./pages/Dashboard";
import Home from "./pages/Home";
import CreateTask from "./pages/CreateTask";
import TaskDetail from "./pages/TaskDetail";

const { Header, Content } = Layout;

function AppLayout() {
  const [showDrawer, setShowDrawer] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const navigate = useNavigate();

  return (
    <AntdApp>
      <Layout
        style={{ minHeight: "100vh", borderRadius: 8, overflow: "hidden" }}
      >
        {showDrawer && (
          <Drawer
            title="菜单"
            placement="left"
            open={showDrawer}
            closable={false}
            styles={{
              content: {
                borderTopRightRadius: 16,
                borderBottomRightRadius: 16,
              },
            }}
            onClose={() => setShowDrawer(false)}
          >
            <div
              style={{
                position: "absolute",
                top: 16,
                right: 16,
              }}
            >
              <Button
                style={{ border: 0, boxShadow: "0 0px 0px" }}
                icon={<MenuOutlined />}
                onClick={() => setShowDrawer(false)}
              />
            </div>
            <Space style={{ padding: "0 0 12px 0" }}>
              <Button
                style={{ border: 0, boxShadow: "0 0px 0px" }}
                icon={<ReloadOutlined />}
                onClick={() => setRefreshKey((k) => k + 1)}
              >
                刷新
              </Button>
              <Button
                style={{ border: 0, boxShadow: "0 0px 0px" }}
                icon={<PlusOutlined />}
                onClick={() => {
                  navigate("/tasks/new");
                  setShowDrawer(false);
                }}
              >
                新建任务
              </Button>
            </Space>
            <menu style={{ padding: "0" }}>
              <Dashboard key={refreshKey} />
            </menu>
          </Drawer>
        )}
        <Header
          style={{
            display: "flex",
            alignItems: "center",
            background: "#ffffff",
            padding: "0 12px",
          }}
        >
          <Button
            style={{ border: 0, boxShadow: "0 0px 0px" }}
            icon={<MenuOutlined />}
            onClick={() => setShowDrawer(!showDrawer)}
          />
          <h1 style={{ color: "#000000", margin: "0 12px", fontSize: 18 }}>
            Crawler Agent
          </h1>
        </Header>
        <Content
          style={{
            padding: "24px",
            maxWidth: 1200,
            margin: "0 auto",
            width: "100%",
          }}
        >
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/tasks/new" element={<CreateTask />} />
            <Route path="/tasks/:taskId" element={<TaskDetail />} />
          </Routes>
        </Content>
      </Layout>
    </AntdApp>
  );
}

export default function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.defaultAlgorithm,
        token: {
          colorPrimary: "#78a9ed",
        },
      }}
    >
      <BrowserRouter
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <AppLayout />
      </BrowserRouter>
    </ConfigProvider>
  );
}
