import { fetchWithAuth as fetch } from './fetchWithAuth';

export interface TopologyEvidenceObservation {
  id: string;
  source: string;
  evidence_type: string;
  source_node: string;
  target_node: string;
  source_identity: string | null;
  target_identity: string | null;
  confidence: number;
  observed_at: string;
  metadata: Record<string, unknown>;
}

export interface TopologyEvidenceResponse {
  items: TopologyEvidenceObservation[];
  count: number;
  sources: Record<string, number>;
}

export interface TopologyDryRunCandidate {
  source_device: string;
  target_device: string;
  confidence: number;
  evidence_count: number;
  evidence_sources: string[];
  evidence_types: string[];
  status: string;
  reason: string;
}

export interface TopologyDryRunResponse {
  candidates: TopologyDryRunCandidate[];
  candidate_count: number;
  covered_pair_count: number;
  unresolved_observation_count: number;
  evidence_count: number;
}

export async function listTopologyEvidence(source?: string): Promise<TopologyEvidenceResponse> {
  const params = new URLSearchParams();
  if (source) params.set('source', source);
  const query = params.toString();
  const res = await fetch(`/api/topology/evidence${query ? `?${query}` : ''}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Evidence request failed with HTTP ${res.status}`);
  }
  return res.json();
}

export async function getTopologyDryRun(): Promise<TopologyDryRunResponse> {
  const res = await fetch('/api/topology/dry-run');
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Dry-run request failed with HTTP ${res.status}`);
  }
  return res.json();
}
