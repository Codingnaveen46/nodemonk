import React, { useEffect, useState } from 'react';
import { GraphNode } from '../types';
import { X, FileCode, Tag, Network, ArrowDownLeft, ArrowUpRight, ShieldCheck, Compass } from 'lucide-react';

interface NodeInspectorProps {
  node: GraphNode | null;
  onClose: () => void;
  onSelectNodeById: (id: string) => void;
  communityColors: Record<number, string>;
}

export const NodeInspector: React.FC<NodeInspectorProps> = ({
  node,
  onClose,
  onSelectNodeById,
  communityColors,
}) => {
  const [details, setDetails] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!node) {
      setDetails(null);
      return;
    }
    setLoading(true);
    fetch(`/api/node/${encodeURIComponent(node.id)}`)
      .then(res => res.json())
      .then(data => setDetails(data))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, [node]);

  if (!node) return null;

  const color = (node.community !== undefined && communityColors[node.community]) || '#3b82f6';

  return (
    <div style={{
      width: 340,
      background: 'var(--bg-secondary)',
      borderLeft: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      flexShrink: 0,
      zIndex: 15,
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 14px',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{ width: 10, height: 10, borderRadius: '50%', backgroundColor: color }} />
          <span style={{ fontSize: 13, fontWeight: 600 }}>Node Details</span>
        </div>
        <button
          onClick={onClose}
          style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
        >
          <X size={16} />
        </button>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '14px' }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, wordBreak: 'break-word', marginBottom: 4 }}>
          {node.label || node.id}
        </h2>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', wordBreak: 'break-all', marginBottom: 14 }}>
          {node.id}
        </div>

        {/* Badges */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 14 }}>
          {node.kind && (
            <span style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border)',
              padding: '2px 8px',
              borderRadius: 4,
              fontSize: 11,
              color: 'var(--accent)',
            }}>
              {node.kind}
            </span>
          )}
          {node.community !== undefined && (
            <span style={{
              background: 'var(--bg-card)',
              border: `1px solid ${color}`,
              padding: '2px 8px',
              borderRadius: 4,
              fontSize: 11,
              color: '#ffffff',
            }}>
              Comm #{node.community}
            </span>
          )}
        </div>

        {/* Source File Location */}
        {(node.file || node.source_file) && (
          <div style={{
            background: 'var(--bg-card)',
            padding: 10,
            borderRadius: 6,
            border: '1px solid var(--border)',
            marginBottom: 14,
            fontSize: 12,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-secondary)', marginBottom: 4 }}>
              <FileCode size={14} />
              <span>Source Location</span>
            </div>
            <div style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--text-primary)', wordBreak: 'break-all' }}>
              {node.file || node.source_file} {node.source_location ? `(${node.source_location})` : ''}
            </div>
          </div>
        )}

        {/* Docstring */}
        {node.docstring && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 4, fontWeight: 600 }}>
              DOCSTRING / DESCRIPTION
            </div>
            <div style={{
              background: 'var(--bg-primary)',
              padding: 8,
              borderRadius: 6,
              fontSize: 11,
              lineHeight: 1.5,
              color: 'var(--text-secondary)',
              whiteSpace: 'pre-wrap',
            }}>
              {node.docstring}
            </div>
          </div>
        )}

        {/* Neighbors / Edges */}
        {details && (
          <div>
            {details.incoming && details.incoming.length > 0 && (
              <div style={{ marginBottom: 14 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 600 }}>
                  <ArrowDownLeft size={13} color="var(--accent)" />
                  <span>CALLED / IMPORTED BY ({details.incoming.length})</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {details.incoming.map((inc: any, idx: number) => (
                    <div
                      key={idx}
                      onClick={() => onSelectNodeById(inc.node || inc.id)}
                      style={{
                        padding: '6px 8px',
                        background: 'var(--bg-card)',
                        borderRadius: 4,
                        fontSize: 11,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                      onMouseLeave={e => (e.currentTarget.style.background = 'var(--bg-card)')}
                    >
                      <span style={{ fontWeight: 500 }}>{inc.label || inc.node || inc.id}</span>
                      <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>{inc.relation || 'links'}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {details.outgoing && details.outgoing.length > 0 && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, fontWeight: 600 }}>
                  <ArrowUpRight size={13} color="#10b981" />
                  <span>CALLS / USES OUT ({details.outgoing.length})</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {details.outgoing.map((out: any, idx: number) => (
                    <div
                      key={idx}
                      onClick={() => onSelectNodeById(out.node || out.id)}
                      style={{
                        padding: '6px 8px',
                        background: 'var(--bg-card)',
                        borderRadius: 4,
                        fontSize: 11,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-hover)')}
                      onMouseLeave={e => (e.currentTarget.style.background = 'var(--bg-card)')}
                    >
                      <span style={{ fontWeight: 500 }}>{out.label || out.node || out.id}</span>
                      <span style={{ fontSize: 9, color: 'var(--text-muted)' }}>{out.relation || 'links'}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
