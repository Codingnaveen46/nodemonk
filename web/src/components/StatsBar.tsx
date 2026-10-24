import React from 'react';
import { GraphStats } from '../types';
import { Activity, ShieldCheck, Cpu, Download, Database } from 'lucide-react';

interface StatsBarProps {
  stats: GraphStats | null;
  onExport: (format: string) => void;
}

export const StatsBar: React.FC<StatsBarProps> = ({ stats, onExport }) => {
  return (
    <header style={{
      height: 52,
      background: 'var(--bg-secondary)',
      borderBottom: '1px solid var(--border)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 16px',
      gap: 16,
      flexShrink: 0,
      zIndex: 20,
    }}>
      {/* Brand & Title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{
          width: 30,
          height: 30,
          borderRadius: 8,
          background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontWeight: 700,
          fontSize: 16,
          color: '#ffffff',
          boxShadow: '0 0 12px rgba(59, 130, 246, 0.4)'
        }}>
          N
        </div>
        <div>
          <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: '-0.01em' }}>nodemonk</span>
          <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 8 }}>knowledge graph</span>
        </div>
      </div>

      {/* Live Graph Metrics */}
      {stats && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, fontSize: 12, color: 'var(--text-secondary)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Cpu size={14} color="var(--accent)" />
            <span>Nodes: <strong style={{ color: 'var(--text-primary)' }}>{stats.nodes.toLocaleString()}</strong></span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Activity size={14} color="#10b981" />
            <span>Edges: <strong style={{ color: 'var(--text-primary)' }}>{stats.edges.toLocaleString()}</strong></span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span>Avg Degree: <strong style={{ color: 'var(--text-primary)' }}>{stats.avg_degree.toFixed(2)}</strong></span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span>Communities: <strong style={{ color: 'var(--text-primary)' }}>{stats.communities_count}</strong></span>
          </div>

          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            background: 'rgba(16, 185, 129, 0.1)',
            padding: '3px 8px',
            borderRadius: 6,
            color: 'var(--success)',
            fontSize: 11,
          }}>
            <ShieldCheck size={13} />
            <span>Extracted: {stats.confidence_profile['EXTRACTED'] || 0}</span>
          </div>
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <button
          onClick={() => onExport('json')}
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            padding: '6px 10px',
            borderRadius: 6,
            fontSize: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <Database size={13} />
          Export JSON
        </button>
        <button
          onClick={() => onExport('cypher')}
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
            padding: '6px 10px',
            borderRadius: 6,
            fontSize: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <Download size={13} />
          Cypher / Neo4j
        </button>
      </div>
    </header>
  );
};
