import type { ModelConfig, Provider } from "../types";

const PROVIDER_MODELS: Record<Provider, string[]> = {
  anthropic: ["anthropic/claude-sonnet-4-6", "anthropic/claude-haiku-4-5-20251001", "anthropic/claude-opus-4-8"],
  openai: ["openai/gpt-4o", "openai/gpt-4o-mini", "openai/gpt-4-turbo"],
  groq: ["groq/llama-3.1-70b-versatile", "groq/llama-3.1-8b-instant", "groq/mixtral-8x7b-32768"],
  ollama: ["ollama/llama3", "ollama/mistral", "ollama/codellama"],
  custom: ["openai/custom"],
};

interface Props {
  value: ModelConfig;
  onChange: (cfg: ModelConfig) => void;
}

export function ModelPicker({ value, onChange }: Props) {
  function setField<K extends keyof ModelConfig>(key: K, val: ModelConfig[K]) {
    onChange({ ...value, [key]: val });
  }

  function setProvider(p: Provider) {
    onChange({
      provider: p,
      model: PROVIDER_MODELS[p][0],
      api_base: p === "ollama" ? "http://localhost:11434" : undefined,
      api_key: undefined,
    });
  }

  const needsKey = value.provider !== "anthropic" && value.provider !== "ollama";
  const needsBase = value.provider === "ollama" || value.provider === "custom";
  const models = PROVIDER_MODELS[value.provider];

  return (
    <div className="flex flex-wrap gap-2 items-center">
      {/* Provider */}
      <select
        value={value.provider}
        onChange={(e) => setProvider(e.target.value as Provider)}
        className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-orange-500"
      >
        {(["anthropic", "openai", "groq", "ollama", "custom"] as Provider[]).map((p) => (
          <option key={p} value={p}>{p.charAt(0).toUpperCase() + p.slice(1)}</option>
        ))}
      </select>

      {/* Model */}
      <select
        value={value.model}
        onChange={(e) => setField("model", e.target.value)}
        className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-orange-500"
      >
        {models.map((m) => (
          <option key={m} value={m}>{m.split("/")[1] || m}</option>
        ))}
      </select>

      {/* Endpoint */}
      {needsBase && (
        <input
          type="url"
          placeholder="Endpoint URL"
          value={value.api_base ?? ""}
          onChange={(e) => setField("api_base", e.target.value || undefined)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-orange-500 w-48"
        />
      )}

      {/* API key */}
      {needsKey && (
        <input
          type="password"
          placeholder="API key"
          value={value.api_key ?? ""}
          onChange={(e) => setField("api_key", e.target.value || undefined)}
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:ring-1 focus:ring-orange-500 w-36"
        />
      )}
    </div>
  );
}
