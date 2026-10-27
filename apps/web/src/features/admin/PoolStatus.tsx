import { useState } from "react";
import type { PoolResponse } from "../../api/client";

export interface PoolStatusProps {
  readonly pool: PoolResponse | null;
  readonly onReplenish: () => void;
  readonly onEnqueue: (arm: string, requested: number) => void;
}

export function PoolStatus({ pool, onReplenish, onEnqueue }: PoolStatusProps): React.JSX.Element {
  const [selectedArm, setSelectedArm] = useState("control");
  const [count, setCount] = useState(2);

  if (!pool) {
    return (
      <div className="bg-white p-6 border border-gray-200 rounded-lg text-gray-500 text-center">
        No participant selected or pool status unavailable.
      </div>
    );
  }

  const handleEnqueue = (e: React.FormEvent) => {
    e.preventDefault();
    onEnqueue(selectedArm, count);
  };

  return (
    <div
      className="flex flex-col gap-6 bg-white p-6 border border-gray-200 rounded-lg shadow-xs"
      data-testid="pool-status-panel"
    >
      <div className="flex justify-between items-center pb-4 border-b border-gray-200">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Drill Pool Buffer</h2>
          <p className="text-xs text-gray-500">
            Participant: <span className="font-medium text-gray-800">{pool.alias}</span> (
            {pool.participant_id})
          </p>
        </div>
        <button
          type="button"
          onClick={onReplenish}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors"
          data-testid="replenish-btn"
        >
          Replenish Pool
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {pool.arms.map((arm) => {
          let badgeColor = "bg-green-100 text-green-800";
          let badgeText = "Ready";
          if (!arm.is_ready) {
            if (arm.queued_count > 0) {
              badgeColor = "bg-yellow-100 text-yellow-800";
              badgeText = "Generating";
            } else {
              badgeColor = "bg-red-100 text-red-800";
              badgeText = "Deficit";
            }
          }

          return (
            <div
              key={arm.arm}
              className="flex flex-col justify-between p-4 bg-gray-50 border border-gray-200 rounded-lg"
              data-testid={`arm-card-${arm.arm}`}
            >
              <div>
                <div className="flex justify-between items-center mb-2">
                  <h3 className="font-semibold text-gray-800 uppercase tracking-wider text-xs">
                    {arm.arm}
                  </h3>
                  <span
                    className={`px-2 py-0.5 text-xs font-medium rounded-full ${badgeColor}`}
                    data-testid={`badge-${arm.arm}`}
                  >
                    {badgeText}
                  </span>
                </div>

                <div className="text-2xl font-bold text-gray-900 my-1">
                  {arm.ready_count}{" "}
                  <span className="text-sm font-normal text-gray-500">/ {arm.target_count}</span>
                </div>
              </div>

              <div className="mt-3 pt-3 border-t border-gray-200 text-xs text-gray-600 space-y-1">
                <div className="flex justify-between">
                  <span>Queued:</span>
                  <span className="font-medium text-gray-800">{arm.queued_count}</span>
                </div>
                <div className="flex justify-between">
                  <span>Used:</span>
                  <span className="font-medium text-gray-800">{arm.used_count}</span>
                </div>
                <div className="flex justify-between">
                  <span>Deficit:</span>
                  <span
                    className={`font-medium ${arm.deficit > 0 ? "text-red-600 font-bold" : "text-gray-800"}`}
                  >
                    {arm.deficit}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="pt-4 border-t border-gray-200">
        <h3 className="text-sm font-semibold text-gray-800 mb-2">Manual Drill Generation</h3>
        <form onSubmit={handleEnqueue} className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-gray-600">
            Arm:
            <select
              value={selectedArm}
              onChange={(e) => setSelectedArm(e.target.value)}
              className="px-2.5 py-1.5 text-sm border border-gray-300 rounded-md bg-white focus:outline-hidden focus:ring-2 focus:ring-blue-500"
              data-testid="arm-select"
            >
              <option value="control">Control</option>
              <option value="heuristic">Heuristic</option>
              <option value="markov">Markov</option>
              <option value="llm">LLM</option>
            </select>
          </label>

          <label className="flex items-center gap-1.5 text-xs text-gray-600">
            Count:
            <input
              type="number"
              min={1}
              max={20}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              className="w-16 px-2.5 py-1.5 text-sm border border-gray-300 rounded-md bg-white focus:outline-hidden focus:ring-2 focus:ring-blue-500"
              data-testid="count-input"
            />
          </label>

          <button
            type="submit"
            className="px-3.5 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 border border-gray-300 rounded-md transition-colors"
            data-testid="enqueue-btn"
          >
            Enqueue Drills
          </button>
        </form>
      </div>
    </div>
  );
}
