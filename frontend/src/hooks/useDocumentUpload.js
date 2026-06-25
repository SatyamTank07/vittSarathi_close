import { useState, useRef, useEffect, useCallback } from 'react';
import { uploadDocument, fetchDocumentStatus } from '../api/client';

export function useDocumentUpload() {
  const [uploadPhase, setUploadPhase] = useState('idle'); // 'idle' | 'uploading' | 'processing' | 'complete' | 'failed'
  const [trackingId, setTrackingId] = useState(null);
  const [extractedMeta, setExtractedMeta] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [processingStatus, setProcessingStatus] = useState(null);

  const intervalRef = useRef(null);
  const tickCountRef = useRef(0);

  const cleanupInterval = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    return cleanupInterval;
  }, [cleanupInterval]);

  const uploadFile = async (file) => {
    setUploadPhase('uploading');
    setErrorMessage(null);
    setTrackingId(null);
    setExtractedMeta(null);
    setProcessingStatus(null);
    cleanupInterval();
    tickCountRef.current = 0;

    const res = await uploadDocument(file, '', '');

    if (!res) {
      setUploadPhase('failed');
      setErrorMessage("Upload failed. Check the file and try again.");
      return;
    }

    if (res.tracking_id) {
      setTrackingId(res.tracking_id);
      setExtractedMeta(res.extracted_metadata || null);
      setUploadPhase('processing');
      setProcessingStatus('WAITING'); // Custom default for 404s

      intervalRef.current = setInterval(async () => {
        tickCountRef.current += 1;

        if (tickCountRef.current >= 150) {
          // 5 minutes timeout
          cleanupInterval();
          setUploadPhase('failed');
          setErrorMessage("Ingestion timed out. The document may still process in the background.");
          return;
        }

        const statusRes = await fetchDocumentStatus(res.tracking_id);
        
        if (!statusRes) {
          // 404 or network issue - keep polling
          setProcessingStatus('WAITING');
          return;
        }

        setProcessingStatus(statusRes.status);

        if (statusRes.status === 'COMPLETED') {
          cleanupInterval();
          setUploadPhase('complete');
        } else if (statusRes.status === 'FAILED') {
          cleanupInterval();
          setUploadPhase('failed');
          setErrorMessage(statusRes.error_message || "Ingestion failed. Try uploading again.");
        }
        // PENDING or PROCESSING: keep polling
      }, 2000);
    }
  };

  const reset = useCallback(() => {
    cleanupInterval();
    setUploadPhase('idle');
    setTrackingId(null);
    setExtractedMeta(null);
    setErrorMessage(null);
    setProcessingStatus(null);
  }, [cleanupInterval]);

  return {
    uploadPhase,
    trackingId,
    extractedMeta,
    errorMessage,
    processingStatus,
    uploadFile,
    reset,
  };
}
