/**
 * Knowledge Base / Documents Center
 * - List uploaded documents with download links
 * - Upload new documents
 */
import { useEffect, useState } from 'react';
import {
  Button,
  Card,
  Empty,
  List,
  Space,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd';
import {
  CloudUploadOutlined,
  DeleteOutlined,
  DownloadOutlined,
  FileTextOutlined,
  FilePdfOutlined,
  FileWordOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import type { UploadFile } from 'antd';
import { http } from '../api/client';

interface DocItem {
  id: number;
  filename: string;
  original_name: string;
  size: number;
  mime_type: string;
  uploaded_at: string;
  description: string;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function fileIcon(mime: string) {
  if (mime.includes('pdf')) return <FilePdfOutlined style={{ fontSize: 32, color: '#e74c3c' }} />;
  if (mime.includes('word') || mime.includes('docx')) return <FileWordOutlined style={{ fontSize: 32, color: '#2980b9' }} />;
  return <FileTextOutlined style={{ fontSize: 32, color: '#7f8c8d' }} />;
}

export default function DocsCenter() {
  const [docs, setDocs] = useState<DocItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);

  const fetchDocs = async () => {
    setLoading(true);
    try {
      const resp = await http.get('/docs');
      const data = resp.data?.data ?? resp.data ?? [];
      setDocs(Array.isArray(data) ? data : []);
    } catch {
      // If API doesn't exist yet, show empty
      setDocs([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchDocs(); }, []);

  const handleUpload = async (file: File) => {
    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      await http.post('/docs/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      message.success(`${file.name} uploaded`);
      fetchDocs();
    } catch (err: any) {
      message.error('Upload failed: ' + (err?.response?.data?.message || err.message));
    } finally {
      setUploading(false);
    }
    return false; // prevent antd auto upload
  };

  const handleDelete = async (id: number) => {
    try {
      await http.delete(`/docs/${id}`);
      message.success('Document deleted');
      fetchDocs();
    } catch {
      message.error('Delete failed');
    }
  };

  const handleDownload = (doc: DocItem) => {
    window.open(`/api/docs/${doc.id}/download`, '_blank');
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <div>
          <Typography.Title level={5} style={{ margin: 0 }}>Internal Documents</Typography.Title>
          <Typography.Text type="secondary">Whitepapers, SOPs, and reference materials for the team</Typography.Text>
        </div>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchDocs}>Refresh</Button>
          <Upload
            beforeUpload={(file) => { handleUpload(file); return false; }}
            showUploadList={false}
            accept=".pdf,.docx,.doc,.xlsx,.pptx,.md,.txt"
          >
            <Button type="primary" icon={<CloudUploadOutlined />} loading={uploading}>
              Upload Document
            </Button>
          </Upload>
        </Space>
      </div>

      {docs.length === 0 && !loading ? (
        <Card>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="No documents yet. Upload your first file to get started."
          />
        </Card>
      ) : (
        <List
          loading={loading}
          dataSource={docs}
          renderItem={(doc) => (
            <Card style={{ marginBottom: 12 }} hoverable>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                {fileIcon(doc.mime_type)}
                <div style={{ flex: 1 }}>
                  <Typography.Text strong style={{ fontSize: 15 }}>{doc.original_name}</Typography.Text>
                  <div style={{ marginTop: 4 }}>
                    <Space size="small">
                      <Tag>{formatSize(doc.size)}</Tag>
                      <Tag color="default">{doc.mime_type.split('/').pop()}</Tag>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {new Date(doc.uploaded_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
                      </Typography.Text>
                    </Space>
                  </div>
                  {doc.description && (
                    <Typography.Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: 13 }}>
                      {doc.description}
                    </Typography.Text>
                  )}
                </div>
                <Space>
                  <Button icon={<DownloadOutlined />} onClick={() => handleDownload(doc)}>
                    Download
                  </Button>
                  <Button icon={<DeleteOutlined />} danger onClick={() => handleDelete(doc.id)} />
                </Space>
              </div>
            </Card>
          )}
        />
      )}
    </div>
  );
}
