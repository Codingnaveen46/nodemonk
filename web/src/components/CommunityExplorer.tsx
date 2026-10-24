import React from 'react';
import { CommunityInfo } from '../types';
import { Users, Layers, Award } from 'lucide-react';

interface CommunityExplorerProps {
  communities: CommunityInfo[];
  highlightedCommunity: number | null;
  onSelectCommunity: (cid: number | null) => void;
  communityColors: Record<number, string>;
}

export const CommunityExplorer: React.FC<CommunityExplorerProps> = ({
  communities,
  highlightedCommunity,
  onSelectCommunity,
  communityColors,
}) => {
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
          <Layers size={15} color="var(--accent)" />
          <span>Communities ({communities.length})</span>
        </div>
        {highlightedCommunity !== null && (
          <button
            onClick={() => onSelectCommunity(null)}
            style={{
              background: 'transparent',
              border: 'none',
              color: 'var(--accent)',
              fontSize: 11,
              cursor: 'pointer',
            }}
          >
            Clear Filter
          </button>
        )}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '8px' }}>
        {communities.map(c => {
          const isSelected = highlightedCommunity === c.id;
          const color = communityColors[c.id] || '#3b82f6';

          return (
            <div
              key={c.id}
              onClick={() => onSelectCommunity(isSelected ? null : c.id)}
              style={{
                padding: '8px 10px',
                marginBottom: 4,
                borderRadius: 6,
                background: isSelected ? 'var(--bg-hover)' : 'transparent',
                border: isSelected ? `1px solid ${color}` : '1px solid transparent',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                transition: 'background 0.15s ease',
              }}
              onMouseEnter={e => {
                if (!isSelected) e.currentTarget.style.background = 'var(--bg-card)';
              }}
              onMouseLeave={e => {
                if (!isSelected) e.currentTarget.style.background = 'transparent';
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                <div style={{
                  width: 10,
                  height: 10,
                  borderRadius: '50%',
                  backgroundColor: color,
                  flexShrink: 0,
                }} />
                <div style={{ minWidth: 0 }}>
                  <div style={{
                    fontSize: 12,
                    fontWeight: 500,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    color: isSelected ? '#ffffff' : 'var(--text-primary)',
                  }}>
                    {c.label}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                    Cohesion: {(c.cohesion * 100).toFixed(0)}%
                  </div>
                </div>
              </div>

              <div style={{
                background: 'var(--bg-secondary)',
                padding: '2px 6px',
                borderRadius: 10,
                fontSize: 11,
                color: 'var(--text-secondary)',
                flexShrink: 0,
              }}>
                {c.size}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
