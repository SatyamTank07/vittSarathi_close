import React, { useState, useEffect } from 'react';

interface Report {
  id: string;
  ticker: string;
  company_name: string;
  sector: string;
  industry: string;
  investment_verdict: string;
  confidence_level: string;
  created_at: string;
}

interface AnalysisSidebarProps {
  selectedReportId: string | null;
  onSelectReport: (id: string) => void;
  onDeleteReport: (id: string) => void;
  refreshTrigger: number;
}

const AnalysisSidebar: React.FC<AnalysisSidebarProps> = ({
  selectedReportId,
  onSelectReport,
  onDeleteReport,
  refreshTrigger,
}) => {
  const [reports, setReports] = useState<Report[]>([]);

  const fetchReports = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/reports');
      if (res.ok) {
        const data = await res.json();
        setReports(data);
      }
    } catch (error) {
      console.error('Failed to fetch reports:', error);
    }
  };

  useEffect(() => {
    fetchReports();
  }, [refreshTrigger]);

  const getVerdictEmoji = (verdict: string) => {
    const v = (verdict || '').toLowerCase();
    if (v.includes('bullish')) return '🟢';
    if (v.includes('bearish')) return '🔴';
    return '🟡';
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const res = await fetch(`http://localhost:8000/api/reports/${id}`, { method: 'DELETE' });
      if (res.ok) {
        setReports(prev => prev.filter(r => r.id !== id));
        onDeleteReport(id);
      }
    } catch (error) {
      console.error('Failed to delete report:', error);
    }
  };

  if (reports.length === 0) return null;

  return (
    <div className="analysis-bar">
      <span className="analysis-bar-label">📊 Reports</span>
      <div className="report-chips">
        {reports.map((report) => (
          <button
            key={report.id}
            className={`report-chip ${report.id === selectedReportId ? 'active' : ''}`}
            onClick={() => onSelectReport(report.id)}
          >
            <span className="chip-verdict">{getVerdictEmoji(report.investment_verdict)}</span>
            {report.ticker}
            <span
              className="chip-delete"
              onClick={(e) => handleDelete(report.id, e)}
              title="Delete report"
            >
              ×
            </span>
          </button>
        ))}
      </div>
    </div>
  );
};

export default AnalysisSidebar;
