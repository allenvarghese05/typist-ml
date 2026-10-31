import { useState } from "react";
import type { ParticipantResponse } from "../../api/client";

export interface ParticipantListProps {
  readonly participants: readonly ParticipantResponse[];
  readonly selectedId: string | null;
  readonly onSelect: (id: string) => void;
  readonly onCreate: (alias: string, isBuilder: boolean) => void;
  readonly onAssign: (id: string) => void;
}

const STATUS_COLORS: Record<string, string> = {
  enrolled: "bg-gray-100 text-gray-800",
  baseline: "bg-blue-100 text-blue-800",
  assigned: "bg-purple-100 text-purple-800",
  practice: "bg-yellow-100 text-yellow-800",
  retest: "bg-indigo-100 text-indigo-800",
  done: "bg-green-100 text-green-800",
  withdrawn: "bg-red-100 text-red-800",
};

export function ParticipantList({
  participants,
  selectedId,
  onSelect,
  onCreate,
  onAssign,
}: ParticipantListProps): React.JSX.Element {
  const [alias, setAlias] = useState("");
  const [isBuilder, setIsBuilder] = useState(false);

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!alias.trim()) return;
    onCreate(alias.trim(), isBuilder);
    setAlias("");
    setIsBuilder(false);
  };

  return (
    <div className="flex flex-col gap-4 bg-white p-4 border border-gray-200 rounded-lg shadow-xs">
      <h2 className="text-lg font-semibold text-gray-900">Participants</h2>

      <form
        onSubmit={handleCreate}
        className="flex flex-col gap-2 p-3 bg-gray-50 rounded-md border border-gray-200"
      >
        <span className="text-xs font-semibold uppercase text-gray-600">Enroll Participant</span>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Participant alias"
            value={alias}
            onChange={(e) => setAlias(e.target.value)}
            className="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded-md bg-white focus:outline-hidden focus:ring-2 focus:ring-blue-500"
            data-testid="new-alias-input"
          />
          <button
            type="submit"
            disabled={!alias.trim()}
            className="px-3 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            data-testid="create-participant-btn"
          >
            Add
          </button>
        </div>
        <label className="flex items-center gap-2 text-xs text-gray-600 cursor-pointer">
          <input
            type="checkbox"
            checked={isBuilder}
            onChange={(e) => setIsBuilder(e.target.checked)}
            className="rounded-sm border-gray-300 text-blue-600 focus:ring-blue-500"
            data-testid="builder-checkbox"
          />
          Builder (unblinded)
        </label>
      </form>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-gray-700" data-testid="participants-table">
          <thead className="text-xs uppercase bg-gray-50 text-gray-500 border-b border-gray-200">
            <tr>
              <th className="py-2 px-3">Alias</th>
              <th className="py-2 px-3">Status</th>
              <th className="py-2 px-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200">
            {participants.length === 0 ? (
              <tr>
                <td colSpan={3} className="py-4 text-center text-gray-500">
                  No participants enrolled.
                </td>
              </tr>
            ) : (
              participants.map((p) => {
                const isSelected = p.id === selectedId;
                const canAssign = p.status === "baseline";
                return (
                  <tr
                    key={p.id}
                    onClick={() => onSelect(p.id)}
                    className={`cursor-pointer transition-colors ${
                      isSelected ? "bg-blue-50 font-medium" : "hover:bg-gray-50"
                    }`}
                    data-testid={`participant-row-${p.id}`}
                  >
                    <td className="py-2 px-3">
                      <div className="flex items-center gap-1.5">
                        <span>{p.alias}</span>
                        {p.is_builder && (
                          <span className="text-[10px] px-1 py-0.5 bg-gray-200 text-gray-700 rounded-sm">
                            Builder
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-gray-400 font-mono">{p.id}</div>
                    </td>
                    <td className="py-2 px-3">
                      <span
                        className={`inline-block px-2 py-0.5 text-xs rounded-full font-medium ${
                          STATUS_COLORS[p.status] ?? "bg-gray-100 text-gray-800"
                        }`}
                      >
                        {p.status}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <a
                          href={`#/results/${p.id}`}
                          onClick={(e) => e.stopPropagation()}
                          className="px-2 py-1 text-xs font-medium rounded-md text-blue-600 hover:text-blue-800 hover:underline"
                          data-testid={`debrief-link-${p.id}`}
                        >
                          Debrief
                        </a>
                        <button
                          type="button"
                          disabled={!canAssign}
                          onClick={(e) => {
                            e.stopPropagation();
                            onAssign(p.id);
                          }}
                          className="px-2.5 py-1 text-xs font-medium rounded-md bg-purple-600 text-white hover:bg-purple-700 disabled:opacity-30 disabled:cursor-not-allowed"
                          data-testid={`assign-btn-${p.id}`}
                        >
                          Assign
                        </button>
                      </div>
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
