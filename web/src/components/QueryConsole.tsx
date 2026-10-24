import React, { useState } from 'react';
import { Terminal, Send, Filter, CheckCircle2, AlertCircle } from 'lucide-react';

interface QueryConsoleProps {
  onRunQuery: (question: string, mode: 'bfs' | 'dfs') => Promise<void>;
  queryResults: { question: string; starts: string[]; nodes: any[]; edges: any[] } | null;
  onSelectNodeById: (id: string) => void;
  onClearQuery: () => void;
}

export const QueryConsole: React.FC<QueryConsoleProps> = ({
  onRunQuery,
  queryResults,
  onSelectNodeById,
  onClearQuery,
}) => {
  const [question, setQuestion] = useState('');
  const [mode, setMode] = useState<'bfs' | 'dfs'>('bfs');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    try {
      await onRunQuery(question, mode);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      <div style={{
        padding: '12px 14px',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 600 }}>
          <Terminal size={15} color="var(--accent)" />
          <span>Graph Query Console</span>
        </div>
        {queryResults && (
          <button
            onClick={onClearQuery}
            style={{ background: 'transparent', border: 'none', color: 'var(--accent)', fontSize: 11, cursor: 'pointer' }}
          >
            Clear
          </button>
        )}
      </div>

      <form onSubmit={handleSubmit} style={{ padding: '12px', borderBottom: '1px solid var(--border)' }}>
        <div style={{ position: 'relative', marginBottom: 8 }}>
          <input
            type="text"
            placeholder="Ask anything (e.g. how does pipeline run)..."
            value={question}
            onChange={e => setQuestion(e.target.value)}
            style={{
              width: '100%',
              padding: '8px 32px 8px 10px',
              borderRadius: 6,
              background: 'var(--bg-primary)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontSize: 12,
              outline: 'none',
            }}
          />
          <button
            type="submit"
            disabled={loading || !question.trim()}
            style={{
              position: 'absolute',
              right: 6,
              top: '50%',
              transform: 'translateY(-50%)',
              background: 'transparent',
              border: 'none',
              color: question.trim() ? 'var(--accent)' : 'var(--text-muted)',
              cursor: 'pointer',
              display: 'flex',
            }}
          >
            <Send size={14} />
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 11 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-secondary)' }}>
            <span
              onClick={() => setMode('bfs')}
              style={{
                cursor: 'pointer',
                fontWeight: mode === 'bfs' ? 600 : 400,
                color: mode === 'bfs' ? 'var(--accent)' : 'inherit',
              }}
            >
              BFS (Breadth)
            </span>
            <span>·</span>
            <span
              onClick={() => setMode('dfs')}
              style={{
                cursor: 'pointer',
                fontWeight: mode === 'dfs' ? 600 : 400,
                color: mode === 'dfs' ? 'var(--accent)' : 'inherit',
              }}
            >
              DFS (Deep Callflow)
            </span>
          </div>
          <span style={{ color: 'var(--success)', fontSize: 10 }}>Unlimited Depth</span>
        </div>
      </form>

      {/* Query Subgraph Response */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
        {queryResults ? (
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6 }}>
              Seeds found: <strong>{queryResults.starts.join(', ')}</strong>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 10 }}>
              Matched Subgraph: <strong>{queryResults.nodes.length}</strong> nodes · <strong>{queryResults.edges.length}</strong> edges
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {queryResults.nodes.map(n => (
                <div
                  key={n.id}
                  onClick={() => onSelectNodeById(n.id)}
                  style={{
                    padding: '6px 8px',
                    borderRadius: 6,
                    background: 'var(--bg-card)',
                    fontSize: 12,
                    cursor: 'pointer',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'var(--bg-card)')}
                >
                  <span style={{ fontWeight: 500 }}>{n.label}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', marginTop: 40 }}>
            Type a query to traverse the code graph without token caps or node limits.
          </div>
        )}
      </div>
    </div>
  );
};
