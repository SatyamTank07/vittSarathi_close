import React, { useEffect } from 'react';
import { useDocumentLibrary } from '../hooks/useDocumentLibrary';

interface DocumentLibraryProps {
  isOpen: boolean;
  onClose: () => void;
  refreshTrigger?: number;
}

const DocumentLibrary: React.FC<DocumentLibraryProps> = ({ isOpen, onClose, refreshTrigger = 0 }) => {
  const { documents, loading, error, refresh } = useDocumentLibrary();

  useEffect(() => {
    if (refreshTrigger > 0) {
      refresh();
    }
  }, [refreshTrigger, refresh]);

  return (
    <>
      {/* Backdrop overlay */}
      <div 
        className={`doc-library-backdrop ${isOpen ? 'open' : ''}`} 
        onClick={onClose}
      />
      
      {/* Sidebar panel */}
      <div className={`doc-library-panel ${isOpen ? 'open' : ''}`}>
        <div className="doc-library-header">
          <div className="doc-library-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            <h2>Document Library</h2>
          </div>
          <button className="doc-library-close" onClick={onClose}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="doc-library-content">
          {loading && documents.length === 0 ? (
            <div className="doc-library-loading">Loading documents...</div>
          ) : error ? (
            <div className="doc-library-error">{error}</div>
          ) : documents.length === 0 ? (
            <div className="doc-library-empty">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p>No documents ingested yet.</p>
            </div>
          ) : (
            <div className="doc-library-list">
              {Object.entries(
                documents.reduce((acc, doc) => {
                  if (!acc[doc.company_id]) acc[doc.company_id] = [];
                  acc[doc.company_id].push(doc);
                  return acc;
                }, {} as Record<string, typeof documents>)
              ).map(([companyId, companyDocs]) => (
                <div key={companyId} className="doc-card">
                  <div className="doc-card-header">
                    <span className="doc-company">{companyId}</span>
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {companyDocs.length} {companyDocs.length === 1 ? 'Report' : 'Reports'}
                    </span>
                  </div>
                  <div className="doc-card-body" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {companyDocs.map(doc => (
                      <div key={doc.id} style={{ 
                        background: 'rgba(255,255,255,0.03)', 
                        padding: '10px', 
                        borderRadius: '8px',
                        border: '1px solid var(--border)'
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                          <span style={{ fontSize: '0.85rem', fontWeight: 500, color: 'var(--text-main)' }}>
                            {doc.fiscal_year} {doc.report_type.toUpperCase()}
                          </span>
                          <div className="doc-status-wrapper">
                            {doc.ingestion_status === 'completed' && (
                              <span className="status-badge success">
                                <span className="status-dot"></span> Done
                              </span>
                            )}
                            {(doc.ingestion_status === 'processing' || doc.ingestion_status === 'pending') && (
                              <span className="status-badge processing">
                                <span className="status-dot pulsing"></span> Processing
                              </span>
                            )}
                            {doc.ingestion_status === 'failed' && (
                              <span className="status-badge failed" title={doc.error_message}>
                                <span className="status-dot"></span> Failed
                              </span>
                            )}
                          </div>
                        </div>
                        {doc.total_pages > 0 && (
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            {doc.total_pages} pages
                          </div>
                        )}
                        {doc.ingestion_status === 'failed' && doc.error_message && (
                          <div className="doc-card-error" style={{ marginTop: '6px', paddingTop: '6px' }}>
                            {doc.error_message}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
};

export default DocumentLibrary;
