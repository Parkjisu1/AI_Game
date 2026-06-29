export interface Level {
  _id?: string;
  level_number: number;
  level_id: string;
  pkg: number;
  pos: number;
  chapter: number;
  purpose_type: string;
  target_cr: number;
  target_attempts: number;
  num_colors: number;
  color_distribution: string;
  field_rows: number;
  field_columns: number;
  total_cells: number;
  rail_capacity: number;
  rail_capacity_tier: string;
  queue_columns: number;
  queue_rows: number;
  gimmick_hidden: number;
  gimmick_chain: number;
  gimmick_pinata: number;
  gimmick_spawner_t: number;
  gimmick_pin: number;
  gimmick_lock_key: number;
  gimmick_surprise: number;
  gimmick_wall: number;
  gimmick_spawner_o: number;
  gimmick_pinata_box: number;
  gimmick_ice: number;
  gimmick_frozen_dart: number;
  gimmick_curtain: number;
  total_darts: number;
  dart_capacity_range: string;
  emotion_curve: string;
  designer_note: string;
  pixel_art_source: string;
  // 추가 필드
  image_url?: string;
  image_base64?: string;
  json_data?: string;
  status?: "draft" | "generated" | "approved" | "exported";
  created_at?: string;
  updated_at?: string;
}

export interface Task {
  _id?: string;
  title: string;
  description: string;
  assignee: string;
  status: "todo" | "in_progress" | "review" | "done";
  priority: "low" | "medium" | "high" | "urgent";
  level_numbers?: number[];
  created_at: string;
  updated_at: string;
}
