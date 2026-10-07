export type StreamProfile = {
  id: string;
  name: string;
  url: string;
  transport: 'auto' | 'tcp' | 'udp';
  codec: string | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  bitrate: number | null;
  latency_profile: 'ultra-low' | 'low' | 'normal' | 'stable';
  priority: number;
};

export type Camera = {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  vendor: string;
  model: string | null;
  host: string | null;
  tags: string[];
  location: string | null;
  username: string | null;
  has_password: boolean;
  stream_profiles: StreamProfile[];
  created_at: string;
  updated_at: string;
};

export type Crop = { top: number; right: number; bottom: number; left: number };
export type SlotType = 'fixed' | 'rotation' | 'manual' | 'empty';
export type AspectMode = 'contain' | 'cover' | 'stretch' | 'native';

export type Slot = {
  id: string;
  name: string;
  type: SlotType;
  x: number;
  y: number;
  width: number;
  height: number;
  z_index: number;
  enabled: boolean;
  camera_id: string | null;
  rotation_group_id: string | null;
  selected_camera_id: string | null;
  stream_profile_id: string | null;
  stream_selection: 'manual' | 'automatic';
  aspect_mode: AspectMode;
  crop: Crop;
  background: string;
  border: string;
  border_width: number;
  label: string | null;
  title_position: 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'none';
  muted: boolean;
  locked: boolean;
  opacity: number;
  pixel_override: Record<string, number> | null;
};

export type LayoutData = {
  schema_version: number;
  slots: Slot[];
  background: string;
  output_width: number | null;
  output_height: number | null;
  grid_columns: number;
  grid_rows: number;
};

export type LayoutRevision = {
  id: string;
  revision: number;
  status: string;
  data: LayoutData;
  created_by: string | null;
  created_at: string;
};

export type Layout = {
  id: string;
  name: string;
  description: string;
  current_revision: number;
  active: boolean;
  display_profile_id: string | null;
  created_at: string;
  updated_at: string;
  revision: LayoutRevision | null;
};

export type RotationEntry = { camera_id: string; weight: number; stream_profile_id: string | null };
export type RotationGroup = {
  id: string;
  name: string;
  camera_entries: RotationEntry[];
  interval_seconds: number;
  order_mode: 'sequential' | 'reverse' | 'random' | 'weighted';
  enabled: boolean;
  preconnect: 'off' | 'next';
  failure_behavior: 'skip' | 'hold' | 'placeholder';
  rotate_together_group: string | null;
  start_position: number;
  created_at: string;
  updated_at: string;
};

export type DisplayProfile = {
  id: string;
  name: string;
  output_name: string | null;
  width: number;
  height: number;
  refresh_rate: number;
  rotation: 0 | 90 | 180 | 270;
  prevent_blanking: boolean;
  created_at: string;
  updated_at: string;
};

export type StreamHealth = {
  slot_id: string;
  camera_id: string;
  state: 'CONNECTING' | 'LIVE' | 'DEGRADED' | 'STALLED' | 'RECONNECTING' | 'OFFLINE' | 'DISABLED';
  detail: string | null;
  restart_count: number;
  switch_count?: number;
  last_restart_reason?: string | null;
  decoded_frames: number;
  dropped_frames: number;
};

export type RendererStatus = {
  backend?: string;
  state: string;
  sink?: string;
  output?: { width: number; height: number };
  uptime_seconds?: number;
  streams: Record<string, StreamHealth>;
  active_layout_id?: string | null;
  active_revision?: number | null;
  focused?: boolean;
  error?: string;
};

export type RendererConfig = {
  selected: 'auto' | 'gstreamer' | 'omxplayer';
  options: Array<{ name: string; available: boolean; reason: string | null }>;
  can_change?: boolean;
  restart_requested?: boolean;
  changed?: boolean;
};

export type SystemStatus = {
  version: string;
  time: string;
  metrics: {
    cpu_percent: number;
    cpu_temperature_c: number | null;
    memory: { percent: number; used_bytes: number; total_bytes: number };
    load_average: number[];
    boot_time: string;
  };
  counts: {
    cameras: number;
    layouts: number;
    rotation_groups: number;
    active_streams: number;
    failed_streams: number;
  };
  renderer: RendererStatus;
  settings: { bind: string; port: number; profile: string };
};

export type AuthState = {
  user: { id: string; username: string; is_admin: boolean };
  csrf_token: string;
  expires_at: string;
  renderer_restart_requested?: boolean;
};
