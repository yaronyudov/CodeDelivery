import { useEffect, useState } from "react";
import { Plus, Trash2, X, ToggleLeft, ToggleRight, Edit2, Check } from "lucide-react";
import type { Skill } from "../types";
import {
  listSkills,
  createSkill,
  updateSkill,
  deleteSkill,
  toggleSkillDefault,
} from "../api/skills";

const ALL_AGENTS = [
  "planner", "coder", "docker", "observability",
  "tester", "debugger", "reviewer", "review_supervisor",
  "security", "perf", "style", "coverage",
];

interface Props {
  onClose: () => void;
}

const EMPTY_FORM = {
  id: "",
  name: "",
  description: "",
  kind: "prompt_injection" as Skill["kind"],
  target_agents: [] as string[],
  prompt_addon: "",
  is_default: false,
};

export function SkillsManager({ onClose }: Props) {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSkills()
      .then(setSkills)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  async function handleCreate() {
    setError(null);
    try {
      const created = await createSkill({
        ...form,
        prompt_addon: form.kind === "prompt_injection" ? form.prompt_addon || null : null,
      });
      setSkills((prev) => [...prev, created]);
      setShowCreate(false);
      setForm(EMPTY_FORM);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to create skill");
    }
  }

  async function handleUpdate(skill: Skill) {
    setError(null);
    try {
      const updated = await updateSkill(skill.id, {
        name: skill.name,
        description: skill.description,
        target_agents: skill.target_agents,
        prompt_addon: skill.prompt_addon,
        is_default: skill.is_default,
      });
      setSkills((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
      setEditingId(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to update skill");
    }
  }

  async function handleDelete(id: string) {
    setError(null);
    try {
      await deleteSkill(id);
      setSkills((prev) => prev.filter((s) => s.id !== id));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to delete skill");
    }
  }

  async function handleToggleDefault(id: string) {
    setError(null);
    try {
      const updated = await toggleSkillDefault(id);
      setSkills((prev) => prev.map((s) => (s.id === updated.id ? updated : s)));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to toggle default");
    }
  }

  const injections = skills.filter((s) => s.kind === "prompt_injection");
  const toggles = skills.filter((s) => s.kind === "agent_toggle");

  return (
    <div className="fixed inset-0 z-50 flex">
      {/* Backdrop */}
      <div className="flex-1 bg-black/60" onClick={onClose} />

      {/* Panel */}
      <div className="w-[560px] bg-gray-900 border-l border-gray-800 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
          <h2 className="text-sm font-semibold text-gray-200">Skill Library</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300">
            <X size={16} />
          </button>
        </div>

        {error && (
          <div className="mx-5 mt-3 text-xs text-red-400 bg-red-900/30 border border-red-800 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-6">
          {/* Prompt injections */}
          <Section
            title="Prompt Injections"
            description="Append custom instructions to agent system prompts"
            skills={injections}
            editingId={editingId}
            onEdit={setEditingId}
            onSave={handleUpdate}
            onDelete={handleDelete}
            onToggleDefault={handleToggleDefault}
            loading={loading}
          />

          {/* Agent toggles */}
          <Section
            title="Agent Toggles"
            description="Enable or disable specific pipeline agents"
            skills={toggles}
            editingId={editingId}
            onEdit={setEditingId}
            onSave={handleUpdate}
            onDelete={handleDelete}
            onToggleDefault={handleToggleDefault}
            loading={loading}
          />

          {/* Create form */}
          {showCreate ? (
            <div className="bg-gray-800 border border-gray-700 rounded-xl p-4 space-y-3">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest">New Skill</p>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">ID (slug)</label>
                  <input
                    value={form.id}
                    onChange={(e) => setForm((f) => ({ ...f, id: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "") }))}
                    placeholder="my-skill"
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-orange-500"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Name</label>
                  <input
                    value={form.name}
                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder="Display name"
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-orange-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">Kind</label>
                <select
                  value={form.kind}
                  onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value as Skill["kind"] }))}
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-orange-500"
                >
                  <option value="prompt_injection">Prompt Injection</option>
                  <option value="agent_toggle">Agent Toggle (disables agent)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">Description</label>
                <input
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  placeholder="What does this skill do?"
                  className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-orange-500"
                />
              </div>

              <div>
                <label className="block text-xs text-gray-500 mb-1">Target agents (empty = all)</label>
                <AgentChips
                  selected={form.target_agents}
                  onChange={(v) => setForm((f) => ({ ...f, target_agents: v }))}
                />
              </div>

              {form.kind === "prompt_injection" && (
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Prompt text to inject</label>
                  <textarea
                    value={form.prompt_addon}
                    onChange={(e) => setForm((f) => ({ ...f, prompt_addon: e.target.value }))}
                    rows={4}
                    placeholder="Instructions to append to the agent's system prompt…"
                    className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200 resize-none focus:outline-none focus:ring-1 focus:ring-orange-500"
                  />
                </div>
              )}

              <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.is_default}
                  onChange={(e) => setForm((f) => ({ ...f, is_default: e.target.checked }))}
                  className="rounded border-gray-600 bg-gray-800 text-orange-500"
                />
                Active by default for all runs
              </label>

              <div className="flex gap-2 pt-1">
                <button
                  onClick={handleCreate}
                  disabled={!form.id || !form.name}
                  className="px-4 py-1.5 bg-orange-500 hover:bg-orange-600 disabled:opacity-40 text-white text-sm font-semibold rounded-lg"
                >
                  Create
                </button>
                <button
                  onClick={() => { setShowCreate(false); setForm(EMPTY_FORM); }}
                  className="px-4 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 text-sm rounded-lg"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowCreate(true)}
              className="flex items-center gap-2 text-sm text-orange-400 hover:text-orange-300"
            >
              <Plus size={14} /> New skill
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Section({
  title, description, skills, editingId, onEdit, onSave, onDelete, onToggleDefault, loading,
}: {
  title: string;
  description: string;
  skills: Skill[];
  editingId: string | null;
  onEdit: (id: string | null) => void;
  onSave: (skill: Skill) => void;
  onDelete: (id: string) => void;
  onToggleDefault: (id: string) => void;
  loading: boolean;
}) {
  const [editDraft, setEditDraft] = useState<Skill | null>(null);

  function startEdit(skill: Skill) {
    setEditDraft({ ...skill });
    onEdit(skill.id);
  }

  function cancelEdit() {
    setEditDraft(null);
    onEdit(null);
  }

  return (
    <div>
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-widest mb-1">{title}</h3>
      <p className="text-xs text-gray-600 mb-3">{description}</p>
      {loading ? (
        <p className="text-xs text-gray-600">Loading…</p>
      ) : skills.length === 0 ? (
        <p className="text-xs text-gray-600 italic">No skills yet.</p>
      ) : (
        <div className="space-y-2">
          {skills.map((skill) =>
            editingId === skill.id && editDraft ? (
              <SkillEditCard
                key={skill.id}
                draft={editDraft}
                onChange={setEditDraft}
                onSave={() => { onSave(editDraft); setEditDraft(null); }}
                onCancel={cancelEdit}
              />
            ) : (
              <SkillCard
                key={skill.id}
                skill={skill}
                onEdit={() => startEdit(skill)}
                onDelete={() => onDelete(skill.id)}
                onToggleDefault={() => onToggleDefault(skill.id)}
              />
            )
          )}
        </div>
      )}
    </div>
  );
}

function SkillCard({ skill, onEdit, onDelete, onToggleDefault }: {
  skill: Skill;
  onEdit: () => void;
  onDelete: () => void;
  onToggleDefault: () => void;
}) {
  return (
    <div className="flex items-start gap-3 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2.5">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-gray-200 truncate">{skill.name}</span>
          {skill.is_system && (
            <span className="text-[10px] bg-gray-700 text-gray-400 px-1.5 py-0.5 rounded">system</span>
          )}
          {skill.target_agents.length > 0 && (
            <span className="text-[10px] text-gray-500 truncate">
              → {skill.target_agents.join(", ")}
            </span>
          )}
        </div>
        {skill.description && (
          <p className="text-xs text-gray-500 mt-0.5 truncate">{skill.description}</p>
        )}
      </div>
      <div className="flex items-center gap-1.5 shrink-0">
        <button
          onClick={onToggleDefault}
          title={skill.is_default ? "Default ON — click to remove from defaults" : "Set as default"}
          className={`transition-colors ${skill.is_default ? "text-orange-400 hover:text-orange-300" : "text-gray-600 hover:text-gray-400"}`}
        >
          {skill.is_default ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
        </button>
        <button onClick={onEdit} className="text-gray-600 hover:text-gray-300">
          <Edit2 size={13} />
        </button>
        {!skill.is_system && (
          <button onClick={onDelete} className="text-gray-600 hover:text-red-400">
            <Trash2 size={13} />
          </button>
        )}
      </div>
    </div>
  );
}

function SkillEditCard({ draft, onChange, onSave, onCancel }: {
  draft: Skill;
  onChange: (s: Skill) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  return (
    <div className="bg-gray-800 border border-orange-900/50 rounded-lg px-3 py-3 space-y-2">
      <input
        value={draft.name}
        onChange={(e) => onChange({ ...draft, name: e.target.value })}
        className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-orange-500"
        placeholder="Name"
      />
      <input
        value={draft.description}
        onChange={(e) => onChange({ ...draft, description: e.target.value })}
        className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-orange-500"
        placeholder="Description"
      />
      <AgentChips
        selected={draft.target_agents}
        onChange={(v) => onChange({ ...draft, target_agents: v })}
      />
      {draft.kind === "prompt_injection" && (
        <textarea
          value={draft.prompt_addon || ""}
          onChange={(e) => onChange({ ...draft, prompt_addon: e.target.value })}
          rows={3}
          className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1 text-sm text-gray-200 resize-none focus:outline-none focus:ring-1 focus:ring-orange-500"
          placeholder="Prompt text…"
        />
      )}
      <div className="flex gap-2">
        <button onClick={onSave} className="flex items-center gap-1 px-3 py-1 bg-orange-500 hover:bg-orange-600 text-white text-xs font-semibold rounded">
          <Check size={12} /> Save
        </button>
        <button onClick={onCancel} className="px-3 py-1 bg-gray-700 hover:bg-gray-600 text-gray-300 text-xs rounded">
          Cancel
        </button>
      </div>
    </div>
  );
}

function AgentChips({ selected, onChange }: { selected: string[]; onChange: (v: string[]) => void }) {
  function toggle(agent: string) {
    onChange(
      selected.includes(agent) ? selected.filter((a) => a !== agent) : [...selected, agent],
    );
  }
  return (
    <div className="flex flex-wrap gap-1">
      {ALL_AGENTS.map((agent) => (
        <button
          key={agent}
          onClick={() => toggle(agent)}
          className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
            selected.includes(agent)
              ? "bg-orange-900/50 border-orange-700 text-orange-300"
              : "bg-gray-900 border-gray-700 text-gray-500 hover:border-gray-500"
          }`}
        >
          {agent}
        </button>
      ))}
    </div>
  );
}
