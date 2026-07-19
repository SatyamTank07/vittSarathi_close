import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchAllDocuments } from '../api/client';

export function useDocumentLibrary() {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const pollIntervalRef = useRef(null);

  const loadDocuments = useCallback(async () => {
    try {
      const data = await fetchAllDocuments();
      if (data) {
        setDocuments(data);
        setError(null);
        
        // Check if any document is processing
        const isProcessing = data.some(doc => doc.ingestion_status === 'processing' || doc.ingestion_status === 'pending');
        
        if (isProcessing) {
          if (!pollIntervalRef.current) {
            pollIntervalRef.current = setInterval(() => {
              loadDocuments();
            }, 5000);
          }
        } else {
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
          }
        }
      } else {
        setError("Failed to fetch documents.");
      }
    } catch (err) {
      setError("An error occurred while fetching documents.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDocuments();
    
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [loadDocuments]);

  return {
    documents,
    loading,
    error,
    refresh: loadDocuments
  };
}
