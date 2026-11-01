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
    <div className="flex flex-col gap-6 typist-card p-6" data-testid="pool-status-panel">
      <div className="flex justify-between items-center pb-4 border-b border-[#EAEAEA]">
        <div>
          <h2 className="text-base font-semibold text-[#111111]">Drill Pool Buffer</h2>
          <p className="text-xs text-[#666560]">
            Participant: <span className="font-medium text-[#111111]">{pool.alias}</span> (
            {pool.participant_id})
          </p>
        </div>
        <button
          type="button"
          onClick={onReplenish}
          className="typist-btn-primary px-4 py-2 text-xs"
          data-testid="replenish-btn"
        >
          Replenish Pool
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {pool.arms.map((arm) => {
          let badgeColor = "bg-[#EDF3EC] text-[#2B5930] border-[#D7E6D5]";
          let badgeText = "Ready";
          if (!arm.is_ready) {
            if (arm.queued_count > 0) {
              badgeColor = "bg-[#FBF3DB] text-[#8A5A00] border-[#EFE0B4]";
              badgeText = "Generating";
            } else {
              badgeColor = "bg-[#FDEBEB] text-[#9F2F2D] border-[#F5D0D2]";
              badgeText = "Deficit";
            }
          }

          return (
            <div
              key={arm.arm}
              className="flex flex-col justify-between p-4 typist-inset"
              data-testid={`arm-card-${arm.arm}`}
            >
              <div>
                <div className="flex justify-between items-center mb-2">
                  <h3 className="font-semibold text-[#111111] capitalize text-xs">{arm.arm}</h3>
                  <span
                    className={`px-2 py-0.5 text-[11px] font-medium rounded-md border ${badgeColor}`}
                    data-testid={`badge-${arm.arm}`}
                  >
                    {badgeText}
                  </span>
                </div>

                <div className="text-2xl font-normal font-mono tabular-nums text-[#111111] my-1">
                  {arm.ready_count}{" "}
                  <span className="text-sm font-normal text-[#8A8883]">/ {arm.target_count}</span>
                </div>
              </div>

              <div className="mt-3 pt-3 border-t border-[#EAEAEA] text-xs text-[#666560] space-y-1 font-mono tabular-nums">
                <div className="flex justify-between">
                  <span className="font-sans">Queued:</span>
                  <span className="font-medium text-[#111111]">{arm.queued_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="font-sans">Used:</span>
                  <span className="font-medium text-[#111111]">{arm.used_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="font-sans">Deficit:</span>
                  <span
                    className={`font-medium ${arm.deficit > 0 ? "text-[#9F2F2D] font-bold" : "text-[#111111]"}`}
                  >
                    {arm.deficit}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="pt-4 border-t border-[#EAEAEA]">
        <h3 className="text-xs font-medium text-[#666560] mb-2.5">Manual Drill Generation</h3>
        <form onSubmit={handleEnqueue} className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-[#666560]">
            Arm:
            <select
              value={selectedArm}
              onChange={(e) => setSelectedArm(e.target.value)}
              className="px-2.5 py-1.5 text-xs border border-[#D9D7D0] rounded-lg bg-white text-[#111111] focus:outline-hidden focus:border-[#111111]"
              data-testid="arm-select"
            >
              <option value="control">Control</option>
              <option value="heuristic">Heuristic</option>
              <option value="markov">Markov</option>
              <option value="llm">LLM</option>
            </select>
          </label>

          <label className="flex items-center gap-1.5 text-xs text-[#666560]">
            Count:
            <input
              type="number"
              min={1}
              max={20}
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              className="w-16 px-2.5 py-1.5 text-xs font-mono border border-[#D9D7D0] rounded-lg bg-white text-[#111111] focus:outline-hidden focus:border-[#111111]"
              data-testid="count-input"
            />
          </label>

          <button
            type="submit"
            className="typist-btn-secondary px-3.5 py-1.5 text-xs"
            data-testid="enqueue-btn"
          >
            Enqueue Drills
          </button>
        </form>
      </div>
    </div>
  );
}
