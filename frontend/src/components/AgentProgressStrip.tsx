import React from 'react';
import { AGENT_SEQUENCE } from '../constants/agents';

interface AgentProgressStripProps {
  simulatedStatuses: Record<string, string>;
  realStatuses: Record<string, string>;
  loading: boolean;
}

const AgentProgressStrip: React.FC<AgentProgressStripProps> = ({
  simulatedStatuses,
  realStatuses,
  loading,
}) => {
  if (!loading && Object.keys(realStatuses).length === 0) return null;

  const displayStatuses = loading ? simulatedStatuses : realStatuses;

  return (
    <div className="analysis-loading animate-fade-in">
      <div className="analysis-spinner" />
      <h2>{loading ? 'Analysing...' : 'Complete'}</h2>
      <p>{loading ? 'Agents are working in parallel...' : 'All agents finished.'}</p>

      <div className="agent-progress">
        {AGENT_SEQUENCE.map(({ key, label, icon }) => {
          const status = displayStatuses[key] || 'idle';

          return (
            <div
              key={key}
              className={`agent-step ${status === 'running' ? 'active' : ''} ${status === 'completed' ? 'done' : ''} ${status === 'error' ? 'error' : ''}`}
            >
              <span className="agent-step-icon">{icon}</span>
              <span className="agent-step-label">{label}</span>
              <span className="agent-step-status-text">{getStatusText(status)}</span>
              <div className={`agent-step-dot ${status}`} />
            </div>
          );
        })}
      </div>
    </div>
  );
};

function getStatusText(status: string): string {
  switch (status) {
    case 'running':   return 'Working...';
    case 'completed': return 'Done';
    case 'error':     return 'Failed';
    case 'idle':      return 'Waiting';
    default:          return '';
  }
}

export default AgentProgressStrip;
