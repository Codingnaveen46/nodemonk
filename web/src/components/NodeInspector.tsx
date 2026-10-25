import React, { useEffect, useState } from 'react';
import { GraphNode, GraphEdge } from '../types';
import { X, FileCode, ArrowDownLeft, ArrowUpRight, Network } from 'lucide-react';

interface NodeInspectorProps {
  node: GraphNode | null;
  onClose: () => void;
  onSelectNodeById: (id: string) => void;
  communityColors: Record<number, string>;
  allEdges?: GraphEdge[];
  allNodes?: GraphNode[];
}

export const NodeInspector: React.FC<NodeInspectorProps> = ({
  node,
  onClose,
  onSelectNodeById,
  communityColors,
  allEdges = [],
  allNodes = [],
}) => {
  const [details, setDetails] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!node) {
      setDetails(null);
      return;
    }

    const computeLocalDetails = () => {
      const nid = node.id;
      const incoming: any[] = [];
      const outgoing: any[] = [];
      const nbrSet = new Set<string>();
      const nodeById = new Map<string, GraphNode>(allNodes.map(n => [n.id, n]));

      // Same entry shape the HTTP API returns (id/to/node/label/file/kind) so
      // rows render labels and click-through works in embedded graph.html too.
      const entryFor = (otherId: string, relation?: string, confidence?: string) => {
        const nd: any = nodeById.get(otherId);
        return {
          id: otherId,
          to: otherId,
          node: otherId,
          label: nd?.label || otherId,
          file: nd?.file || nd?.source_file,
          kind: nd?.kind,
          relation: relation || 'CALLS',
          confidence: confidence || 'EXTRACTED',
        };
      };

      allEdges.forEach(e => {
        const s = typeof e.source === 'object' ? (e.source as any).id : e.source;
        const t = typeof e.target === 'object' ? (e.target as any).id : e.target;
        if (s === nid) {
          outgoing.push(entryFor(t, e.relation, e.confidence));
          nbrSet.add(t);
        }
        if (t === nid) {
          incoming.push(entryFor(s, e.relation, e.confidence));
          nbrSet.add(s);
        }
      });

      setDetails({
        node: {
          id: node.id,
          label: node.label || node.id,
          file: node.file || node.source_file,
          source_location: node.source_location,
          kind: node.kind,
          community: node.community,
          degree: incoming.length + outgoing.length,
          docstring: node.docstring,
        },
        incoming,
        outgoing,
        neighbors: Array.from(nbrSet).map(id => entryFor(id, 'links', 'EXTRACTED')),
        community_meta: {
          id: node.community,
          label: `Community ${node.community}`,
          cohesion: 0.85,
        }
      });
    };

    if (window.location.protocol.startsWith('http')) {
      setLoading(true);
      fetch(`/api/node/${encodeURIComponent(node.id)}`)
        .then(res => {
          if (!res.ok) throw new Error('API unavailable');
          return res.json();
        })
        .then(data => setDetails(data))
        .catch(() => {
          computeLocalDetails();
        })
        .finally(() => setLoading(false));
    } else {
      computeLocalDetails();
    }
  }, [node, allEdges, allNodes]);

  if (!node) return null;

  const color = (node.community !== undefined && communityColors[node.community]) || '#3b82f6';
  const totalConns = (details?.neighbors?.length) || (node.degree) || 0;

  return (
    <div style={{
      width: 360,
      background: 'var(--bg-secondary)',
      borderLeft: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      flexShrink: 0,
      zIndex: 15,
      boxShadow: '-4px 0 20px rgba(0, 0, 0, 0.3)',
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
          <span style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            padding: '2px 8px',
            borderRadius: 4,
            fontSize: 11,
            color: '#10b981',
          }}>
            {totalConns} connections
          </span>
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

        {/* Connections Section */}
        {loading ? (
          <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', padding: '20px 0' }}>
            Loading connections...
          </div>
        ) : details ? (
          <div>
            {/* Outgoing Connections */}
            {details.outgoing && details.outgoing.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#10b981', marginBottom: 6, fontWeight: 600 }}>
                  <ArrowUpRight size={14} />
                  <span>CALLS / USES OUT ({details.outgoing.length})</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {details.outgoing.map((out: any, idx: number) => (
                    <div
                      key={idx}
                      onClick={() => onSelectNodeById(out.node || out.id || out.to || out.target)}
                      style={{
                        padding: '6px 8px',
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border)',
                        borderRadius: 6,
                        fontSize: 11,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                      onMouseEnter={e => {
                        e.currentTarget.style.borderColor = '#10b981';
                        e.currentTarget.style.background = 'var(--bg-hover)';
                      }}
                      onMouseLeave={e => {
                        e.currentTarget.style.borderColor = 'var(--border)';
                        e.currentTarget.style.background = 'var(--bg-card)';
                      }}
                    >
                      <div style={{ minWidth: 0, paddingRight: 6 }}>
                        <div style={{ fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {out.label || out.node || out.id || out.target}
                        </div>
                        {out.file && (
                          <div style={{ fontSize: 10, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {out.file}
                          </div>
                        )}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
                        <span style={{ fontSize: 10, color: '#10b981', background: 'rgba(16, 185, 129, 0.1)', padding: '2px 5px', borderRadius: 4 }}>
                          {out.relation || 'calls'}
                        </span>
                        <span style={{
                          fontSize: 9,
                          color: out.confidence === 'INFERRED' ? '#60a5fa' : '#9ca3af',
                          background: 'var(--bg-secondary)',
                          padding: '2px 4px',
                          borderRadius: 3
                        }}>
                          {out.confidence || 'EXT'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Incoming Connections */}
            {details.incoming && details.incoming.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#38bdf8', marginBottom: 6, fontWeight: 600 }}>
                  <ArrowDownLeft size={14} />
                  <span>CALLED / IMPORTED BY ({details.incoming.length})</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {details.incoming.map((inc: any, idx: number) => (
                    <div
                      key={idx}
                      onClick={() => onSelectNodeById(inc.node || inc.id || inc.to || inc.source)}
                      style={{
                        padding: '6px 8px',
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border)',
                        borderRadius: 6,
                        fontSize: 11,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                      onMouseEnter={e => {
                        e.currentTarget.style.borderColor = '#38bdf8';
                        e.currentTarget.style.background = 'var(--bg-hover)';
                      }}
                      onMouseLeave={e => {
                        e.currentTarget.style.borderColor = 'var(--border)';
                        e.currentTarget.style.background = 'var(--bg-card)';
                      }}
                    >
                      <div style={{ minWidth: 0, paddingRight: 6 }}>
                        <div style={{ fontWeight: 600, color: 'var(--text-primary)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {inc.label || inc.node || inc.id || inc.source}
                        </div>
                        {inc.file && (
                          <div style={{ fontSize: 10, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {inc.file}
                          </div>
                        )}
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
                        <span style={{ fontSize: 10, color: '#38bdf8', background: 'rgba(56, 189, 248, 0.1)', padding: '2px 5px', borderRadius: 4 }}>
                          {inc.relation || 'links'}
                        </span>
                        <span style={{
                          fontSize: 9,
                          color: inc.confidence === 'INFERRED' ? '#60a5fa' : '#9ca3af',
                          background: 'var(--bg-secondary)',
                          padding: '2px 4px',
                          borderRadius: 3
                        }}>
                          {inc.confidence || 'EXT'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Fallback to neighbors if incoming & outgoing empty */}
            {(!details.incoming?.length && !details.outgoing?.length && details.neighbors?.length > 0) && (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: 'var(--text-secondary)', marginBottom: 6, fontWeight: 600 }}>
                  <Network size={14} />
                  <span>ALL CONNECTED NEIGHBORS ({details.neighbors.length})</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {details.neighbors.map((nb: any, idx: number) => (
                    <div
                      key={idx}
                      onClick={() => onSelectNodeById(nb.node || nb.id || nb.to)}
                      style={{
                        padding: '6px 8px',
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border)',
                        borderRadius: 6,
                        fontSize: 11,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                      }}
                      onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--accent)')}
                      onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border)')}
                    >
                      <span style={{ fontWeight: 500 }}>{nb.label || nb.to || nb.id}</span>
                      <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>{nb.relation || 'links'}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(!details.neighbors || details.neighbors.length === 0) && (
              <div style={{ fontSize: 11, color: 'var(--text-muted)', fontStyle: 'italic', padding: '10px 0' }}>
                Isolated node with no edge connections.
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
};
