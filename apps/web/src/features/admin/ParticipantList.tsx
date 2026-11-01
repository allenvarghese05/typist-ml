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
  enrolled: "bg-[#F3F2EE] text-[#4A4945] border-[#E4E2DC]",
  baseline: "bg-[#EBF3FA] text-[#1F5E8B] border-[#CEE2F4]",
  assigned: "bg-[#FBF3DB] text-[#8A5A00] border-[#EFE0B4]",
  practice: "bg-[#EBF3FA] text-[#1F5E8B] border-[#CEE2F4]",
  retest: "bg-[#EBF3FA] text-[#1F5E8B] border-[#CEE2F4]",
  done: "bg-[#EDF3EC] text-[#2B5930] border-[#D7E6D5]",
  withdrawn: "bg-[#FDEBEB] text-[#9F2F2D] border-[#F5D0D2]",
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
    <div className="flex flex-col gap-4 typist-card p-5">
      <h2 className="text-base font-semibold text-[#111111]">Participants</h2>

      <form onSubmit={handleCreate} className="flex flex-col gap-2.5 p-3.5 typist-inset">
        <span className="text-xs font-medium text-[#666560]">Enroll Participant</span>
        <div className="flex gap-2">
          <input
            type="text"
            placeholder="Participant alias"
            value={alias}
            onChange={(e) => setAlias(e.target.value)}
            className="flex-1 px-3 py-1.5 text-xs border border-[#D9D7D0] rounded-lg bg-white text-[#111111] focus:outline-hidden focus:border-[#111111]"
            data-testid="new-alias-input"
          />
          <button
            type="submit"
            disabled={!alias.trim()}
            className="typist-btn-primary px-3 py-1.5 text-xs"
            data-testid="create-participant-btn"
          >
            Add
          </button>
        </div>
        <label className="flex items-center gap-2 text-xs text-[#666560] cursor-pointer">
          <input
            type="checkbox"
            checked={isBuilder}
            onChange={(e) => setIsBuilder(e.target.checked)}
            className="rounded border-[#D9D7D0]"
            data-testid="builder-checkbox"
          />
          Builder (unblinded)
        </label>
      </form>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs text-[#4A4945]" data-testid="participants-table">
          <thead className="text-[11px] text-[#666560] border-b border-[#EAEAEA]">
            <tr>
              <th className="py-2 px-2 font-medium">Alias</th>
              <th className="py-2 px-2 font-medium">Status</th>
              <th className="py-2 px-2 font-medium text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#F1F0EC]">
            {participants.length === 0 ? (
              <tr>
                <td colSpan={3} className="py-4 text-center text-[#666560]">
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
                    className={`cursor-pointer typist-fluid ${
                      isSelected ? "bg-[#F5F4F0] font-medium" : "hover:bg-[#FBFBFA]"
                    }`}
                    data-testid={`participant-row-${p.id}`}
                  >
                    <td className="py-2.5 px-2">
                      <div className="flex items-center gap-1.5 text-[#111111]">
                        <span>{p.alias}</span>
                        {p.is_builder && (
                          <span className="text-[10px] px-1.5 py-0.5 bg-[#ECEAE3] text-[#4A4945] rounded">
                            Builder
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-[#8A8883] font-mono">{p.id.slice(0, 8)}</div>
                    </td>
                    <td className="py-2.5 px-2">
                      <span
                        className={`inline-block px-2 py-0.5 text-[11px] rounded-md border font-medium ${
                          STATUS_COLORS[p.status] ?? "bg-[#F3F2EE] text-[#4A4945] border-[#E4E2DC]"
                        }`}
                      >
                        {p.status}
                      </span>
                    </td>
                    <td className="py-2.5 px-2 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <a
                          href={`#/results/${p.id}`}
                          onClick={(e) => e.stopPropagation()}
                          className="px-2 py-1 text-xs font-medium text-[#111111] hover:underline underline-offset-2"
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
                          className="typist-btn-primary px-2.5 py-1 text-xs"
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
