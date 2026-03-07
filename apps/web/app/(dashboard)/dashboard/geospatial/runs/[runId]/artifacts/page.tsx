"use client";

import { apiFetch } from "@phil-onion-watch/api-client";
import { apiConfig } from "@phil-onion-watch/config";
import { DataTable, EmptyState, ErrorState, LoadingState, PageHeader, SectionShell, StatCard } from "@phil-onion-watch/ui";
import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";

import { useAuth } from "../../../../../../providers";

type ArtifactCenterResponse = {
  run_id: number;
  generated_at: string;
  artifact_count: number;
  total_size_bytes: number;
  artifacts: Array<{
    artifact_key: string;
    label: string;
    filename: string;
    content_type: string;
    size_bytes: number;
    checksum_sha256: string;
    download_path: string;
    generated_at: string;
  }>;
};

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export default function GeospatialRunArtifactCenterPage() {
  const params = useParams<{ runId: string }>();
  const runId = Number(Array.isArray(params?.runId) ? params?.runId[0] : params?.runId);
  const { token } = useAuth();
  const [message, setMessage] = useState("");
  const [downloadingKey, setDownloadingKey] = useState("");

  const center = useQuery({
    queryKey: ["geospatial-run-artifact-center-page", token, runId],
    queryFn: () => apiFetch<ArtifactCenterResponse>(`/api/v1/geospatial/runs/${runId}/artifacts/download-center`, { token }),
    enabled: !!token && Number.isFinite(runId) && runId > 0,
  });

  async function downloadArtifact(artifactKey: string, filename: string) {
    try {
      setDownloadingKey(artifactKey);
      const response = await fetch(`${apiConfig.baseUrl}/api/v1/geospatial/runs/${runId}/artifacts/${artifactKey}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        throw new Error(`artifact-download-${response.status}`);
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setMessage(`Downloaded ${filename}`);
    } catch {
      setMessage("Artifact download failed");
    } finally {
      setDownloadingKey("");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Run #${runId} Artifact Download Center`}
        subtitle="Download run outputs, provenance exports, and diagnostics artifacts with checksums."
        actions={(
          <div className="flex flex-wrap gap-2 text-sm">
            <a href={`/dashboard/geospatial/runs/${runId}`} className="rounded border border-slate-300 px-3 py-1 font-medium text-slate-700 hover:bg-slate-50">Back to run</a>
            <a href="/dashboard/geospatial/aois" className="rounded border border-slate-300 px-3 py-1 font-medium text-slate-700 hover:bg-slate-50">AOI workbench</a>
          </div>
        )}
      />

      {message ? <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">{message}</div> : null}
      {center.isLoading ? <LoadingState label="Loading run artifact download center..." /> : null}
      {center.error ? <ErrorState message="Failed to load run artifact download center" /> : null}

      {center.data ? (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <StatCard label="Artifact count" value={center.data.artifact_count} hint={`Run #${center.data.run_id}`} />
            <StatCard label="Total size" value={formatBytes(center.data.total_size_bytes)} hint={`${center.data.total_size_bytes} bytes`} />
            <StatCard label="Generated at" value={center.data.generated_at.slice(0, 19).replace("T", " ")} hint="UTC" />
          </div>

          <SectionShell title="Artifacts">
            {center.data.artifacts.length === 0 ? (
              <EmptyState title="No artifacts available" description="This run has no generated artifact payloads yet." />
            ) : (
              <DataTable
                columns={[
                  { key: "label", label: "Artifact" },
                  { key: "filename", label: "File" },
                  { key: "content_type", label: "Type" },
                  { key: "size_bytes", label: "Size", render: (row) => formatBytes(Number((row as { size_bytes: number }).size_bytes ?? 0)) },
                  { key: "checksum_sha256", label: "Checksum", render: (row) => String((row as { checksum_sha256: string }).checksum_sha256).slice(0, 16) },
                  {
                    key: "artifact_key",
                    label: "Actions",
                    render: (row) => {
                      const artifact = row as ArtifactCenterResponse["artifacts"][number];
                      return (
                        <button
                          type="button"
                          disabled={downloadingKey === artifact.artifact_key}
                          onClick={() => {
                            void downloadArtifact(artifact.artifact_key, artifact.filename);
                          }}
                          className="rounded border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                        >
                          {downloadingKey === artifact.artifact_key ? "Downloading..." : "Download"}
                        </button>
                      );
                    },
                  },
                ]}
                rows={center.data.artifacts as unknown as Record<string, unknown>[]}
              />
            )}
          </SectionShell>
        </>
      ) : null}
    </div>
  );
}

