import { useState, useEffect } from 'react';
import { checkHealth } from '../api/client';

export function useHealthCheck() {
  const [isOnline, setIsOnline] = useState(true);

  useEffect(() => {
    let mounted = true;

    const performCheck = async () => {
      const status = await checkHealth();
      if (mounted) {
        setIsOnline(status);
      }
    };

    // Initial check
    performCheck();

    // Polling interval
    const intervalId = setInterval(performCheck, 3000);

    return () => {
      mounted = false;
      clearInterval(intervalId);
    };
  }, []);

  return { isOnline };
}
