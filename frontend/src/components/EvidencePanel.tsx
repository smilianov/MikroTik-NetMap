import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import {
  getTopologyDryRun,
  listTopologyEvidence,
  type TopologyDryRunResponse,
  type TopologyEvidenceObservation,
} from '../api/evidence';

interface EvidencePanelProps {
  onClose: () => void;
}

export function EvidencePanel({ onClose }: EvidencePanelProps) {
  const [source, setSource] = useState<string>('');
  const [items, setItems] = useState<TopologyEvidenceObservation[]>([]);
  const [sources, setSources] = useState<Record<string, number>>({});
  const [count, setCount] = useState(0);
  const [dryRun, setDryRun] = useState<TopologyDryRunResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const sourceOptions = useMemo(
    () => Object.entries(sources).sort(([a], [b]) => a.localeCompare(b)),
    [sources],
  );

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      listTopologyEvidence(source || undefined),
      getTopologyDryRun(),
    ])
      .then(([result, dryRunResult]) => {
        if (cancelled) return;
        setItems(result.items);
        setSources(result.sources);
        setCount(result.count);
        setDryRun(dryRunResult);
        setError(null);
        setLoading(false);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load evidence');
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [source, refreshKey]);

  return (
    <div style={panelStyle}>
      <div style={headerStyle}>
        <div>
          <div style={titleStyle}>Topology Evidence</div>
          <div style={subtitleStyle}>{count} observations</div>
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          <button onClick={() => setRefreshKey((value) => value + 1)} style={iconButtonStyle} title="Refresh evidence">
            R
          </button>
          <button onClick={onClose} style={iconButtonStyle} title="Close">
            x
          </button>
        </div>
      </div>

      <div style={tabsStyle}>
        <button
          onClick={() => setSource('')}
          style={source === '' ? activeTabStyle : tabStyle}
        >
          All
        </button>
        {sourceOptions.map(([name, total]) => (
          <button
            key={name}
            onClick={() => setSource(name)}
            style={source === name ? activeTabStyle : tabStyle}
          >
            {name} {total}
          </button>
        ))}
      </div>

      {dryRun && (
        <div style={dryRunStyle}>
          <div style={dryRunMetricStyle}>
            <span style={mutedStyle}>Candidates</span>
            <strong>{dryRun.candidate_count}</strong>
          </div>
          <div style={dryRunMetricStyle}>
            <span style={mutedStyle}>Covered</span>
            <strong>{dryRun.covered_pair_count}</strong>
          </div>
          <div style={dryRunMetricStyle}>
            <span style={mutedStyle}>Unresolved</span>
            <strong>{dryRun.unresolved_observation_count}</strong>
          </div>
          {dryRun.candidates.slice(0, 3).map((candidate) => (
            <div key={`${candidate.source_device}-${candidate.target_device}`} style={candidateStyle}>
              <span style={nodeStyle}>{candidate.source_device}</span>
              <span style={mutedStyle}>to</span>
              <span style={nodeStyle}>{candidate.target_device}</span>
              <span style={mutedStyle}>{Math.round(candidate.confidence * 100)}%</span>
            </div>
          ))}
        </div>
      )}

      {error && <div style={messageStyle}>{error}</div>}
      {loading && <div style={messageStyle}>Loading...</div>}
      {!loading && !error && items.length === 0 && (
        <div style={messageStyle}>No observations</div>
      )}

      {!loading && !error && items.length > 0 && (
        <div style={tableWrapStyle}>
          <table style={tableStyle}>
            <thead>
              <tr>
                <th style={thStyle}>Source</th>
                <th style={thStyle}>Observation</th>
                <th style={thStyle}>Confidence</th>
                <th style={thStyle}>Details</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id}>
                  <td style={tdStyle}>
                    <div style={monoStyle}>{item.source}</div>
                    <div style={mutedStyle}>{item.evidence_type}</div>
                  </td>
                  <td style={tdStyle}>
                    <div style={nodeStyle}>{item.source_identity || item.source_node}</div>
                    <div style={mutedStyle}>to</div>
                    <div style={nodeStyle}>{item.target_identity || item.target_node}</div>
                  </td>
                  <td style={tdStyle}>{Math.round(item.confidence * 100)}%</td>
                  <td style={tdStyle}>{formatMetadata(item.metadata)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function formatMetadata(metadata: Record<string, unknown>): string {
  const interfaceName = metadata.interface;
  const vlanId = metadata.vlan_id;
  const vlanText = typeof vlanId === 'string' || typeof vlanId === 'number'
    ? String(vlanId)
    : '';
  const destinations = metadata.destination_identities;
  if (typeof interfaceName === 'string' && interfaceName) {
    return vlanText ? `${interfaceName} / VLAN ${vlanText}` : interfaceName;
  }
  if (Array.isArray(destinations) && destinations.length > 0) {
    return destinations.slice(0, 3).join(', ');
  }
  return '';
}

const panelStyle: React.CSSProperties = {
  position: 'absolute',
  right: '60px',
  bottom: '16px',
  width: 'min(560px, calc(100vw - 84px))',
  maxHeight: '420px',
  display: 'flex',
  flexDirection: 'column',
  background: '#111827',
  border: '1px solid #374151',
  borderRadius: '8px',
  color: '#E5E7EB',
  fontFamily: 'Inter, system-ui, sans-serif',
  zIndex: 90,
  boxShadow: '0 12px 30px rgba(0,0,0,0.35)',
};

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '12px',
  borderBottom: '1px solid #374151',
};

const titleStyle: React.CSSProperties = {
  fontSize: '14px',
  fontWeight: 700,
  color: '#F9FAFB',
};

const subtitleStyle: React.CSSProperties = {
  fontSize: '11px',
  color: '#9CA3AF',
  marginTop: '2px',
};

const iconButtonStyle: React.CSSProperties = {
  width: '30px',
  height: '30px',
  border: '1px solid #374151',
  borderRadius: '6px',
  background: '#1F2937',
  color: '#D1D5DB',
  cursor: 'pointer',
  fontSize: '12px',
  fontWeight: 700,
};

const tabsStyle: React.CSSProperties = {
  display: 'flex',
  gap: '6px',
  padding: '10px 12px',
  borderBottom: '1px solid #1F2937',
  overflowX: 'auto',
};

const tabStyle: React.CSSProperties = {
  padding: '5px 9px',
  border: '1px solid #374151',
  borderRadius: '6px',
  background: '#111827',
  color: '#9CA3AF',
  cursor: 'pointer',
  fontSize: '12px',
  whiteSpace: 'nowrap',
};

const activeTabStyle: React.CSSProperties = {
  ...tabStyle,
  background: '#1F2937',
  color: '#F9FAFB',
  border: '1px solid #60A5FA',
};

const messageStyle: React.CSSProperties = {
  padding: '20px',
  color: '#9CA3AF',
  fontSize: '13px',
};

const dryRunStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(3, minmax(0, 1fr))',
  gap: '8px',
  padding: '10px 12px',
  borderBottom: '1px solid #1F2937',
};

const dryRunMetricStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'baseline',
  justifyContent: 'space-between',
  gap: '8px',
  padding: '7px 8px',
  background: '#1F2937',
  border: '1px solid #374151',
  borderRadius: '6px',
  fontSize: '12px',
};

const candidateStyle: React.CSSProperties = {
  gridColumn: '1 / -1',
  display: 'grid',
  gridTemplateColumns: 'minmax(0, 1fr) auto minmax(0, 1fr) auto',
  gap: '8px',
  alignItems: 'center',
  padding: '7px 8px',
  background: '#111827',
  border: '1px solid #1F2937',
  borderRadius: '6px',
  fontSize: '12px',
};

const tableWrapStyle: React.CSSProperties = {
  overflow: 'auto',
};

const tableStyle: React.CSSProperties = {
  width: '100%',
  borderCollapse: 'collapse',
  fontSize: '12px',
};

const thStyle: React.CSSProperties = {
  position: 'sticky',
  top: 0,
  background: '#111827',
  color: '#9CA3AF',
  fontWeight: 600,
  textAlign: 'left',
  padding: '8px 10px',
  borderBottom: '1px solid #374151',
};

const tdStyle: React.CSSProperties = {
  padding: '8px 10px',
  borderBottom: '1px solid #1F2937',
  verticalAlign: 'top',
  color: '#D1D5DB',
};

const monoStyle: React.CSSProperties = {
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
  color: '#F9FAFB',
};

const nodeStyle: React.CSSProperties = {
  maxWidth: '180px',
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
};

const mutedStyle: React.CSSProperties = {
  color: '#6B7280',
  fontSize: '11px',
};
