import { Progress, Space, Statistic, Card } from "antd";

interface Props {
  pagesCrawled: number;
  pagesDiscovered: number;
  resultCount: number;
}

export default function CrawlProgress({ pagesCrawled, pagesDiscovered, resultCount }: Props) {
  const pct = pagesDiscovered > 0
    ? Math.round((pagesCrawled / Math.max(pagesDiscovered, pagesCrawled)) * 100)
    : 0;

  return (
    <Card size="small">
      <Space direction="vertical" style={{ width: "100%" }}>
        <Progress percent={Math.min(pct, 100)} status="active" />
        <Space split="|" size="large">
          <Statistic title="已抓取" value={pagesCrawled} suffix="页" />
          <Statistic title="已发现" value={pagesDiscovered} suffix="页" />
          <Statistic title="已提取" value={resultCount} suffix="条" />
        </Space>
      </Space>
    </Card>
  );
}
