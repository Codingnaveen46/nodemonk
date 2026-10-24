import React from 'react';
import { CycleInfo } from '../types';
import { RefreshCw, ArrowRight } from 'lucide-react';

interface CycleViewerProps {
  cycles: CycleInfo[];
  onSelectNodeById: (id: string) => void;
}

export const CycleViewer: React.FC<CycleViewerProps> = ({ cycles, onSelectNodeById }) => {
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
          <RefreshCw size={15} color="#ef4444" />
          <span>Dependency Cycles ({cycles.length})</span>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
        {cycles.length === 0 ? (
          <div style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', marginTop: 40 }}>
            Clean architecture! No circular dependency loops detected.
          </div>
        ) : (
          cycles.map((c, i) => (
            <div
              key={i}
              style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border)',
                borderRadius: 8,
                padding: '10px',
                marginBottom: 10,
              }}
            >
              <div style={{ fontSize: 11, color: '#ef4444', fontWeight: 600, marginBottom: 6 }}>
                Cycle #{i + 1} ({c.length} nodes)
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {c.cycle.map((nodeId, idx) => (
                  <div
                    key={idx}
                    onClick={() => onSelectNodeById(nodeId)}
                    style={{
                      fontSize: 12,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                    }}
                  >
                    <ArrowRight size={12} color="var(--text-muted)" />
                    <span style={{ color: 'var(--text-primary)' }}>{nodeId}</span>
                  </div>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
