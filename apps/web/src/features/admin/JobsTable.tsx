import type { JobResponse } from "../../api/client";

export interface JobsTableProps {
  readonly jobs: readonly JobResponse[];
  readonly onRefresh: () => void;
  readonly onRetry?: (job: JobResponse) => void;
}

const STATUS_BADGES: Record<string, string> = {
  done: "bg-green-100 text-green-800",
  running: "bg-blue-100 text-blue-800",
  pending: "bg-yellow-100 text-yellow-800",
  failed: "bg-red-100 text-red-800",
};

export function JobsTable({ jobs, onRefresh, onRetry }: JobsTableProps): React.JSX.Element {
  return (
    <div
      className="flex flex-col gap-4 bg-white p-6 border border-gray-200 rounded-lg shadow-xs"
      data-testid="jobs-panel"
    >
      <div className="flex justify-between items-center pb-4 border-b border-gray-200">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Generation Jobs Queue</h2>
          <p className="text-xs text-gray-500">
            Monitor background LLM and heuristic generation tasks
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 border border-gray-300 rounded-md transition-colors"
          data-testid="refresh-jobs-btn"
        >
          Refresh
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-gray-700" data-testid="jobs-table">
          <thead className="text-xs uppercase bg-gray-50 text-gray-500 border-b border-gray-200">
            <tr>
              <th className="py-2.5 px-3">Job ID</th>
              <th className="py-2.5 px-3">Arm</th>
              <th className="py-2.5 px-3">Requested</th>
              <th className="py-2.5 px-3">Status</th>
              <th className="py-2.5 px-3">Retries</th>
              <th className="py-2.5 px-3">Created</th>
              <th className="py-2.5 px-3">Details / Error</th>
              <th className="py-2.5 px-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {jobs.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-6 text-center text-gray-500">
                  No generation jobs found.
                </td>
              </tr>
            ) : (
              jobs.map((job) => {
                const badgeColor = STATUS_BADGES[job.status] ?? "bg-gray-100 text-gray-800";
                return (
                  <tr key={job.id} className="hover:bg-gray-50" data-testid={`job-row-${job.id}`}>
                    <td className="py-2.5 px-3 font-mono text-xs text-gray-600">{job.id}</td>
                    <td className="py-2.5 px-3 font-medium uppercase text-xs">{job.arm}</td>
                    <td className="py-2.5 px-3">{job.requested}</td>
                    <td className="py-2.5 px-3">
                      <span
                        className={`px-2 py-0.5 text-xs font-medium rounded-full ${badgeColor}`}
                      >
                        {job.status}
                      </span>
                    </td>
                    <td className="py-2.5 px-3">{job.retries}</td>
                    <td className="py-2.5 px-3 text-xs text-gray-500">
                      {new Date(job.created_at).toLocaleTimeString()}
                    </td>
                    <td className="py-2.5 px-3 text-xs">
                      {job.error ? (
                        <span
                          className="text-red-600 font-mono"
                          title={job.error}
                          data-testid={`job-error-${job.id}`}
                        >
                          {job.error}
                        </span>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      {job.status === "failed" && onRetry && (
                        <button
                          type="button"
                          onClick={() => onRetry(job)}
                          className="px-2 py-1 text-xs font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md"
                          data-testid={`retry-job-btn-${job.id}`}
                        >
                          Re-enqueue
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
