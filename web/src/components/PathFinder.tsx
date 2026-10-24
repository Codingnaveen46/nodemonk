import React, { useState } from 'react';
import { GraphNode } from '../types';
import { GitCommit, ArrowRight, Search, CheckCircle2, AlertCircle } from 'lucide-react';

interface PathFinderProps {
  nodes: GraphNode[];
  onFindPath: (sourceId: string, targetId: string) => Promise<string[] | null>;
  activePath: string[] | null;
  onClearPath: () => void;
  onSelectNodeById: (id: string) => void;
}

export const PathFinder: React.FC<PathFinderProps> = ({
  nodes,
  onFindPath,
  activePath,
  onClearPath,
  onSelectNodeById,
}) => {
  const [sourceQuery, setSourceQuery] = useState('');
  const [targetQuery, setTargetQuery] = useState('');
  const [sourceId, setSourceId] = useState<string>('');
  const [targetId, setTargetId] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const filterNodes = (q: string) => {
    if (!q.trim()) return [];
    const term = q.toLowerCase();
    return nodes.filter(n => n.label.toLowerCase().includes(term) || n.id.toLowerCase().includes(term)).slice(0, 6);
  };

  const handleSearch = async () => {
    if (!sourceId || !targetId) {
      setError('Please select both a source and target node.');
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const res = await onFindPath(sourceId, targetId);
      if (!res || res.length === 0) {
        setError('No path exists between these two nodes.');
      }
    } catch (e: any) {
      setError(e.message || 'Failed to compute path.');
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
          <GitCommit size={15} color="var(--accent)" />
          <span>Path Finder</span>
        </div>
        {activePath && (
          <button
            onClick={onClearPath}
            style={{ background: 'transparent', border: 'none', color: 'var(--accent)', fontSize: 11, cursor: 'pointer' }}
          >
            Clear
          </button>
        )}
      </div>

      <div style={{ padding: '12px', display: 'flex', flexDirection: 'column', gap: 10 }}>
        {/* Source selector */}
        <div>
          <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>
            Source Node:
          </label>
          <input
            type="text"
            placeholder="Search source node..."
            value={sourceQuery}
            onChange={e => {
              setSourceQuery(e.target.value);
              setSourceId('');
            }}
            style={{
              width: '100%',
              padding: '6px 10px',
              borderRadius: 6,
              background: 'var(--bg-primary)',
              border: `1px solid ${sourceId ? 'var(--success)' : 'var(--border)'}`,
              color: 'var(--text-primary)',
              fontSize: 12,
              outline: 'none',
            }}
          />
          {sourceQuery && !sourceId && (
            <div style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              marginTop: 4,
              maxHeight: 120,
              overflowY: 'auto',
            }}>
              {filterNodes(sourceQuery).map(n => (
                <div
                  key={n.id}
                  onClick={() => {
                    setSourceId(n.id);
                    setSourceQuery(n.label);
                  }}
                  style={{ padding: '4px 8px', fontSize: 11, cursor: 'pointer' }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  {n.label} <span style={{ color: 'var(--text-muted)' }}>({n.file || n.kind})</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Target selector */}
        <div>
          <label style={{ fontSize: 11, color: 'var(--text-secondary)', display: 'block', marginBottom: 4 }}>
            Target Node:
          </label>
          <input
            type="text"
            placeholder="Search target node..."
            value={targetQuery}
            onChange={e => {
              setTargetQuery(e.target.value);
              setTargetId('');
            }}
            style={{
              width: '100%',
              padding: '6px 10px',
              borderRadius: 6,
              background: 'var(--bg-primary)',
              border: `1px solid ${targetId ? 'var(--success)' : 'var(--border)'}`,
              color: 'var(--text-primary)',
              fontSize: 12,
              outline: 'none',
            }}
          />
          {targetQuery && !targetId && (
            <div style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              marginTop: 4,
              maxHeight: 120,
              overflowY: 'auto',
            }}>
              {filterNodes(targetQuery).map(n => (
                <div
                  key={n.id}
                  onClick={() => {
                    setTargetId(n.id);
                    setTargetQuery(n.label);
                  }}
                  style={{ padding: '4px 8px', fontSize: 11, cursor: 'pointer' }}
                  onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                  onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                >
                  {n.label} <span style={{ color: 'var(--text-muted)' }}>({n.file || n.kind})</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <button
          onClick={handleSearch}
          disabled={loading || !sourceId || !targetId}
          style={{
            background: 'var(--accent)',
            border: 'none',
            color: '#ffffff',
            padding: '7px 12px',
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            opacity: loading || !sourceId || !targetId ? 0.5 : 1,
          }}
        >
          <Search size={14} />
          {loading ? 'Finding Path...' : 'Find Shortest Path'}
        </button>

        {error && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            color: 'var(--danger)',
            fontSize: 11,
            background: 'rgba(239, 68, 68, 0.1)',
            padding: 8,
            borderRadius: 6,
          }}>
            <AlertCircle size={14} />
            <span>{error}</span>
          </div>
        )}
      </div>

      {/* Path result trace */}
      {activePath && (
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 12px 12px' }}>
          <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 8, fontWeight: 600 }}>
            Trace ({activePath.length} hops):
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {activePath.map((nodeId, idx) => {
              const node = nodes.find(n => n.id === nodeId);
              return (
                <div
                  key={nodeId}
                  onClick={() => onSelectNodeById(nodeId)}
                  style={{
                    padding: '6px 8px',
                    borderRadius: 6,
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border)',
                    fontSize: 12,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                  onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--accent)')}
                  onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border)')}
                >
                  <span style={{ fontWeight: 500 }}>{node?.label || nodeId}</span>
                  <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>Step {idx + 1}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
