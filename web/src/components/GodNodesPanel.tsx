import React, { useState } from 'react';
import { GodNode, GraphNode } from '../types';
import { Crown, Zap, ArrowUpRight } from 'lucide-react';

interface GodNodesPanelProps {
  godNodes: GodNode[];
  onSelectNodeById: (id: string) => void;
}

export const GodNodesPanel: React.FC<GodNodesPanelProps> = ({ godNodes, onSelectNodeById }) => {
  const [metric, setMetric] = useState<'degree' | 'pagerank'>('degree');

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
          <Crown size={15} color="#f59e0b" />
          <span>High-Impact Hubs</span>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '8px' }}>
        {godNodes.map((n, idx) => (
          <div
            key={n.id}
            onClick={() => onSelectNodeById(n.id)}
            style={{
              padding: '8px 10px',
              marginBottom: 4,
              borderRadius: 6,
              background: 'transparent',
              border: '1px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-card)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', width: 14 }}>{idx + 1}</span>
              <div style={{ minWidth: 0 }}>
                <div style={{
                  fontSize: 12,
                  fontWeight: 500,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  color: 'var(--text-primary)',
                }}>
                  {n.label}
                </div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {n.file || n.kind || 'symbol'}
                </div>
              </div>
            </div>

            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              fontSize: 11,
              color: 'var(--accent)',
              fontWeight: 600,
              flexShrink: 0,
            }}>
              <span>{typeof n.score === 'number' ? (n.score > 1 ? n.score : n.score.toFixed(4)) : n.score}</span>
              <ArrowUpRight size={12} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
