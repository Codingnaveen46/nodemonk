export interface GraphNode {
  id: string;
  label: string;
  file?: string;
  source_file?: string;
  source_location?: string;
  kind?: string;
  community?: number;
  docstring?: string;
  in_degree?: number;
  out_degree?: number;
  degree?: number;
  pagerank?: number;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
}

export interface GraphEdge {
  source: string | GraphNode;
  target: string | GraphNode;
  relation?: string;
  confidence?: 'EXTRACTED' | 'INFERRED' | 'AMBIGUOUS';
  weight?: number;
}

export interface CommunityInfo {
  id: number;
  label: string;
  size: number;
  cohesion: number;
  members: string[];
}

export interface GraphStats {
  nodes: number;
  edges: number;
  avg_degree: number;
  median_degree: number;
  max_degree: number;
  self_loops: number;
  edge_density: number;
  confidence_profile: Record<string, number>;
  communities_count: number;
  modularity?: number;
}

export interface GodNode {
  id: string;
  label: string;
  score: number;
  kind?: string;
  file?: string;
}

export interface CycleInfo {
  cycle: string[];
  length: number;
}
