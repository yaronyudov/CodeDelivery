import { useState } from "react";
import { ChevronDown, ChevronUp, Plus, X } from "lucide-react";
import type { Skill, SessionSkillOverrides } from "../types";

interface Props {
  skills: Skill[];
  overrides: SessionSkillOverrides;
  onChange: (overrides: SessionSkillOverrides) => void;
}

const ALL_AGENTS = [
  "planner", "coder", "docker", "observability", "tester",
  "debugger", "reviewer", "review_supervisor", "security", "perf", "style", "coverage",
];

function applyOverride(
  overrides: SessionSkillOverrides,
  scopeKey: string,
  action: "add" | "remove",
  skillId: string,
  op: "append" | "delete",
): SessionSkillOverrides {
  const scope = overrides[scopeKey] ?? { add: [], remove: [] };
  let list = [...scope[action]];
  if (op === "append" && !list.includes(skillId)) list.push(skillId);
  if (op === "delete") list = list.filter(id => id !== skillId);
  const updated = { ...scope, [action]: list };
  const next = { ...overrides, [scopeKey]: updated };
  if (!updated.add.length && !updated.remove.length) delete next[scopeKey];
  return next;
}

function SkillChip({
  skill,
  removed,
  added,
  onToggle,
  onRemove,
}: {
  skill: Skill;
  removed?: boolean;
  added?: boolean;
  onToggle?: () => void;
  onRemove?: () => void;
}) {
  if (added) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border border-orange-700 text-orange-300 bg-orange-900/20">
        {skill.name}
        <button onClick={onRemove} className="hover:text-white transition-colors" title="Remove">
          <X size={10} />
        </button>
      </span>
    );
  }
  return (
    <button
      onClick={onToggle}
      title={removed ? "Re-enable for this run" : "Disable for this run"}
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border transition-all ${
        removed
          ? "border-gray-700 text-gray-600 bg-gray-800/50 line-through"
          : "border-gray-600 text-gray-300 bg-gray-800 hover:border-red-600 hover:text-red-300"
      }`}
    >
      {skill.name}
      {!removed && <X size={10} className="opacity-40" />}
    </button>
  );
}

function AddPicker({
  availableSkills,
  onAdd,
  onClose,
}: {
  availableSkills: Skill[];
  onAdd: (id: string) => void;
  onClose: () => void;
}) {
  if (availableSkills.length === 0) {
    return (
      <div className="flex items-center gap-1 mt-1">
        <span className="text-xs text-gray-600">No more skills available.</span>
        <button onClick={onClose} className="text-gray-600 hover:text-gray-400">
          <X size={11} />
        </button>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-1 mt-1">
      <select
        autoFocus
        defaultValue=""
        onChange={e => { if (e.target.value) onAdd(e.target.value); }}
        className="bg-gray-800 border border-gray-700 text-gray-200 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-orange-500"
      >
        <option value="" disabled>Pick skill…</option>
        {availableSkills.map(s => (
          <option key={s.id} value={s.id}>{s.name}</option>
        ))}
      </select>
      <button onClick={onClose} className="text-gray-600 hover:text-gray-400 p-0.5">
        <X size={11} />
      </button>
    </div>
  );
}

function ScopeSection({
  scopeKey,
  label,
  allSkills,
  overrides,
  onChange,
}: {
  scopeKey: string;
  label: string;
  allSkills: Skill[];
  overrides: SessionSkillOverrides;
  onChange: (o: SessionSkillOverrides) => void;
}) {
  const [showPicker, setShowPicker] = useState(false);
  const ops = overrides[scopeKey] ?? { add: [], remove: [] };

  const defaultsForScope = allSkills.filter(s => {
    if (!s.is_default) return false;
    if (scopeKey === "*") return s.target_agents.length === 0;
    return s.target_agents.includes(scopeKey);
  });

  const addedSkills = ops.add
    .map(id => allSkills.find(s => s.id === id))
    .filter(Boolean) as Skill[];

  const addableSkills = allSkills.filter(s =>
    !defaultsForScope.find(d => d.id === s.id) && !addedSkills.find(a => a.id === s.id)
  );

  function toggleDefault(skillId: string) {
    const removed = ops.remove.includes(skillId);
    onChange(applyOverride(overrides, scopeKey, "remove", skillId, removed ? "delete" : "append"));
  }

  function addSkill(skillId: string) {
    onChange(applyOverride(overrides, scopeKey, "add", skillId, "append"));
    setShowPicker(false);
  }

  function removeAdded(skillId: string) {
    onChange(applyOverride(overrides, scopeKey, "add", skillId, "delete"));
  }

  const hasContent = defaultsForScope.length > 0 || addedSkills.length > 0;

  return (
    <div>
      <div className="flex items-center gap-1 mb-1">
        <span className="text-[11px] font-semibold text-gray-500 uppercase tracking-wider">{label}</span>
        <button
          onClick={() => setShowPicker(v => !v)}
          className="text-gray-600 hover:text-orange-400 transition-colors"
          title="Add skill"
        >
          <Plus size={11} />
        </button>
      </div>

      {hasContent ? (
        <div className="flex flex-wrap gap-1.5">
          {defaultsForScope.map(skill => (
            <SkillChip
              key={skill.id}
              skill={skill}
              removed={ops.remove.includes(skill.id)}
              onToggle={() => toggleDefault(skill.id)}
            />
          ))}
          {addedSkills.map(skill => (
            <SkillChip
              key={skill.id}
              skill={skill}
              added
              onRemove={() => removeAdded(skill.id)}
            />
          ))}
        </div>
      ) : !showPicker ? (
        <p className="text-xs text-gray-600 italic">No active skills — click + to add one.</p>
      ) : null}

      {showPicker && (
        <AddPicker
          availableSkills={addableSkills}
          onAdd={addSkill}
          onClose={() => setShowPicker(false)}
        />
      )}
    </div>
  );
}

function AgentScopeAdder({
  shownAgents,
  allSkills,
  overrides,
  onChange,
}: {
  shownAgents: string[];
  allSkills: Skill[];
  overrides: SessionSkillOverrides;
  onChange: (o: SessionSkillOverrides) => void;
}) {
  const [open, setOpen] = useState(false);
  const [agent, setAgent] = useState("");
  const [skillId, setSkillId] = useState("");

  const availableAgents = ALL_AGENTS.filter(a => !shownAgents.includes(a));
  if (availableAgents.length === 0) return null;

  function handleAdd() {
    if (!agent || !skillId) return;
    onChange(applyOverride(overrides, agent, "add", skillId, "append"));
    setOpen(false);
    setAgent("");
    setSkillId("");
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="text-xs text-gray-600 hover:text-orange-400 flex items-center gap-1 transition-colors mt-1"
      >
        <Plus size={11} />
        Override per-agent
      </button>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5 mt-1">
      <select
        value={agent}
        onChange={e => { setAgent(e.target.value); setSkillId(""); }}
        className="bg-gray-800 border border-gray-700 text-gray-200 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-orange-500"
      >
        <option value="">Agent…</option>
        {availableAgents.map(a => <option key={a} value={a}>{a}</option>)}
      </select>
      {agent && (
        <select
          value={skillId}
          onChange={e => setSkillId(e.target.value)}
          className="bg-gray-800 border border-gray-700 text-gray-200 rounded px-2 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-orange-500"
        >
          <option value="">Skill…</option>
          {allSkills.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      )}
      <button
        onClick={handleAdd}
        disabled={!agent || !skillId}
        className="text-xs px-2 py-1 bg-orange-600 hover:bg-orange-700 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded transition-colors"
      >
        Add
      </button>
      <button onClick={() => setOpen(false)} className="text-gray-600 hover:text-gray-400">
        <X size={11} />
      </button>
    </div>
  );
}

export function SessionSkills({ skills, overrides, onChange }: Props) {
  const [open, setOpen] = useState(false);

  const overrideCount = Object.values(overrides).reduce(
    (n, ops) => n + ops.add.length + ops.remove.length,
    0,
  );

  // Per-agent scopes that have either defaults or active overrides
  const perAgentScopes = ALL_AGENTS.filter(agent => {
    const hasDefaults = skills.some(s => s.is_default && s.target_agents.includes(agent));
    const hasOverrides = (overrides[agent]?.add.length ?? 0) + (overrides[agent]?.remove.length ?? 0) > 0;
    return hasDefaults || hasOverrides;
  });

  return (
    <div className="border border-gray-700/60 rounded-lg px-3 py-2 bg-gray-800/20">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center justify-between text-xs text-gray-400 hover:text-gray-200 transition-colors"
      >
        <span className="font-medium flex items-center gap-1.5">
          Session Skills
          {overrideCount > 0 && (
            <span className="bg-orange-600 text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full leading-none">
              {overrideCount}
            </span>
          )}
        </span>
        {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
      </button>

      {open && (
        <div className="mt-3 space-y-3 border-t border-gray-700/50 pt-3">
          <ScopeSection
            scopeKey="*"
            label="All Agents"
            allSkills={skills}
            overrides={overrides}
            onChange={onChange}
          />

          {perAgentScopes.map(agent => (
            <ScopeSection
              key={agent}
              scopeKey={agent}
              label={agent}
              allSkills={skills}
              overrides={overrides}
              onChange={onChange}
            />
          ))}

          <AgentScopeAdder
            shownAgents={perAgentScopes}
            allSkills={skills}
            overrides={overrides}
            onChange={onChange}
          />
        </div>
      )}
    </div>
  );
}
