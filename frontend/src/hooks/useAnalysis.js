import { useReducer, useRef } from 'react';
import { analyze } from '../api/client.js';
import { AGENT_SEQUENCE } from '../constants/agents';

const initialState = {
  // dashboard data — the full SharedState from backend
  dashboardData: null,          // null until first dashboard response

  // chat history — separate from dashboard, own list
  chatHistory: [],              // array of { role: 'user'|'assistant', content: string, type: 'chat'|'patch_confirm' }

  // session tracking
  sessionId: null,              // string UUID after first dashboard response
  existingStateHash: null,      // MD5 string for stale state detection

  // response type of the last response
  lastResponseType: null,       // 'dashboard' | 'chat' | 'patch' | null

  // loading and error
  loading: false,
  error: null,

  // agent progress — driven by agent_statuses from response
  agentStatuses: {},            // mirrors backend agent_statuses field
  simulatedStatuses: {},        // fake progress during loading

  // clarification
  clarificationNeeded: false,
  clarificationCandidates: [],  // array of { ticker, company_name }
  clarificationMessage: '',

  highlightedCards: new Set(),
};

function computeStateHash(obj) {
  const str = JSON.stringify(obj);
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // convert to 32-bit int
  }
  return hash.toString(16);
}

function mergeChangedPaths(currentData, changedPaths) {
  // deep clone first — never mutate state directly
  const next = JSON.parse(JSON.stringify(currentData));

  for (const [dotPath, value] of Object.entries(changedPaths)) {
    const keys = dotPath.split('.');
    let cursor = next;
    for (let i = 0; i < keys.length - 1; i++) {
      if (cursor[keys[i]] === undefined) cursor[keys[i]] = {};
      cursor = cursor[keys[i]];
    }
    cursor[keys[keys.length - 1]] = value;
  }

  return next;
}

function reducer(state, action) {
  switch (action.type) {
    case 'SUBMIT_START':
      return {
        ...state,
        loading: true,
        error: null,
        clarificationNeeded: false,
        clarificationCandidates: [],
        clarificationMessage: '',
      };

    case 'SIMULATED_PROGRESS':
      return {
        ...state,
        simulatedStatuses: action.payload,
      };

    case 'CLEAR_SIMULATED_PROGRESS':
      return {
        ...state,
        simulatedStatuses: {},
      };

    case 'DASHBOARD_SUCCESS':
      return {
        ...state,
        dashboardData: action.payload,
        sessionId: action.payload.session_id,
        existingStateHash: computeStateHash(action.payload),
        lastResponseType: 'dashboard',
        agentStatuses: action.payload.agent_statuses || {},
        highlightedCards: new Set(),
        loading: false
      };

    case 'CHAT_SUCCESS':
      return {
        ...state,
        sessionId: action.payload.session_id || state.sessionId,
        chatHistory: [
          ...state.chatHistory,
          { role: 'assistant', content: action.payload.targeted_answer, type: 'chat' }
        ],
        loading: false
      };

    case 'PATCH_SUCCESS': {
      const mergedData = mergeChangedPaths(state.dashboardData || {}, action.payload.state_patch.changed_paths);
      const changedPaths = new Set(Object.keys(action.payload.state_patch.changed_paths));
      return {
        ...state,
        dashboardData: mergedData,
        sessionId: action.payload.session_id || state.sessionId,
        existingStateHash: computeStateHash(mergedData),
        highlightedCards: changedPaths,
        chatHistory: [
          ...state.chatHistory,
          { role: 'assistant', content: action.payload.state_patch.patch_summary, type: 'patch_confirm' }
        ],
        loading: false
      };
    }

    case 'CLARIFICATION_NEEDED':
      return {
        ...state,
        clarificationNeeded: true,
        clarificationCandidates: action.payload.candidates || [],
        clarificationMessage: action.payload.clarification_message,
        loading: false
      };

    case 'ERROR':
      return {
        ...state,
        error: action.payload,
        loading: false
      };

    case 'ADD_USER_MESSAGE':
      return {
        ...state,
        chatHistory: [
          ...state.chatHistory,
          { role: 'user', content: action.payload }
        ]
      };

    default:
      return state;
  }
}

export function useAnalysis() {
  const [state, dispatch] = useReducer(reducer, initialState);

  const simulationTimers = useRef([]);

  const clearSimulation = () => {
    simulationTimers.current.forEach(id => clearTimeout(id));
    simulationTimers.current = [];
  };

  const startSimulation = () => {
    clearSimulation();

    let elapsed = 0;

    AGENT_SEQUENCE.forEach((agent, idx) => {
      const startTime = elapsed;

      const startTimer = setTimeout(() => {
        const statuses = {};
        AGENT_SEQUENCE.forEach((a, i) => {
          if (i < idx)        statuses[a.key] = 'completed';
          else if (i === idx) statuses[a.key] = 'running';
          else                statuses[a.key] = 'idle';
        });
        dispatch({ type: 'SIMULATED_PROGRESS', payload: statuses });
      }, startTime);

      simulationTimers.current.push(startTimer);
      elapsed += agent.durationMs;
    });
  };

  const submitQuery = async (query) => {
    if (!query.trim()) return;

    // 1. immediately add user message to chat history
    dispatch({ type: 'ADD_USER_MESSAGE', payload: query });

    // 2. start loading
    dispatch({ type: 'SUBMIT_START' });

    startSimulation();

    try {
      // 3. call the API client
      const response = await analyze(query, state.sessionId, state.existingStateHash);

      clearSimulation();
      dispatch({ type: 'CLEAR_SIMULATED_PROGRESS' });

      // 4. route based on response
      if (response.status === 'error') {
        dispatch({ type: 'ERROR', payload: response.error_message });
        return;
      }

      if (response.status === 'clarification_needed') {
        dispatch({ type: 'CLARIFICATION_NEEDED', payload: response });
        return;
      }

      if (response.response_type === 'dashboard') {
        dispatch({ type: 'DASHBOARD_SUCCESS', payload: response });
        return;
      }

      if (response.response_type === 'chat') {
        dispatch({ type: 'CHAT_SUCCESS', payload: response });
        return;
      }

      if (response.response_type === 'patch') {
        dispatch({ type: 'PATCH_SUCCESS', payload: response });
        return;
      }
    } catch (err) {
      clearSimulation();
      dispatch({ type: 'CLEAR_SIMULATED_PROGRESS' });
      dispatch({ type: 'ERROR', payload: err.message || 'An unexpected error occurred' });
    }
  };

  // clarification resolution — user picks a candidate
  const resolveClarification = (ticker, companyName) => {
    // re-submit with the resolved ticker pre-filled in the query
    submitQuery(`Analyse ${companyName} (${ticker})`);
  };

  return {
    // state
    dashboardData:            state.dashboardData,
    chatHistory:              state.chatHistory,
    loading:                  state.loading,
    error:                    state.error,
    agentStatuses:            state.agentStatuses,
    lastResponseType:         state.lastResponseType,
    clarificationNeeded:      state.clarificationNeeded,
    clarificationCandidates:  state.clarificationCandidates,
    clarificationMessage:     state.clarificationMessage,
    sessionId:                state.sessionId,
    highlightedCards:         state.highlightedCards,
    simulatedStatuses:        state.simulatedStatuses,

    // actions
    submitQuery,
    resolveClarification,
  };
}
