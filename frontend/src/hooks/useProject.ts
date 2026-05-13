import useSWR, { mutate as globalMutate } from "swr";
import { api } from "@/lib/api";
import type { Project, ProjectListResponse } from "@/types/project";

const fetcher = (url: string) => api.get(url);

export function useProjects(page = 1, pageSize = 20) {
  const { data, error, isLoading, mutate } = useSWR<ProjectListResponse>(
    `/projects?page=${page}&page_size=${pageSize}`,
    fetcher,
    { refreshInterval: 30_000 }
  );
  return { data, error, isLoading, mutate };
}

export function useProject(id: string | null) {
  const { data, error, isLoading, mutate } = useSWR<Project>(
    id ? `/projects/${id}` : null,
    fetcher,
    { refreshInterval: 10_000 }
  );
  return { project: data, error, isLoading, mutate };
}

export async function createProject(
  production_type: string,
  preferred_language = "vi"
): Promise<Project> {
  return api.post<Project>("/projects", { production_type, preferred_language });
}

export async function updateProject(id: string, patch: Record<string, unknown>): Promise<Project> {
  const updated = await api.patch<Project>(`/projects/${id}`, patch);
  await globalMutate(`/projects/${id}`);
  return updated;
}
