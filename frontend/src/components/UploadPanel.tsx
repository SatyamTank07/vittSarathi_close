import React, { useRef, useState, useEffect } from 'react';
import { useDocumentUpload } from '../hooks/useDocumentUpload';

interface UploadPanelProps {
  isOnline: boolean;
  onUploadSuccess?: () => void;
}

export default function UploadPanel({ isOnline, onUploadSuccess }: UploadPanelProps) {
  const {
    uploadPhase,
    extractedMeta,
    errorMessage,
    processingStatus,
    uploadFile,
    reset,
  } = useDocumentUpload();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (uploadPhase === 'processing' && onUploadSuccess) {
      onUploadSuccess();
      setTimeout(() => reset(), 100);
    }
  }, [uploadPhase, onUploadSuccess, reset]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!isOnline) return;
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    setLocalError(null);

    if (!isOnline) return;

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
        setLocalError("Only PDF files are supported.");
        return;
      }
      uploadFile(file);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    setLocalError(null);
    if (e.target.files && e.target.files.length > 0) {
      const file = e.target.files[0];
      if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
        setLocalError("Only PDF files are supported.");
        return;
      }
      uploadFile(file);
    }
    // reset input so the same file can be selected again if needed
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleClickZone = () => {
    if (!isOnline) return;
    setLocalError(null);
    if (fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const renderContent = () => {
    if (uploadPhase === 'idle') {
      return (
        <div 
          className={`upload-dropzone ${isDragOver ? 'drag-over' : ''} ${!isOnline ? 'offline' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={handleClickZone}
          style={{
            border: `2px dashed ${isDragOver ? '#10b981' : '#4b5563'}`,
            borderRadius: '8px',
            padding: '2rem',
            textAlign: 'center',
            cursor: isOnline ? 'pointer' : 'not-allowed',
            opacity: isOnline ? 1 : 0.5,
            transition: 'border-color 0.2s',
            backgroundColor: isDragOver ? 'rgba(16, 185, 129, 0.05)' : 'transparent',
            marginBottom: '1rem'
          }}
        >
          <input 
            type="file" 
            accept=".pdf,application/pdf" 
            ref={fileInputRef} 
            onChange={handleFileSelect} 
            style={{ display: 'none' }}
            disabled={!isOnline}
          />
          <svg style={{ width: '48px', height: '48px', margin: '0 auto 1rem', color: '#9ca3af' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
          </svg>
          <div style={{ fontWeight: 500, color: '#e5e7eb', marginBottom: '0.5rem' }}>Drop an annual report PDF here</div>
          <div style={{ fontSize: '0.875rem', color: '#9ca3af' }}>or click to browse</div>
          
          {localError && (
            <div style={{ marginTop: '1rem', color: '#ef4444', fontSize: '0.875rem' }}>
              {localError}
            </div>
          )}
        </div>
      );
    }

    if (uploadPhase === 'uploading') {
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', padding: '2rem', border: '1px solid #374151', borderRadius: '8px', marginBottom: '1rem', justifyContent: 'center' }}>
          <div className="spin" style={{ width: '20px', height: '20px', border: '2px solid #10b981', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 1s linear infinite' }}></div>
          <span style={{ color: '#e5e7eb' }}>Uploading PDF...</span>
        </div>
      );
    }

    if (uploadPhase === 'processing') {
      let stageLabel = "Waiting for pipeline...";
      if (processingStatus === 'PENDING') stageLabel = "Queued for processing";
      if (processingStatus === 'PROCESSING') stageLabel = "Ingesting document...";

      return (
        <div style={{ padding: '1.5rem', border: '1px solid #374151', borderRadius: '8px', marginBottom: '1rem', backgroundColor: '#1f2937' }}>
          {extractedMeta && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '1.5rem', paddingBottom: '1.5rem', borderBottom: '1px solid #374151' }}>
              <div>
                <div style={{ fontSize: '0.75rem', color: '#9ca3af', textTransform: 'uppercase', marginBottom: '0.25rem' }}>Company</div>
                <div style={{ color: '#e5e7eb', fontWeight: 500 }}>{extractedMeta.company_id || 'Unknown'}</div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: '#9ca3af', textTransform: 'uppercase', marginBottom: '0.25rem' }}>Year</div>
                <div style={{ color: '#e5e7eb', fontWeight: 500 }}>{extractedMeta.fiscal_year || 'Unknown'}</div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: '#9ca3af', textTransform: 'uppercase', marginBottom: '0.25rem' }}>Type</div>
                <div style={{ color: '#e5e7eb', fontWeight: 500 }}>{extractedMeta.report_type || 'Annual Report'}</div>
              </div>
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <div className="pulseStatus" style={{ width: '10px', height: '10px', backgroundColor: '#10b981', borderRadius: '50%', animation: 'pulseStatus 2s cubic-bezier(0.4, 0, 0.6, 1) infinite' }}></div>
            <span style={{ color: '#d1d5db' }}>{stageLabel}</span>
          </div>
        </div>
      );
    }

    if (uploadPhase === 'complete') {
      return (
        <div style={{ padding: '1.5rem', border: '1px solid #065f46', borderRadius: '8px', marginBottom: '1rem', backgroundColor: 'rgba(6, 95, 70, 0.1)', display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
          <div style={{ color: '#10b981', flexShrink: 0, marginTop: '2px' }}>
            <svg style={{ width: '24px', height: '24px' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ color: '#10b981', fontWeight: 'bold', marginBottom: '0.5rem' }}>Document ready</div>
            {extractedMeta && (
              <div style={{ color: '#e5e7eb', fontSize: '0.875rem', marginBottom: '0.5rem' }}>
                {extractedMeta.company_id} &middot; FY{extractedMeta.fiscal_year} &middot; {extractedMeta.report_type || 'Annual Report'}
              </div>
            )}
            <div style={{ color: '#9ca3af', fontSize: '0.875rem', marginBottom: '1rem' }}>
              This document is now available to agents via RAG.
            </div>
            <button 
              onClick={reset}
              style={{ background: 'none', border: 'none', padding: 0, color: '#3b82f6', cursor: 'pointer', fontSize: '0.875rem' }}
            >
              Upload another
            </button>
          </div>
        </div>
      );
    }

    if (uploadPhase === 'failed') {
      return (
        <div style={{ padding: '1.5rem', border: '1px solid #7f1d1d', borderRadius: '8px', marginBottom: '1rem', backgroundColor: 'rgba(127, 29, 29, 0.1)', display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
          <div style={{ color: '#ef4444', flexShrink: 0, marginTop: '2px' }}>
            <svg style={{ width: '24px', height: '24px' }} fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ color: '#ef4444', fontWeight: 'bold', marginBottom: '0.5rem' }}>Upload failed</div>
            <div style={{ color: '#e5e7eb', fontSize: '0.875rem', marginBottom: '1rem' }}>
              {errorMessage}
            </div>
            <button 
              onClick={reset}
              style={{ background: 'none', border: 'none', padding: 0, color: '#3b82f6', cursor: 'pointer', fontSize: '0.875rem' }}
            >
              Try again
            </button>
          </div>
        </div>
      );
    }

    return null;
  };

  return (
    <div className="upload-panel-container">
      {renderContent()}
    </div>
  );
}
