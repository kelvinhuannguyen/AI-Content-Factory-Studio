export type ProductionType = "short_video" | "long_video" | "music_mv";

export type ProjectStatus =
  | "draft"
  | "topic_selected"
  | "script_ready"
  | "config_done"
  | "character_selected"
  | "scenes_ready"
  | "generating"
  | "assembly"
  | "quality_review"
  | "human_review"
  | "seo_ready"
  | "seo_approved"
  | "publishing"
  | "published"
  | "failed";

export interface Project {
  id: string;
  title: string;
  production_type: ProductionType;
  status: ProjectStatus;
  duration_seconds: number | null;
  genre: string | null;
  style: string | null;
  topic: string | null;
  preferred_language: string;
  final_video_r2_key: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectListResponse {
  total: number;
  page: number;
  page_size: number;
  items: Project[];
}
