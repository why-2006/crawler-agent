import { useNavigate } from "react-router-dom";
import { Button, Typography, Card, Row, Col, Divider, Steps } from "antd";
import {
  RobotOutlined,
  ThunderboltOutlined,
  BarChartOutlined,
  SyncOutlined,
  SettingOutlined,
  TableOutlined,
  SearchOutlined,
  EditOutlined,
  ApiOutlined,
  CheckCircleOutlined,
} from "@ant-design/icons";

const { Title, Text } = Typography;

const PRIMARY = "#78a9ed";

const FEATURES = [
  {
    icon: <RobotOutlined />,
    title: "智能提取",
    desc: "基于大模型自动识别页面结构，精准提取目标数据",
  },
  {
    icon: <ThunderboltOutlined />,
    title: "实时监控",
    desc: "WebSocket 实时推送爬取进度，结果即时呈现",
  },
  {
    icon: <BarChartOutlined />,
    title: "数据洞察",
    desc: "自动生成可视化图表，洞察数据分布与趋势",
  },
  {
    icon: <SyncOutlined />,
    title: "增量追踪",
    desc: "定时监测页面内容变化，变更即时通知",
  },
  {
    icon: <SettingOutlined />,
    title: "灵活配置",
    desc: "自定义爬取深度、页数限制，支持 JavaScript 渲染",
  },
  {
    icon: <TableOutlined />,
    title: "结构化输出",
    desc: "提取数据自动整理为结构化表格，一目了然",
  },
];

const STEPS = [
  { title: "输入网址", description: "提供目标网站的起始 URL", icon: <SearchOutlined /> },
  { title: "描述数据", description: "用自然语言描述要提取的内容", icon: <EditOutlined /> },
  { title: "自动爬取", description: "AI Agent 自主规划并执行数据采集", icon: <ApiOutlined /> },
  { title: "获取结果", description: "查看结构化数据、图表洞察与变更追踪", icon: <CheckCircleOutlined /> },
];

export default function Home() {
  const navigate = useNavigate();

  return (
    <div>
      {/* Hero */}
      <div style={{ textAlign: "center", padding: "60px 24px 40px" }}>
        <Title style={{ fontSize: 36, marginBottom: 8 }}>智能爬虫 Agent</Title>
        <Text type="secondary" style={{ fontSize: 16 }}>
          基于 AI 的通用网页数据采集与监控平台
        </Text>
        <div style={{ marginTop: 32 }}>
          <Button
            type="primary"
            size="large"
            onClick={() => navigate("/tasks/new")}
            style={{ height: 44, paddingInline: 32, fontSize: 16 }}
          >
            创建新任务
          </Button>
        </div>
      </div>

      {/* Feature Cards */}
      <div style={{ padding: "0 0 40px" }}>
        <Row gutter={[16, 16]}>
          {FEATURES.map((f) => (
            <Col xs={24} sm={12} md={8} key={f.title}>
              <Card
                hoverable
                style={{ height: "100%" }}
                styles={{ body: { padding: 24 } }}
              >
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: 12,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    backgroundColor: "#f0f5ff",
                    marginBottom: 16,
                    fontSize: 24,
                    color: PRIMARY,
                  }}
                >
                  {f.icon}
                </div>
                <Title level={5} style={{ marginBottom: 8 }}>{f.title}</Title>
                <Text type="secondary">{f.desc}</Text>
              </Card>
            </Col>
          ))}
        </Row>
      </div>

      {/* How It Works */}
      <div style={{ padding: "0 0 40px" }}>
        <Divider />
        <Title level={3} style={{ textAlign: "center", marginBottom: 24 }}>
          使用流程
        </Title>
        <Steps
          current={-1}
          items={STEPS.map((s) => ({
            title: s.title,
            description: s.description,
            icon: s.icon,
          }))}
        />
      </div>

      {/* Footer */}
      <div style={{ textAlign: "center", padding: "40px 0 20px" }}>
        <Text type="secondary" style={{ fontSize: 13 }}>
          Powered by LangChain + FastAPI + Ant Design
        </Text>
      </div>
    </div>
  );
}
