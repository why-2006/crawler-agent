import { Table, Empty } from "antd";
import type { ExtractedRecord } from "../types";

interface Props {
  data: ExtractedRecord[];
}

export default function DataTable({ data }: Props) {
  if (!data.length) {
    return <Empty description="暂无提取数据" />;
  }

  // 从数据中推断列
  const allKeys = new Set<string>();
  data.forEach((record) => {
    Object.keys(record.data).forEach((k) => allKeys.add(k));
  });
  const keys = Array.from(allKeys);

  const columns = [
    {
      title: "来源 URL",
      dataIndex: "source_url",
      key: "source_url",
      ellipsis: true,
      width: 200,
      render: (url: string) => (
        <a href={url} target="_blank" rel="noopener noreferrer" title={url}>
          {url.length > 40 ? url.slice(0, 40) + "..." : url}
        </a>
      ),
    },
    ...keys.map((key) => ({
      title: key,
      dataIndex: ["data", key],
      key,
      ellipsis: true,
      render: (val: unknown) => {
        if (val === null || val === undefined) return "-";
        if (typeof val === "object") return JSON.stringify(val);
        return String(val);
      },
    })),
  ];

  const dataSource = data.map((record, idx) => ({
    ...record,
    _key: idx,
  }));

  return (
    <Table
      columns={columns}
      dataSource={dataSource}
      rowKey="_key"
      size="small"
      scroll={{ x: "max-content" }}
      pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
    />
  );
}
